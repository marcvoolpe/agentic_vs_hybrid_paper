import asyncio
import copy
import sys

from .bot_base import InteractionList
from .bot_llm import BotLLM
from .bot_strategy import BotStrategy
from .bot_task import BotTask
from .constants import C
from .offer import Offer, OfferList
from .prompts import HYBRID_PROMPTS
from .utils import log_function


class NegotiationBot(BotStrategy, BotTask):
    def __init__(self, player: 'Player'):
        super().__init__()
        self.id_in_group = -1
        self.player = player
        self.role = player.opposite_role

        # Async functions loose self.player, copy what is needed
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

    @property
    def proposal(self) -> str:
        if not self.offer_list:
            return '(none)<br> '
        last_offer = self.offer_list[-1]
        return f"€ {last_offer['price']}<br>{last_offer['quantity']}"

    @staticmethod
    def field_maybe_none(_: str) -> None:
        return None

    def start_initial(self): 
        #browser sends an 'initial' event (data['type'] == 'initial?)
        #then the bot sends the first opening message 
        log_function(__class__, sys._getframe().f_code.co_name)

        if self.player.field_maybe_none("llm_interactions") is None:#guard against double initialization
            #only send the opening if there hasnt been llm interactions (actual start)
            self.player.llm_interactions = []
            self._offers_interactions()
            self.initial()

    def receive_chat_from_human(self, user_message: str):
        log_function(__class__, sys._getframe().f_code.co_name)

        # Received via the chat
        self.user_message = user_message
        self._offers_interactions()
        # TODO Should be asyncio.create_task(coro) ?
        asyncio.ensure_future(self.start_task(self.follow_up))


    def receive_offer_from_human(self, price: int, quantity: int):
        log_function(__class__, sys._getframe().f_code.co_name)

        # Received via the interface
        self.user_message = HYBRID_PROMPTS['offer_string'] % (price, quantity)
        self._offers_interactions()
        asyncio.ensure_future(self.start_task(self.interface_offer))

    def _offers_interactions(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        # Create offer list, new offer not added yet
        self.offer_list = OfferList(
            Offer(**offer) for offer in self.player.offers)
        # Create interactions list, add user message if needed
        assert isinstance(self.player.llm_interactions, list)
        self.interaction_list = InteractionList(self.player.llm_interactions)
        self.interaction_list.add_user_message(self.user_message)
        self.player.llm_interactions = self.interaction_list
