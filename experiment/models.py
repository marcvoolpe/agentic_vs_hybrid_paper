import random
import sys
from functools import cached_property
from typing import Any, Union

from otree.api import *

from common import JsonField, RoleUtils, ROOM_CONFIGS, AGENT_ROOM_CONFIGS, \
    CLASS_DICT, get_room_config, normalize_room_id
from settings import get_active_classes

from .bot_negotiation import NegotiationBot
from .agentic_negotiation import FullAgentBot

from .constants import C
from .offer import Offer
from .optimal import nash_bargaining_solution, OPTIMAL_OFFER
from .utils import log_debug, now_datetime, log_function


class Subsession(BaseSubsession):
    def initialize_subsession(self):
        config = self.session.config
        self._check_config(config)

        for group in self.get_groups():
            group.initialize_group(config['demand_min'], config['demand_max'])

    def _check_config(self, config: dict[str, Any]):
        assert config['market_price_high'] > config['market_price_low']
        assert config['production_cost_high'] > config['production_cost_low']
        assert config['demand_max'] > config['demand_min']
        room_id = normalize_room_id(config['room'])
        assert room_id == -1 or room_id in ROOM_CONFIGS or room_id in AGENT_ROOM_CONFIGS
        if room_id != -1:
            room = get_room_config(room_id)
            assert room['first'] in (
                C.ROLE_SUPPLIER_EMPLOYEE,
                C.ROLE_RETAILER_EMPLOYEE,
            )
            assert room['product_class'] in CLASS_DICT.keys()


def creating_session(sub_session: Subsession):
    sub_session.session.initialize()
    sub_session.initialize_subsession()


def before_next_round(sub_session: Subsession):
    config = sub_session.session.config
    for group in sub_session.get_groups():
        group.initialize_group(config['demand_min'], config['demand_max'])
        group.set_opponents()
        for player in group.get_players():
            player.participant.vars['first'] = True


class Group(BaseGroup):
    retailer_choice = models.StringField(
        choices=[[C.HUMAN_SENIOR, C.AGENT_HUMAN], [C.AI_JUNIOR, C.AGENT_AI]],
        widget=widgets.RadioSelect,
        label="Your delegation decision:",
        max_length=2
    )
    supplier_choice = models.StringField(
        choices=[[C.HUMAN_SENIOR, C.AGENT_HUMAN], [C.AI_JUNIOR, C.AGENT_AI]],
        widget=widgets.RadioSelect,
        label="Your delegation decision:",
        max_length=2
    )
    market_price = models.IntegerField()
    production_cost = models.IntegerField()
    demand = models.IntegerField()
    optimal_offer = JsonField(initial={})
    class_name = models.StringField()
    target_profit = models.FloatField()
    human_expected_profit = models.FloatField()
    bot_expected_profit = models.FloatField()

    def both_human_or_senior(self) -> bool:
        return self.retailer_choice == self.supplier_choice == C.HUMAN_SENIOR

    def both_ai_or_junior(self) -> bool:
        return self.retailer_choice == self.supplier_choice == C.AI_JUNIOR

    @property
    def formatted_optimal_offer(self) -> str:
        formatted_optimal_offer = self.optimal_offer
        price, quantity = formatted_optimal_offer['offer']
        profit = formatted_optimal_offer['profit']
        formatted_optimal_offer = OPTIMAL_OFFER % (price, quantity, profit)
        return formatted_optimal_offer

    def initialize_group(self, demand_min: int, demand_max: int):
        room_id = normalize_room_id(self.session.config['room'])
        room = get_room_config(room_id)

        if room:
            class_name = room['product_class']
            class_params = CLASS_DICT[class_name]
            session_config = dict(self.session.config)
            session_config['baseline'] = room.get(
                'baseline', session_config['baseline']
            )
            if 'full_agent' in room:
                session_config['full_agent'] = room['full_agent']
            if 'agentic_evaluation_help' in room:
                session_config['agentic_evaluation_help'] = room[
                    'agentic_evaluation_help']
            session_config['room'] = room_id
            self.session.config = session_config
            human_role = room['first']
        else:
            available_classes = get_active_classes(self.session.config)
            class_name = random.choice(list(available_classes.keys()))
            class_params = available_classes[class_name]
            # Default to retailer when no room is configured.
            human_role = C.ROLE_RETAILER_EMPLOYEE

        group_classes = self.session.vars.setdefault('group_classes', {})
        group_classes[self.id_in_subsession] = {
            'class_name': class_name,
            'class_params': class_params,
        }

        self.class_name = class_name
        self.market_price = class_params['market_price']
        self.production_cost = class_params['production_cost']
        self.demand = random.randint(demand_min, demand_max)

        while ('offer' not in self.optimal_offer.keys() or
               'profit' not in self.optimal_offer.keys()):
            self.optimal_offer = nash_bargaining_solution(self.market_price,
                                                          self.production_cost)

        player = self.get_player_by_id(1)
        player._role = human_role
        player.participant.role = player.role
        # Keep participant.choice populated for downstream payoff logic.
        player.participant.choice = C.AI_JUNIOR

    def set_opponents(self):
        player = self.get_player_by_id(1)
        player.other_id = -1
        player.is_active = True

    def record_deal_expected_profits(self, human_player: 'Player'):
        price = human_player.price_accepted
        quantity = human_player.quantity_accepted
        offer = Offer(price=price, quantity=quantity)
        bot_role = (C.ROLE_SUPPLIER_EMPLOYEE if human_player.is_retailer
                    else C.ROLE_RETAILER_EMPLOYEE)
        from .telemetry import profit_constraints

        constraint_user, constraint_bot = profit_constraints(
            bot_role, self.market_price, self.production_cost,
        )
        offer.profits(bot_role, constraint_user, constraint_bot)
        self.target_profit = self.optimal_offer['profit']
        self.human_expected_profit = offer.profit_user
        self.bot_expected_profit = offer.profit_bot

    def set_payoff(self):
        player = self.get_player_by_id(1)
        self.target_profit = self.optimal_offer['profit']
        price_accepted = player.field_maybe_none('price_accepted')
        quantity_accepted = player.field_maybe_none('quantity_accepted')
        if price_accepted is not None and quantity_accepted is not None:
            self.record_deal_expected_profits(player)
            player.set_profit_payoff()


