import asyncio
import re
import logging
from typing import Any

import httpx
import spacy
from ollama import AsyncClient, ChatResponse
from otree.channels import utils as channel_utils
from otree.database import db

from .optimal import nash_bargaining_solution
from .offer import Offer
from .prompts import HYBRID_PROMPTS, hybrid_system_final_prompt
from .utils import log_debug, log_interpret

NLP = spacy.load("en_core_web_sm")
PATTERN_OFFER = re.compile(r'\[([^]]+)]')

_VALID_LLM_PROVIDERS = frozenset({'cerebras', 'openrouter'})
_LOG = logging.getLogger(__name__)


def _normalize_llm_provider(raw) -> str | None:
    """Return canonical provider name, or None if missing/invalid."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in _VALID_LLM_PROVIDERS:
        return s
    return None


class _AttrDict(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as err:
            raise AttributeError(item) from err


def _to_attrdict(value):
    if isinstance(value, dict):
        return _AttrDict({k: _to_attrdict(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_to_attrdict(v) for v in value]
    return value


class BotLLM:
    def __init__(self):
        self.get_player_participant = None
        self.role = None
        self.interaction_list = None
        self.offer_list = None
        self.client = None
        self.config = None
        self.role = None
        self.constraint_bot = None
        self.constraint_user = None

        raise RuntimeError #not meant to be instantiated on its own
        #provides methods but asumes another class supplies the state those
        #methods need (self.client, self.config etc)

    def send_asyncio_data(self, data: dict[str, Any]):
        asyncio.create_task(channel_utils.group_send(
            group=self.config['group_name'], data=data))

    def store_send_data(self,
                        llm_output: str = None,
                        bot_vars: dict[str, Any] = None):
        player, participant = self.get_player_participant()

        # Store bot_vars if updated
        if bot_vars:
            player.bot_vars = {**player.bot_vars, **bot_vars}

        # Store and send LLM output
        if llm_output:
            data = player.process_llm_output(self.role, llm_output)
            self.send_asyncio_data(data)
            self.interaction_list.add_bot_message(llm_output)

        # Store and send interactions
        if self.interaction_list:
            player.llm_interactions = self.interaction_list
            self.send_asyncio_data({'interactions': self.interaction_list})

        # Store and send offers
        if self.offer_list:
            player.offers = self.offer_list
            self.send_asyncio_data({'offers': self.offer_list})

        db.commit()

    @staticmethod
    def extract_content(response: ChatResponse) -> str:
        def remove_inner(string: str, start_char: str, end_char: str):
            while start_char in string and end_char in string:
                start_pos = string.find(start_char)
                end_pos = string.find(end_char, start_pos) + 1
                if 0 <= start_pos < end_pos:
                    string = string[:start_pos] + string[end_pos:]
                else:
                    break
            return string

        def clean_leading_non_alphanum(s: str) -> str:
            # Remove all leading characters that are not a-z, A-Z, or 0-9
            return re.sub(r'^[^a-zA-Z0-9]+', '', s)

        try:
            content: str = response['message']['content'].strip()
        except KeyError as _:
            log_debug(f"Unexpected response format: {response}")
            return f"\nUnexpected response format: {response}\n"

        # Extract text within the quotes if quotes are found
        if content.count('"') > 1:
            start = content.find('"') + 1
            end = content.rfind('"')
            # Prevent cases in which user introduces parameters inside ""
            if len(content[start:end]) > 30:
                content = content[start:end]
        else:
            # Remove 'System" starts
            if content.lower().startswith("system:"):
                content = content[7:].strip()
            if content.lower().startswith("system,"):
                content = content[7:].strip()

        # Remove text within parentheses if no quotes are found
        content = remove_inner(content, '(', ')')

        # Remove text before "optimal_offer"
        if 'optimal_offer' in content:
            split_list = content.split('optimal_offer', 1)
            content = split_list[1].strip() if len(split_list) > 1 else content

        # Remove text before the first colon
        s = 0
        while ':' in content and s != 3:
            split_list = content.split(':', 1)
            content = split_list[1].strip() if len(split_list) > 1 else content
            s += 1

        # Remove internal thoughts
        s = 0
        while 'Here is the most efficient offer' in content and s != 3:
            split_list = content.split('Here is the most efficient offer', 1)
            content = split_list[1].strip() if len(split_list) > 1 else content
            s += 1

        s = 0
        while 'response' in content and s != 3:
            split_list = content.split('response', 1)
            content = split_list[1].strip() if len(split_list) > 1 else content
            s += 1

        # Cleaning text from leading non-alphanumeric characters
        content = clean_leading_non_alphanum(content)
        # Split the content at line breaks and take only the first part
        content = content.split('\n', 1)[0]
        content = content.strip().strip('"')

        return content

    ############################################################################
    # Methods that use the LLMs
    ############################################################################
    def _is_agentic_session(self) -> bool:
        return bool(self.config.get('full_agent', False))

    def _ensure_client(self):
        if self.client is None:
            if not self._is_agentic_session():
                logging.getLogger("httpx").level = logging.WARNING
                auth = httpx.BasicAuth(username=self.config['llm_user'],
                                       password=self.config['llm_pass'])
                self.client = AsyncClient(host=self.config['llm_host'],
                                          auth=auth)
                return

            raw_provider = self.config.get('llm_provider')
            provider = _normalize_llm_provider(raw_provider)
            if provider is None:
                if raw_provider in (None, ''):
                    _LOG.warning(
                        'llm_provider missing in session config; defaulting to '
                        '"openrouter". Set llm_provider in settings or session config.'
                    )
                else:
                    _LOG.warning(
                        'Invalid llm_provider %r; defaulting to "openrouter". '
                        'Use "openrouter" or "cerebras".',
                        raw_provider,
                    )
                provider = 'openrouter'

            api_key = (self.config.get('llm_api_key') or '').strip()
            if not api_key:
                # Backward-compatible fallback (deprecated; see experiment/secret.py).
                from . import secret
                if provider == 'cerebras':
                    api_key = (getattr(secret, 'CEREBRAS_API_KEY', None) or '').strip()
                else:
                    api_key = (getattr(secret, 'OPEN_ROUTER_API_KEY', None) or '').strip()

            if not api_key:
                env_hint = (
                    'CEREBRAS_API_KEY or LLM_API_KEY'
                    if provider == 'cerebras'
                    else 'OPENROUTER_API_KEY, OPEN_ROUTER_API_KEY, or LLM_API_KEY'
                )
                raise RuntimeError(
                    f"Missing API key for llm_provider={provider!r}. "
                    f"Set session config llm_api_key or environment variable {env_hint}."
                )

            if provider == 'openrouter':
                from .open_router import OpenRouterClient
                self.client = OpenRouterClient(api_key)
                return

            from cerebras.cloud.sdk import Cerebras
            self.client = Cerebras(api_key=api_key)

    async def get_llm_response(self, content: str) -> ChatResponse:
        self._ensure_client()

        assert isinstance(content, str)
        system_prompt = hybrid_system_final_prompt(self.config)
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}]

        if not self._is_agentic_session():
            response = await self.client.chat(
                model=self.config['llm_model'],
                options={'temperature': self.config['llm_temp']},
                messages=messages)
            if isinstance(response, dict):
                return _to_attrdict(response)
            return response

        response = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.config['llm_model'],
            messages=messages,
            temperature=self.config['llm_temp'],
        )
        content = response.choices[0].message.content or ''
        return _to_attrdict({'message': {'content': content}})
    
    async def get_llm_response_with_tools(self, messages: list, tools: list):
        if not self._is_agentic_session():
            raise RuntimeError(
                "Tool calling is only supported for agentic (full_agent) sessions.")
        self._ensure_client()

        # asyncio.to_thread runs the blocking Cerebras SDK call in a
        # background thread — keeps the event loop free while LLM thinks
        return await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.config['llm_model'],
            messages=messages,
            tools=tools,
            temperature=self.config['llm_temp'],
        )

    async def interpret_offer(self, message: str, idx: int = None) -> Offer:
        doc = NLP(message)
        parts = [t.lemma_ for t in doc if t.pos_ in ('NUM', 'NOUN')]
        numbers = [self.get_float(p) for p in parts
                   if self.get_float(p) is not None]

        price = quantity = None
        if len(numbers) == 1:
            pass
        elif len(numbers) == 2:
            price, quantity = numbers[0], int(numbers[1])
        elif len(numbers) == 3:
            price, quantity = numbers[0], int(numbers[2])

        if None not in (price, quantity):
            log_interpret(message, "SPACY", price, quantity)
            return Offer(idx=idx, from_chat=True, price=price,
                         quantity=quantity)

        return await self._interpret_offer_llm(message, idx)

    async def _interpret_offer_llm(self, message: str,
                                   idx: int = None) -> Offer:
        # Defaults to User Offer
        if idx is None:
            idx = self.config['idx']

        if re.search(r'\d', message):
            # If a message contains at least one number -> let LLM interpret
            messages = [{'role': 'user',
                         'content': HYBRID_PROMPTS['understanding_offer'] + message}]
            self._ensure_client()
            response = await self.client.chat(
                model=self.config['llm_reader'],
                messages=messages)
            llm_output = response['message']['content']
        else:
            # Otherwise, output an empty offer [,] directly
            llm_output = '[,]'
        log_debug('[DEBUG Bot_llm.interpret_offer]', llm_output)

        # Regular expression to find the pattern [Price, Quantity]
        price = quantity = None
        match_list = list(PATTERN_OFFER.finditer(llm_output))
        for match in reversed(match_list):
            parts = [part.replace('<', '').replace('>', '').strip()
                     for part in match.group(1).split(',')]

            price, quantity = self.extract_price_quantity_1(parts)
            if price is not None and quantity is not None:
                break

            price, quantity = self.extract_price_quantity_2(parts)
            if price is not None and quantity is not None:
                break

        log_interpret(message, llm_output, price, quantity)

        return Offer(idx=idx, from_chat=True, price=price, quantity=quantity)

    def extract_price_quantity_1(self, parts: list[str]) \
            -> tuple[float | None, int | None]:
        # Handle closed range scenarios ex. Interpreter LLM Output = [None, 60-85]
        # TODO In extract_price_quantity_2 we use item 0 and 2 if we have 3
        #  Why do we assume only 2 here?
        for index, part in enumerate(parts):
            if '-' in part:
                nash_result = nash_bargaining_solution(self.constraint_user,
                                                       self.constraint_bot)
                nash_price, nash_quantity = nash_result['offer']

                # TODO This is wrong, it only tests price OR quantity
                #  Or do we assume one None and one range?
                bits = part.split('-')
                if index == 0:
                    low, high = float(bits[0]), float(bits[1])
                    if low <= nash_price <= high:
                        return nash_price, nash_quantity
                if index == 1:
                    low, high = int(bits[0]), int(bits[1])
                    if low <= nash_quantity <= high:
                        return nash_price, nash_quantity

        return None, None

    @classmethod
    def extract_price_quantity_2(cls, parts: list[str]) \
            -> tuple[float | None, int | None]:
        floats = [cls.get_float(part.replace('€', '')) for part in parts]

        if len(floats) == 1:
            pass
        elif len(floats) == 2:
            return floats[0], int(floats[1]) if floats[1] is not None else None
        elif len(floats) == 3:
            if floats[0] is not None and floats[2] is not None:
                return floats[0], int(floats[2])
            elif floats[0] is not None and floats[1:] == [None, None]:
                return floats[0], None
            elif floats[:2] == [None, None] and floats[2] is not None:
                return None, int(floats[2])

        return None, None

    @staticmethod
    def get_float(p: str) -> float | None:
        try:
            p = "".join(s for s in p if s.isdigit() or s == '.')
            return round(float(p), 2)
        except ValueError:
            pass
