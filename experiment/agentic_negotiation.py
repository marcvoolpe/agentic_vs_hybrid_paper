import copy
import asyncio
import sys
import json

from ollama import ChatResponse


from .bot_base import BotBase, InteractionList
from .bot_llm import BotLLM
from .bot_task import BotTask
from .prompts import HYBRID_PROMPTS, agent_system_final_prompts
from .offer import Offer, OfferList
from .optimal import nash_bargaining_solution
from .utils import log_function
from .bot_tools import numeric_offer_evaluation, TOOLS, ACTION_TOOLS




class FullAgentBot(BotBase, BotLLM, BotTask):
    def __init__(self, player: 'Player'):
        super().__init__()
        self.id_in_group = -1
        self.player = player
        self.role = player.opposite_role

        # Async functions loose self.player, copy what is needed
        self._pending_offer = None
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

            'bot_vars': player.bot_vars,
        })

    def start_initial(self):
        if self.player.field_maybe_none('llm_interactions') is None:

            self.player.llm_interactions = []
            self._offers_interactions()
            asyncio.ensure_future(self.start_task(self._run_initial))
            #asyncio use to call an async / await function
            #always use when functions call external services (llm, browser etc)
            #since it allows running the program (not freezing)
            #while waiting for the external service response / answer

    def receive_chat_from_human(self, user_message:str):
        self.user_message = user_message
        self._offers_interactions()
        asyncio.ensure_future(self.start_task(self._run_chat))

    def receive_offer_from_human(self, price: int, quantity: int):
        self.user_message = HYBRID_PROMPTS['offer_string'] % (price, quantity)
        self._offers_interactions()
        asyncio.ensure_future(self.start_task(self._run_offer))


    async def _run_initial(self):
        await self._run_loop("Start the negotiation with an opening message.")

    async def _run_chat(self):
        await self._run_loop(self.user_message)

    async def _run_offer(self):
        await self._run_loop(self.user_message)

    async def _run_loop(self, trigger: str, messages: list = None) -> list:
        """Core tool-calling loop. trigger is 'initial', 'chat', or 'offer'.
        Pass messages to continue an existing conversation; omit to start fresh.
        Returns the updated messages list so callers can continue the conversation."""
        if messages is None:
            system_prompt = agent_system_final_prompts(self.config)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self.user_message or trigger},
            ]
        else:
            messages.append({"role": "user", "content": trigger})
        action_taken = False

        for step in range(7):
            print(f"  [loop step {step}] calling LLM...")
            response = await self.get_llm_response_with_tools(messages, TOOLS)

            tool_calls = response.choices[0].message.tool_calls or []

            if not tool_calls:
                messages.append({
                    "role": "user",
                    "content": "You must respond by calling a tool. Plain text is not allowed."
                })
                continue

            assistant_message = {
                "role": "assistant",
                "content": response.choices[0].message.content,
                "tool_calls": response.choices[0].message.tool_calls
            }
            messages.append(assistant_message)

            for obj_tool_call in tool_calls:

                tool_call = {
                    'id': obj_tool_call.id,
                    'name': obj_tool_call.function.name,
                    'arguments': obj_tool_call.function.arguments
                }

                tool_id = tool_call['id']
                tool_name = tool_call['name']
                arguments = tool_call['arguments']

                result = await self._dispatch(tool_name, arguments)

                if tool_name not in ACTION_TOOLS:
                    print(f"  [loop step {step}] tool result for '{tool_name}': {result}")
                    messages.append({"role": "tool", "tool_call_id": tool_id, "content": str(result)})
                    # action_taken = True
                    break

                else:
                    print(f"  [loop step {step}] action tool '{tool_name}' called — loop break")
                    action_taken = True
                    break

            if action_taken:
                break

        if not action_taken:
            text = 'I need a moment to think'
            print(f"  [loop] max steps reached without action — fallback")
            self.store_send_data(llm_output=text)

        return messages




    def _offers_interactions(self):
        # TODO: move to BotBase - shared with NegotiationBot
        log_function(__class__, sys._getframe().f_code.co_name)

        # Create offer list, new offer not added yet
        self.offer_list = OfferList(
            Offer(**offer) for offer in self.player.offers)
        # Create interactions list, add user message if needed
        assert isinstance(self.player.llm_interactions, list)
        self.interaction_list = InteractionList(self.player.llm_interactions)
        self.interaction_list.add_user_message(self.user_message)
        self.player.llm_interactions = self.interaction_list
    
    async def _dispatch(self, tool_name: str, arguments: dict) -> dict | None:
        log_function(__class__, sys._getframe().f_code.co_name)

        # Dispatch table — maps tool names to handler methods
        table = {
            "send_chat": self._handle_send_chat,
            "propose_offer": self._handle_propose_offer,
            "send_offer": self._handle_send_offer,
            "accept_offer": self._handle_accept_offer,
            "evaluate_offer": self._handle_evaluate_offer,
            "compute_nash": self._handle_compute_nash,
        }

        if tool_name not in table:
            # Log hallucinated tool — this is research data, not just an error
            self.add_debug_log(f"Unknown tool called by LLM: {tool_name}")
            self.store_send_data(llm_output="I need a moment to think.")
            return

        return await table[tool_name](arguments)

    async def _handle_evaluate_offer(self, arguments: str) -> dict:
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments) # arguments are json string -> convert to dict

        price = arguments.get('price')
        quantity = arguments.get('quantity')

        if price is None or quantity is None:
            last_offer = self.offer_list[-1]
            price = last_offer['price']
            quantity = last_offer['quantity']

        return numeric_offer_evaluation(price, quantity, self.role,
                                        self.constraint_user, self.constraint_bot)
    
    async def _handle_compute_nash(self, arguments: str) -> dict: # arguments is always empty here
        log_function(__class__, sys._getframe().f_code.co_name)

        return nash_bargaining_solution(self.constraint_user, self.constraint_bot)
    
    async def _handle_send_chat(self, arguments: str) -> None:
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        message = arguments.get('message')
        self.store_send_data(llm_output=message)

    async def _handle_propose_offer(self, arguments: str) -> dict:
        """Draft an offer and evaluate it. Does NOT send to the interface."""
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        price = arguments.get('price')
        quantity = arguments.get('quantity')

        self._pending_offer = Offer(price=price, quantity=quantity)

        evaluation = numeric_offer_evaluation(
            price, quantity, self.role,
            self.constraint_user, self.constraint_bot)

        return evaluation

    async def _handle_send_offer(self, arguments: str) -> None:
        """Send the pending offer to the interface."""
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        if self._pending_offer is None:
            self.store_send_data(llm_output="I need a moment to think.")
            return

        self.offer_list.append(self._pending_offer)
        self.store_send_data()
        self._pending_offer = None

    async def _handle_accept_offer(self, arguments: str) -> None:
        log_function(__class__, sys._getframe().f_code.co_name)
        arguments = json.loads(arguments)

        last_offer = self.offer_list[-1]
        price = last_offer['price']
        quantity = last_offer['quantity']

        # player, participant = self.get_player_participant()
        # player.process_accept(price, quantity)
        # self.send_asyncio_data({'finished': True})
