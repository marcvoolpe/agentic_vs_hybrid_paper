import random
import sys
from functools import cached_property
from typing import Any, Union

from otree.api import *

from common import JsonField, RoleUtils, employee_retailer_profit, \
    employee_supplier_profit, ROOM_CONFIGS, CLASS_DICT
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
        assert config['room'] in range(-1, 13)
        if config['room'] in range(1, 13):
            room = ROOM_CONFIGS[config['room']]
            assert room['first'] in (C.ROLE_SUPPLIER_EMPLOYEE,
                                     C.ROLE_RETAILER_EMPLOYEE)
            assert room['product_class'] in CLASS_DICT.keys()


def creating_session(sub_session: Subsession):
    sub_session.session.initialize()
    sub_session.initialize_subsession()


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
        # Retrieve the selected class from session.vars (set by intro app)
        group_class_data = self.subsession.session.vars. \
            get('group_classes', {}).get(self.id_in_subsession)

        if group_class_data:
            class_name = group_class_data['class_name']
            class_params = group_class_data['class_params']
        else:
            # Only for development
            assert 'intro' not in self.session.config['app_sequence']
            from agentic_vs_hybrid.intro.models import Subsession as IntroSubsession
            available_classes = get_active_classes(self.session.config)
            class_dict = IntroSubsession.select_random_class(available_classes)
            class_name = class_dict['class_name']
            class_params = class_dict['class_params']
            group_classes = self.session.vars['group_classes'] = {}
            group_classes[self.id_in_subsession] = class_dict

            self.retailer_choice = random.choice([C.HUMAN_SENIOR, C.AI_JUNIOR])
            self.supplier_choice = random.choice([C.HUMAN_SENIOR, C.AI_JUNIOR])
            self.get_players()[0].participant.choice = self.retailer_choice
            self.get_players()[1].participant.choice = self.supplier_choice

        self.class_name = class_name
        self.market_price = class_params['market_price']
        self.production_cost = class_params['production_cost']
        self.demand = random.randint(demand_min, demand_max)

        while ('offer' not in self.optimal_offer.keys() or
               'profit' not in self.optimal_offer.keys()):
            self.optimal_offer = nash_bargaining_solution(self.market_price,
                                                          self.production_cost)

        for player in self.get_players():
            player._role = C.ROLES[player.id_in_group - 1]
            player.participant.role = player.role

    def set_opponents(self):
        retailer_manager = self.get_player_by_role(C.ROLE_RETAILER_MANAGER)
        supplier_manager = self.get_player_by_role(C.ROLE_SUPPLIER_MANAGER)
        retailer_employee = self.get_player_by_role(C.ROLE_RETAILER_EMPLOYEE)
        supplier_employee = self.get_player_by_role(C.ROLE_SUPPLIER_EMPLOYEE)

        self.retailer_choice = retailer_manager.participant.choice
        self.supplier_choice = supplier_manager.participant.choice

        is_baseline = self.session.config['baseline'] == True
        if is_baseline or self.both_human_or_senior():
            # Only Human-Human if both managers chose Human (or baseline)
            retailer_employee.other_id = supplier_employee.id_in_group
            supplier_employee.other_id = retailer_employee.id_in_group
            retailer_employee.is_active = supplier_employee.is_active = True
        elif self.both_ai_or_junior():
            # Both managers chose AI, nothing to do for anyone
            pass
        else:
            # If manager chose AI for the employee: negotiate with bot
            retailer_employee.is_active = (self.retailer_choice == C.AI_JUNIOR)
            supplier_employee.is_active = (self.supplier_choice == C.AI_JUNIOR)

    def set_payoff(self):
        retailer_employee = self.get_player_by_role(C.ROLE_RETAILER_EMPLOYEE)
        supplier_employee = self.get_player_by_role(C.ROLE_SUPPLIER_EMPLOYEE)
        retailer_manager = self.get_player_by_role(C.ROLE_RETAILER_MANAGER)
        supplier_manager = self.get_player_by_role(C.ROLE_SUPPLIER_MANAGER)

        # Both managers chose AI -> use Nash equilibrium
        if retailer_employee.is_active == supplier_employee.is_active == False:
            nash_price, nash_quantity = self.optimal_offer['offer']
            retailer_employee.price_accepted = nash_price
            retailer_employee.quantity_accepted = nash_quantity
            supplier_employee.price_accepted = nash_price
            supplier_employee.quantity_accepted = nash_quantity

        # Employees
        for employee in [retailer_employee, supplier_employee]:
            price_accepted = employee.field_maybe_none('price_accepted')
            quantity_accepted = employee.field_maybe_none('quantity_accepted')
            if price_accepted is not None and quantity_accepted is not None:
                employee.set_profit_payoff()

        # Managers: set payoff if their employee has a deal
        if retailer_employee.field_maybe_none('price_accepted') is not None and retailer_employee.field_maybe_none('quantity_accepted') is not None:
            retailer_manager.set_profit_payoff()
        if supplier_employee.field_maybe_none('price_accepted') is not None and supplier_employee.field_maybe_none('quantity_accepted') is not None:
            supplier_manager.set_profit_payoff()


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

    def process_offer(self, price: int, quantity: int) -> list[dict[str, int]]:
        log_function(__class__, sys._getframe().f_code.co_name)

        """ Offer made via the interface """
        assert isinstance(self.offers, list)
        self.price_proposed = price
        self.quantity_proposed = quantity

        offer_user = Offer(idx=self.id_in_group, price=price, quantity=quantity)
        self.offers = self.offers + [offer_user]
        if not self.bot_opponent:
            self.other.offers = self.other.offers + [offer_user]
        else:
            self.other.receive_offer_from_human(price, quantity)

        return self.offers

    def process_accept(self, price: int, quantity: int):
        log_function(__class__, sys._getframe().f_code.co_name)
        print(f"[DEBUG] process_accept: self={self.role}, price={price}, quantity={quantity}, bot_opponent={self.bot_opponent}")

        """ User accepts the opposing offer """
        # Human - Human negotiation
        if not self.bot_opponent:
            assert price == self.other.price_proposed
            assert quantity == self.other.quantity_proposed
            self.time_end = self.other.time_end = now_datetime()
            self.price_accepted = self.other.price_accepted = price
            self.quantity_accepted = self.other.quantity_accepted = quantity
            print(f"[DEBUG] process_accept (human): self={self.role}, price_accepted={self.price_accepted}, quantity_accepted={self.quantity_accepted}, other={self.other.role}, other_price_accepted={self.other.price_accepted}, other_quantity_accepted={self.other.quantity_accepted}")
        else:
            self.time_end = now_datetime()
            self.price_accepted = price
            self.quantity_accepted = quantity
            # Defensive: only set idle_player if it exists
            if hasattr(self, 'idle_player') and self.idle_player is not None:
                self.idle_player.price_accepted = price
                self.idle_player.quantity_accepted = quantity
                print(f"[DEBUG] process_accept (bot): idle_player={self.idle_player.role}, price_accepted={self.idle_player.price_accepted}, quantity_accepted={self.idle_player.quantity_accepted}")
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

        # Realized demand and parameters (common knowledge)
        demand = int(self.group.demand or 0)
        market_price = float(self.group.market_price)
        production_cost = float(self.group.production_cost)

        quantity_sold = min(quantity, demand)
        quantity_unsold = max(0, quantity - demand)

        if self.role == C.ROLE_RETAILER_EMPLOYEE:
            return employee_retailer_profit(market_price, price, quantity_sold)
        else:
            return employee_supplier_profit(price, production_cost,
                                            quantity_sold, quantity_unsold)

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