class Player(BasePlayer, RoleUtils):
    # -1 means Bot opponent
    other_id = models.IntegerField(initial=-1)
    # Only for employees that participate in negotiations
    is_active = models.BooleanField(initial=False)

    price_proposed = models.FloatField()
    price_accepted = models.FloatField()
    quantity_proposed = models.IntegerField()
    quantity_accepted = models.IntegerField()
    profit = models.FloatField(initial=0)

    # Add these fields for managers to store cost breakdown
    transaction_cost = models.FloatField(initial=0)
    base_cost = models.FloatField(initial=0)
    bonus_delegee = models.FloatField(initial=0)
    delegation_cost = models.FloatField(initial=0)
    company_profit = models.FloatField(initial=0)

    offers = JsonField(initial=[])
    chat_data = JsonField(initial=[])
    llm_interactions = JsonField()
    bot_vars = JsonField(initial={})

    time_start = models.StringField(max_length=20)
    time_end = models.StringField(max_length=20)

    turn_counter = models.IntegerField(initial=0)
    accepted_by = models.StringField(blank=True)
    deal = models.BooleanField(initial=False)

    @cached_property
    def other(self) -> Union['Player', NegotiationBot, FullAgentBot]:
        if self.other_id == -1:
            if self.session.config.get('full_agent', False):
                return FullAgentBot(self)
            return NegotiationBot(self)
        return self.group.get_players()[self.opposite_id - 1]

    @property
    def bot_opponent(self) -> bool:
        return self.other_id == -1

    @property
    def other_is_ai_agent_or_human(self) -> str:
        return "AI Agent" if self.bot_opponent else "Human"

    @property
    def proposal(self) -> str:
        price = self.field_maybe_none('price_proposed')
        quantity = self.field_maybe_none('quantity_proposed')
        if None not in (price, quantity):
            return f"€ {price}<br>{quantity}"
        return '(none)<br> '

    @property
    def live_ids(self) -> list[int]:
        return [idx for idx in [self.id_in_group, self.other_id] if idx > 0]

    def process_offer(
            self, price: int, quantity: int, body: str | None = None,
    ) -> list[dict[str, int]]:
        log_function(__class__, sys._getframe().f_code.co_name)

        """ Offer made via the interface """
        from .telemetry import current_turn, log_offer_event

        assert isinstance(self.offers, list)
        self.price_proposed = price
        self.quantity_proposed = quantity

        offer_user = Offer(idx=self.id_in_group, price=price, quantity=quantity)
        log_offer_event(
            self, offer_user, sender='human', origin='interface',
            turn=current_turn(self),
        )
        self.offers = self.offers + [offer_user]
        if body:
            assert isinstance(self.chat_data, list)
            self.chat_data = self.chat_data + [
                {'nick': f"{self.role} (Me)", 'body': body}]
        if not self.bot_opponent:
            self.other.offers = self.other.offers + [offer_user]
        else:
            self.other.receive_offer_from_human(price, quantity, body=body)

        return self.offers

    def process_accept(self, price: int, quantity: int, accepted_by: str = 'human'):
        log_function(__class__, sys._getframe().f_code.co_name)
        from .telemetry import mark_accepted

        print(f"[DEBUG] process_accept: self={self.role}, price={price}, quantity={quantity}, bot_opponent={self.bot_opponent}")

        """ User accepts the opposing offer """
        # Human - Human negotiation
        if not self.bot_opponent:
            assert price == self.other.price_proposed
            assert quantity == self.other.quantity_proposed
            self.time_end = self.other.time_end = now_datetime()
            self.price_accepted = self.other.price_accepted = price
            self.quantity_accepted = self.other.quantity_accepted = quantity
            mark_accepted(self, price, quantity, accepted_by)
            print(f"[DEBUG] process_accept (human): self={self.role}, price_accepted={self.price_accepted}, quantity_accepted={self.quantity_accepted}, other={self.other.role}, other_price_accepted={self.other.price_accepted}, other_quantity_accepted={self.other.quantity_accepted}")
        else:
            self.time_end = now_datetime()
            self.price_accepted = price
            self.quantity_accepted = quantity
            mark_accepted(self, price, quantity, accepted_by)
            print(f"[DEBUG] process_accept (bot): self={self.role}, price_accepted={self.price_accepted}, quantity_accepted={self.quantity_accepted}")

    def process_chat(self, data: dict[str, Any]) -> dict[int, Any]:
        log_function(__class__, sys._getframe().f_code.co_name)

        """ Process a chat message from the user """
        assert isinstance(self.chat_data, list)
        body = data['body']

        tmp = self.chat_data + [{'nick': f"{self.role} (Me)", 'body': body}]
        self.chat_data = tmp
        result = {self.id_in_group: {'chat': self.chat_data}}

        if not self.bot_opponent:
            tmp = self.other.chat_data + [{'nick': self.role, 'body': body}]
            self.other.chat_data = tmp
            result[self.other.id_in_group] = {'chat': self.other.chat_data}
        else:
            self.other.receive_chat_from_human(body)

        return result

    def process_llm_output(self, role: str, body: str) -> dict[str, Any]:
        log_function(__class__, sys._getframe().f_code.co_name)

        """ Send LLM output to the user """
        assert isinstance(self.chat_data, list)
        tmp = self.chat_data + [{'nick': f"{role}", 'body': body}]
        self.chat_data = tmp
        return {'chat': self.chat_data}

    def calculate_profits_manager(self) -> float:
        log_function(__class__, sys._getframe().f_code.co_name)

        assert self.role in C.ROLES_MANAGEMENT

        employee_profit = self.employee_player.calculate_profits_employee()
        bonus_delegee = max(employee_profit, 0) * 0.02

        if self.participant.choice == C.HUMAN_SENIOR:
            base_cost = self.session.config['delegation_cost_1']
        elif self.participant.choice == C.AI_JUNIOR:
            base_cost = self.session.config['delegation_cost_2']
        else:
            raise NotImplementedError

        transaction_cost = 0
        if self.employee_player.price_accepted is not None:
            transaction_costs = self.session.vars['group_classes'] \
                [self.group.id_in_subsession]['class_params'] \
                ['transaction_costs']
            if self.group.both_human_or_senior():
                transaction_cost = random.choice(transaction_costs)
            else:
                transaction_cost = max(transaction_costs)

        delegation_cost = transaction_cost + base_cost
        company_profit = employee_profit - delegation_cost - bonus_delegee

        # Store the cost breakdown in player fields for display in results
        self.transaction_cost = transaction_cost
        self.base_cost = base_cost
        self.bonus_delegee = bonus_delegee
        self.delegation_cost = delegation_cost
        self.company_profit = company_profit

        return company_profit

    def calculate_profits_employee(self) -> float:
        log_function(__class__, sys._getframe().f_code.co_name)

        assert self.role in C.ROLES_EMPLOYEE

        # Negotiated terms
        price = float(self.price_accepted or 0)
        quantity = int(self.quantity_accepted or 0)

        market_price = int(self.group.market_price)
        production_cost = int(self.group.production_cost)

        if self.role == C.ROLE_RETAILER_EMPLOYEE:
            return Offer.profit_retailer(price, quantity, market_price)
        return Offer.profit_supplier(price, quantity, production_cost)

    def set_profit_payoff(self):
        print(f"[DEBUG] set_profit_payoff: role={self.role}, price_accepted={self.field_maybe_none('price_accepted')}, quantity_accepted={self.field_maybe_none('quantity_accepted')}")
        if self.role in C.ROLES_MANAGEMENT:
            self.profit = self.calculate_profits_manager()
            # manager earns 2.5% of company profit
            self.payoff = Currency(max(self.profit, 0) * 0.025)
        else:
            self.profit = self.calculate_profits_employee()
            # employee earns 2% of deal profit
            self.payoff = Currency(max(self.profit, 0) * 0.02)


