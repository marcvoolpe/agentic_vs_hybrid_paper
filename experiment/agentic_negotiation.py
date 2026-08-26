import copy
import asyncio
import sys
import json
from typing import Callable

from ollama import ChatResponse


from .bot_base import BotBase, InteractionList
from .bot_llm import BotLLM, _normalize_llm_provider
from .bot_task import BotTask
from .prompts import HYBRID_PROMPTS, agent_system_final_prompts
from .offer import Offer, OfferList
from .optimal import nash_bargaining_solution
from .utils import log_function
from .bot_tools import numeric_offer_evaluation, TOOLS, ACTION_TOOLS
from .open_router import LLMTransportError
from .telemetry import (
    increment_bot_turn, log_drafts, log_offer_event, log_llm_call,
    mark_chosen, set_bot_response,
)

KNOWN_TOOL_NAMES = {
    'send_chat', 'propose_offer', 'send_offer', 'accept_offer',
    'evaluate_offer', 'compute_nash', 'evaluate_single',
}




class FullAgentBot(BotBase, BotLLM, BotTask):
    def __init__(self, player: 'Player'):
        super().__init__()
        self.id_in_group = -1
        self.player = player
        self.role = player.opposite_role

        # Async functions loose self.player, copy what is needed
        self._pending_offer1 = None
        self._pending_offer2 = None
        self._pending_offer3 = None
        self._current_call_id = ''
        self._propose_call_id = ''
        self._current_step = 0
        self._loop_trigger = 'chat'

        self.config = copy.deepcopy(player.session.config)
        self.config.update({
            'idx': player.id_in_group,
            'code': player.participant.code,
            'session_code': player.session.code,
            'round_number': player.round_number,
            'group_name': self.group_name(player),
            'roles': {'human_role': player.role, 'bot_role': self.role},

            'production_cost': player.group.production_cost,
            'market_price': player.group.market_price,
            'demand': player.group.demand,
            'class_name': player.group.class_name,
            'optimal_offer': player.group.optimal_offer,

            'bot_vars': player.bot_vars,
        })

    def start_initial(self):
        if self.player.field_maybe_none('llm_interactions') is None:

            self.player.llm_interactions = []
            self._offers_interactions()
            asyncio.ensure_future(self.start_task(self._run_initial))

    def receive_chat_from_human(self, user_message:str):
        self.user_message = user_message
        self._offers_interactions()
        asyncio.ensure_future(self.start_task(self._run_chat))

    def receive_offer_from_human(
            self, price: int, quantity: int, body: str | None = None,
    ):
        message = HYBRID_PROMPTS['offer_string'] % (price, quantity)
        if body:
            message = f"{message}\n{body}"
        self.user_message = message
        self._offers_interactions()
        asyncio.ensure_future(self.start_task(self._run_offer))

    async def start_task(self, coro: Callable):
        """Agentic bot uses Cerebras API; do not block on Ollama host queue."""
        log_function(__class__, sys._getframe().f_code.co_name)

        self.ensure_exception_handler()
        data = {'llm_host': None,
                'group_name': self.config['group_name'],
                'session_code': self.config['session_code'],
                'round_number': self.config['round_number']}
        task = asyncio.create_task(coro())
        task.set_name(json.dumps(data))
        task.add_done_callback(self.callback_handler)

    def _offers_interactions(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        self._current_turn = increment_bot_turn(self.player, config=self.config)

        self.offer_list = OfferList(
            Offer(**offer) for offer in self.player.offers)

        assert isinstance(self.player.llm_interactions, list)
        self.interaction_list = InteractionList(self.player.llm_interactions)
        self.interaction_list.add_user_message(self.user_message)
        self.player.llm_interactions = self.interaction_list

    def _llm_provider_name(self) -> str:
        provider = _normalize_llm_provider(self.config.get('llm_provider'))
        return provider or 'openrouter'

    def _last_human_offer(self) -> Offer | None:
        for offer in reversed(self.offer_list):
            if offer.idx != -1 and offer.is_complete:
                return offer
        return None

    async def _run_initial(self):
        self._loop_trigger = 'initial'
        await self._run_loop("Start the negotiation with an opening message.")

    async def _run_chat(self):
        self._loop_trigger = 'chat'
        await self._run_loop(self.user_message)

    async def _run_offer(self):
        self._loop_trigger = 'offer'
        await self._run_loop(self.user_message)

    async def _run_loop(self, trigger: str, messages: list = None) -> list:
        """Core tool-calling loop."""
        player, _ = self.get_player_participant()
        if messages is None:
            system_prompt = agent_system_final_prompts(self.config)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(
                {
                    "role": "assistant" if m["role"] == "system" else "user",
                    "content": m["content"],
                }
                for m in (self.interaction_list or [])
            )
            if not messages or messages[-1]["role"] != "user":
                messages.append({
                    "role": "user",
                    "content": self.user_message or trigger,
                })
        else:
            messages.append({"role": "user", "content": trigger})
        action_taken = False

        for step in range(7):
            self._current_step = step
            print(f"  [loop step {step}] calling LLM...")
            try:
                response = await self.get_llm_response_with_tools(messages, TOOLS)
            except LLMTransportError as exc:
                msg = f'LLM transport error after retries — abandoning round: {exc!r}'
                print(f"  [loop step {step}] {msg}")
                self.add_debug_log(msg)
                log_llm_call(
                    player,
                    config=self.config,
                    turn=self._current_turn,
                    step=step,
                    trigger=self._loop_trigger,
                    provider=self._llm_provider_name(),
                    model=self.config.get('llm_model', ''),
                    temperature=self.config.get('llm_temp'),
                    messages_sent=messages,
                    assistant_content='',
                    tool_name='',
                    tool_arguments={},
                    tool_result='',
                    error=repr(exc),
                )
                self.send_asyncio_data({'finished': True})
                return messages

            raw_tool_calls = response.choices[0].message.tool_calls or []
            assistant_content = response.choices[0].message.content or ''
            tool_calls = [
                {
                    "id": tc.id,
                    "type": getattr(tc, "type", None) or "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in raw_tool_calls
            ]

            if len(tool_calls) > 1:
                dropped = ', '.join(
                    tc["function"]["name"] for tc in tool_calls[1:])
                print(f"  [loop step {step}] dropped parallel tool calls: {dropped}")
                self.add_debug_log(f"Dropped parallel tool calls: {dropped}")
                tool_calls = tool_calls[:1]

            if not tool_calls:
                log_llm_call(
                    player,
                    config=self.config,
                    turn=self._current_turn,
                    step=step,
                    trigger=self._loop_trigger,
                    provider=self._llm_provider_name(),
                    model=self.config.get('llm_model', ''),
                    temperature=self.config.get('llm_temp'),
                    messages_sent=messages,
                    assistant_content=assistant_content,
                    tool_name='',
                    tool_arguments={},
                    tool_result='',
                    no_tool_call=True,
                )
                messages.append({
                    "role": "user",
                    "content": "You must respond by calling a tool. Plain text is not allowed."
                })
                continue

            assistant_message = {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            for tool_call in tool_calls:
                tool_id = tool_call["id"]
                tool_name = tool_call["function"]["name"]
                arguments = tool_call["function"]["arguments"]
                self._current_call_id = tool_id

                try:
                    parsed_args = json.loads(arguments) if isinstance(arguments, str) else arguments
                except json.JSONDecodeError:
                    parsed_args = {}

                result = await self._dispatch(tool_name, arguments)

                log_llm_call(
                    player,
                    config=self.config,
                    turn=self._current_turn,
                    step=step,
                    trigger=self._loop_trigger,
                    provider=self._llm_provider_name(),
                    model=self.config.get('llm_model', ''),
                    temperature=self.config.get('llm_temp'),
                    messages_sent=messages[:-1],
                    assistant_content=assistant_content,
                    tool_name=tool_name,
                    tool_arguments=parsed_args,
                    tool_result=str(result) if result is not None else '',
                    unknown_tool=tool_name not in KNOWN_TOOL_NAMES,
                )

                if tool_name not in ACTION_TOOLS:
                    print(f"  [loop step {step}] tool result for '{tool_name}': {result}")
                    messages.append({"role": "tool", "tool_call_id": tool_id, "content": str(result)})
                    break

                print(f"  [loop step {step}] action tool '{tool_name}' called — loop break")
                action_taken = True
                break

            if action_taken:
                break

        if not action_taken:
            text = 'I need a moment to think'
            print(f"  [loop] max steps reached without action — fallback")
            set_bot_response(player, self._current_turn, 'fallback', config=self.config)
            self.store_send_data(llm_output=text)

        return messages

    async def _dispatch(self, tool_name: str, arguments: str) -> dict | None:
        log_function(__class__, sys._getframe().f_code.co_name)

        table = {
            "send_chat": self._handle_send_chat,
            "propose_offer": self._handle_propose_offer,
            "send_offer": self._handle_send_offer,
            "accept_offer": self._handle_accept_offer,
            "evaluate_offer": self._handle_evaluate_offer,
            "compute_nash": self._handle_compute_nash,
            "evaluate_single": self._handle_evaluate_single
        }

        if tool_name not in table:
            self.add_debug_log(f"Unknown tool called by LLM: {tool_name}")
            self.store_send_data(llm_output="I need a moment to think.")
            return

        return await table[tool_name](arguments)

    def _include_profitable_in_evaluation(self) -> bool:
        return self.config.get('agentic_evaluation_help', False)

    async def _handle_evaluate_offer(self, arguments: str) -> dict:
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        price = arguments.get('price')
        quantity = arguments.get('quantity')

        if price is None or quantity is None:
            last_offer = self.offer_list[-1]
            price = last_offer['price']
            quantity = last_offer['quantity']

        result = numeric_offer_evaluation(
            price, quantity, self.role,
            self.constraint_user, self.constraint_bot,
            include_profitable=self._include_profitable_in_evaluation(),
        )
        player, _ = self.get_player_participant()
        set_bot_response(player, self._current_turn, 'evaluate', config=self.config)
        return result

    async def _handle_evaluate_single(self, arguments: str) -> dict:
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        price = arguments.get('price')
        quantity = arguments.get('quantity')
        offer = Offer(price=price, quantity=quantity)

        params = {
            'bot_is_supplier': self.bot_is_supplier,
            'nash_profit': nash_bargaining_solution(
                self.constraint_user, self.constraint_bot)['profit'],
            'production_cost': min([self.constraint_user, self.constraint_bot]),
            'market_price': max([self.constraint_user, self.constraint_bot]),
        }

        if price is None:
            return {f'Is quantity {quantity} feasible?': offer._is_quantity_feasible(params=params)}
        return {f'Is price {price} feasible?': offer._is_price_feasible(params=params)}

    async def _handle_compute_nash(self, arguments: str) -> dict:
        log_function(__class__, sys._getframe().f_code.co_name)
        return nash_bargaining_solution(self.constraint_user, self.constraint_bot)

    async def _handle_send_chat(self, arguments: str) -> None:
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        message = arguments.get('message')
        player, _ = self.get_player_participant()
        set_bot_response(player, self._current_turn, 'chat', config=self.config)
        self.store_send_data(llm_output=message)

    async def _handle_propose_offer(self, arguments: str) -> dict:
        """Draft three offers and evaluate them. Does NOT send to the interface."""
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        pending_offers = []
        evaluations = []

        for i in range(1, 4):
            price = arguments.get(f'price_{i}')
            quantity = arguments.get(f'quantity_{i}')
            pending_offer = Offer(price=price, quantity=quantity)
            setattr(self, f'_pending_offer{i}', pending_offer)
            pending_offers.append(pending_offer)

            evaluation = numeric_offer_evaluation(
                price, quantity, self.role,
                self.constraint_user, self.constraint_bot,
                include_profitable=self._include_profitable_in_evaluation(),
            )
            evaluations.append(evaluation)

        player, _ = self.get_player_participant()
        self._propose_call_id = self._current_call_id
        log_drafts(
            player,
            self._propose_call_id,
            self._current_turn,
            self._current_step,
            pending_offers,
            evaluations,
            bot_role=self.role,
            config=self.config,
        )

        output = "\n".join(
            f'Proposed Offer {i + 1} evaluation: {evaluations[i]}'
            for i in range(3)
        )
        return output

    async def _handle_send_offer(self, arguments: str) -> None:
        """Send the pending offer to the interface."""
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        offer_number = arguments.get('offer_number')
        message = arguments.get('message')
        player, _ = self.get_player_participant()

        pending = getattr(self, f'_pending_offer{offer_number}', None)
        if pending is None:
            mark_chosen(player, self._propose_call_id, offer_number, sent=False,
                        config=self.config)
            self.store_send_data(llm_output="I need a moment to think.")
            return

        self.add_profits(pending)
        mark_chosen(player, self._propose_call_id, offer_number, sent=True,
                    config=self.config)
        log_offer_event(
            player, pending,
            sender='bot', origin='tool',
            turn=self._current_turn, bot_response='counter_offer',
            bot_role=self.role,
            config=self.config,
        )
        self.offer_list.append(pending)
        set_bot_response(player, self._current_turn, 'counter_offer', config=self.config)
        self.store_send_data(llm_output=message)

        for i in range(1, 4):
            setattr(self, f'_pending_offer{i}', None)

    async def _handle_accept_offer(self, arguments: str) -> None:
        log_function(__class__, sys._getframe().f_code.co_name)
        if arguments:
            json.loads(arguments)

        human_offer = self._last_human_offer()
        if human_offer is None:
            await self._handle_send_chat(json.dumps({
                'message': "I didn't receive a complete offer to accept yet."
            }))
            return

        price = human_offer.price
        quantity = human_offer.quantity

        player, participant = self.get_player_participant()
        player.process_accept(price, quantity, accepted_by='bot')
        set_bot_response(player, self._current_turn, 'accept', config=self.config)
        self.send_asyncio_data({'finished': True})
