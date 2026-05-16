from functools import cached_property

from otree.database import db
from otree.models import Participant, Session

from .constants import C, Config
from .offer import Offer, OfferList

import sys
from .utils import log_function


class InteractionList(list):
    def add_user_message(self, user_message: str | None):
        if user_message:
            self.append({"role": "user", "content": user_message})

    def add_bot_message(self, user_message: str| None):
        if user_message:
            self.append({"role": "system", "content": user_message})


class BotBase:
    def __init__(self):
        self.client = None
        self.config: Config | None = None
        self.role: str | None = None
        self.user_message: str | None = None
        self.offer_user: Offer | None = None
        self.interaction_list: InteractionList | None = None
        self.offer_list: OfferList | None = None
        self.optimal_offer_str = None

        # The Player must be able to set these, but they will be ignored
        self.price_proposed = None
        self.price_accepted = None
        self.offers = None
        self.time_end = None

    @staticmethod
    def group_name(player: 'Player') -> str:
        return C.GROUP_NAME % (player.group.session.code,
                               player.participant._index_in_pages,
                               player.participant.code)

    @cached_property
    def constraint_user(self) -> int:
        if self.role == C.ROLE_RETAILER_EMPLOYEE:
            return self.config['production_cost']
        else:
            return self.config['market_price']

    @cached_property
    def constraint_bot(self) -> int:
        if self.role == C.ROLE_SUPPLIER_EMPLOYEE:
            return self.config['production_cost']
        else:
            return self.config['market_price']

    @property
    def bot_is_supplier(self) -> bool:
        if self.role == C.ROLE_SUPPLIER_EMPLOYEE:
            return True
        elif self.role == C.ROLE_RETAILER_EMPLOYEE:
            return False
        raise NotImplementedError

    @property
    def proposal(self) -> str:
        if not self.offer_list:
            return '(none)<br> '
        last_offer = self.offer_list[-1]
        return f"â‚¬ {last_offer['price']}<br>{last_offer['quantity']}"

    def add_profits(self, offer: Offer):
        offer.profits(self.role, self.constraint_user, self.constraint_bot)

    def get_session(self) -> Session:
        return db.query(Session) \
            .filter_by(code=self.config['session_code']).one()

    def get_player_participant(self) -> tuple['Player', Participant]:
        participant = db.query(
            Participant).filter_by(code=self.config['code']).one()
        return participant._get_current_player(), participant

    def add_debug_log(self, message: str):
        try:
            debug_log = self.get_session().debug_log
            debug_log[self.config['round_number']].append(message)
            db.commit()
        except Exception as e:
            return