class OfferEvent(ExtraModel):
    player = models.Link(Player)
    turn = models.IntegerField()
    stamp = models.FloatField()
    sender = models.StringField()
    origin = models.StringField()
    price = models.FloatField(null=True)
    quantity = models.IntegerField(null=True)
    is_valid = models.BooleanField()
    is_complete = models.BooleanField()
    profit_bot = models.FloatField(null=True)
    profit_user = models.FloatField(null=True)
    nash_profit = models.FloatField()
    nash_price = models.FloatField()
    nash_quantity = models.IntegerField()
    surplus_bot = models.FloatField(null=True)
    surplus_user = models.FloatField(null=True)
    joint_profit = models.FloatField(null=True)
    evaluation = models.StringField(blank=True)
    bot_response = models.StringField(blank=True)
    accepted = models.BooleanField(initial=False)
    accepted_by = models.StringField(blank=True)
    is_mirror = models.BooleanField(initial=False)
    n_generations = models.IntegerField(initial=1)
    session_code = models.StringField()
    participant_code = models.StringField()
    round_number = models.IntegerField()
    room = models.IntegerField()
    arm = models.StringField()
    human_role = models.StringField()
    bot_role = models.StringField()
    market_price = models.IntegerField()
    production_cost = models.IntegerField()
    class_name = models.StringField()
    agentic_evaluation_help = models.BooleanField(initial=False)
    num_rounds = models.IntegerField()


class DraftOffer(ExtraModel):
    player = models.Link(Player)
    turn = models.IntegerField()
    step = models.IntegerField()
    call_id = models.StringField()
    slot = models.IntegerField()
    price = models.FloatField(null=True)
    quantity = models.IntegerField(null=True)
    profit_bot = models.FloatField(null=True)
    profit_user = models.FloatField(null=True)
    nash_profit = models.FloatField()
    nash_price = models.FloatField()
    nash_quantity = models.IntegerField()
    surplus_bot = models.FloatField(null=True)
    surplus_user = models.FloatField(null=True)
    joint_profit = models.FloatField(null=True)
    price_dev_nash = models.FloatField(null=True)
    quantity_dev_nash = models.IntegerField(null=True)
    chosen = models.BooleanField(initial=False)
    sent = models.BooleanField(initial=False)
    session_code = models.StringField()
    participant_code = models.StringField()
    round_number = models.IntegerField()
    room = models.IntegerField()
    arm = models.StringField()
    human_role = models.StringField()
    bot_role = models.StringField()
    market_price = models.IntegerField()
    production_cost = models.IntegerField()
    class_name = models.StringField()
    agentic_evaluation_help = models.BooleanField(initial=False)
    num_rounds = models.IntegerField()


class LLMCall(ExtraModel):
    player = models.Link(Player)
    turn = models.IntegerField()
    step = models.IntegerField()
    trigger = models.StringField(blank=True)
    provider = models.StringField(blank=True)
    model = models.StringField(blank=True)
    temperature = models.FloatField(null=True)
    messages_sent = models.LongStringField(blank=True)
    assistant_content = models.LongStringField(blank=True)
    tool_name = models.StringField(blank=True)
    tool_arguments = models.LongStringField(blank=True)
    tool_result = models.LongStringField(blank=True)
    no_tool_call = models.BooleanField(initial=False)
    unknown_tool = models.BooleanField(initial=False)
    session_code = models.StringField()
    participant_code = models.StringField()
    round_number = models.IntegerField()
    room = models.IntegerField()
    arm = models.StringField()
    human_role = models.StringField()
    bot_role = models.StringField()
    market_price = models.IntegerField()
    production_cost = models.IntegerField()
    class_name = models.StringField()
    agentic_evaluation_help = models.BooleanField(initial=False)
    num_rounds = models.IntegerField()
