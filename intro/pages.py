import inspect
import json
import random
from typing import Any

from otree.api import *
from otree.database import db, AUTO_SUBMIT_DEFAULTS

from common import employee_retailer_profit, employee_supplier_profit
from .comprehension import get_employee_error_message, \
    EMPLOYEE_RETAILER_PROFIT, EMPLOYEE_SUPPLIER_PROFIT, MANAGER_QUESTIONS, \
    get_manager_error_message
from .constants import C
from .models import Player, Group


def get_numbers(config: dict[str, Any]) -> dict[str, str]:
    def get_str(start, end) -> str:
        tmp = ", ".join(str(x) for x in range(start, end))
        return f"{tmp}{' or ' if tmp else ''}{end}"

    market_price = get_str(config['market_price_low'],
                           config['market_price_high'])
    production_costs = get_str(config['production_cost_low'],
                               config['production_cost_high'])
    demand = f"[{config['demand_min']}, {config['demand_max']}]"

    return {
        'market_price': market_price,
        'production_costs': production_costs,
        'demand': demand,
    }


class Instructions(Page):
    @staticmethod
    def is_displayed(player: Player) -> bool:
        return not player.is_management

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        config = player.session.config
        timeout = config['timeout_experiment'] // 60
        result = {
            'agent_1': C.get_agent_1(player.session),
            'agent_2': C.get_agent_2(player.session),
            'contact': C.get_agent_1(player.session).split(' ')[0].lower(),
            'timeout': timeout
        }
        result.update(**get_numbers(config))
        return result


class InstructionsManager(Page):
    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_management

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        # TODO The content of the Table is hardcoded, should come from settings
        config = player.session.config
        result = {
            'agent_1': C.get_agent_1(player.session),
            'agent_2': C.get_agent_2(player.session),
            'contact': C.get_agent_1(player.session).split(' ')[0].lower(),
        }
        result.update(**get_numbers(config))
        return result


class ComprehensionCheck1(Page):
    form_model = 'player'
    form_fields = ['comprehension_check']
    template_name = 'intro/ComprehensionCheck.html'

    QUANTITY_DEMAND = {
        1: (10, 90),
        2: (90, 10),
        3: (50, 50),
        4: (70, 80),
        5: (40, 30),
    }

    @classmethod
    def get_page_idx(cls) -> int:
        return int(cls.__name__[-1])

    @staticmethod
    def is_displayed(player: Player):
        return not player.is_management

    @classmethod
    def vars_for_template(cls, player: Player) -> dict[str, Any]:
        def next_question():
            # Randomize market_price/production_cost and wholesale price
            market_price = random.randint(
                config['market_price_low'], config['market_price_high'])
            production_cost = random.randint(
                config['production_cost_low'],
                config['production_cost_high'])
            price = random.randint(4, 9)

            # Calculate correct profit based on role
            quantity_sold = min(quantity, demand)
            quantity_unsold = max(0, quantity - demand)
            if player.is_retailer:
                profit = employee_retailer_profit(
                    market_price, price, quantity_sold)
            else:
                profit = employee_supplier_profit(
                    price, production_cost, quantity_sold, quantity_unsold)

            return {
                'market_price': market_price,
                'production_cost': production_cost,
                'price': price,
                'quantity': quantity,
                'demand': demand,
                'profit': profit,
            }

        config = player.session.config
        var_dict = player.participant.vars

        page_idx = cls.get_page_idx()
        quantity, demand = cls.QUANTITY_DEMAND[page_idx]

        assert config['demand_min'] <= demand <= config['demand_max']
        assert quantity >= 0

        # Generate new values if first time on this question or after error
        if page_idx not in var_dict.keys():
            var_dict[page_idx] = next_question()

        return {
            'market_price': var_dict[page_idx]['market_price'],
            'production_cost': var_dict[page_idx]['production_cost'],
            'price': var_dict[page_idx]['price'],
            'quantity': var_dict[page_idx]['quantity'],
            'demand': var_dict[page_idx]['demand'],
            'question_number': page_idx,
            'total_questions': 5,
        }

    @classmethod
    def error_message(cls, player: Player, values) -> str | None:
        """Validate comprehension check answer"""
        var_dict = player.participant.vars

        page_idx = cls.get_page_idx()
        comprehension_attempts = json.loads(player.comprehension_attempts)
        page_attempts = comprehension_attempts[str(page_idx)]

        answer = values['comprehension_check']
        correct = var_dict[page_idx]['profit']

        # Store answer
        comprehension_answer = json.loads(player.comprehension_answer)
        comprehension_answer[str(page_idx)].append(answer)
        player.comprehension_answer = json.dumps(comprehension_answer)

        if answer == correct:
            return None

        # Increase the nof attempts
        comprehension_attempts[str(page_idx)] = page_attempts + 1
        player.comprehension_attempts = json.dumps(comprehension_attempts)

        # Pop question and clear for new generation
        question = var_dict.pop(page_idx)

        market_price = question['market_price']
        price = question['price']
        production_cost = question['production_cost']
        quantity = question['quantity']
        demand = question['demand']
        quantity_sold = min(quantity, demand)
        quantity_unsold = max(0, quantity - demand)

        if player.is_retailer:
            profit_calc = EMPLOYEE_RETAILER_PROFIT % (
                market_price, price, quantity_sold, correct)
        else:
            profit_calc = EMPLOYEE_SUPPLIER_PROFIT % (
                price, production_cost, quantity_sold,
                production_cost, quantity_unsold, correct)

        return get_employee_error_message(player, profit_calc,
                                          market_price, price, production_cost,
                                          quantity, demand)


class ComprehensionCheck2(ComprehensionCheck1):
    pass


class ComprehensionCheck3(ComprehensionCheck1):
    pass


class ComprehensionCheck4(ComprehensionCheck1):
    pass


class ComprehensionCheck5(ComprehensionCheck1):
    pass


class ComprehensionCheckManagerBase(Page):
    """Base class for manager comprehension checks"""
    form_model = 'player'
    form_fields = ['comprehension_answer_a', 'comprehension_answer_b']

    PRODUCTS = ['C', 'A', 'B']

    @classmethod
    def get_page_idx(cls) -> int:
        return int(cls.__name__[-1])

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_management

    @classmethod
    def vars_for_template(cls, player: Player) -> dict[str, Any]:
        page_idx = cls.get_page_idx()
        page_attempts = json.loads(player.comprehension_attempts)[str(page_idx)]
        product_idx = (page_attempts - 1) % 3
        product_class = cls.PRODUCTS[product_idx]
        question = MANAGER_QUESTIONS[page_idx][product_class]

        # print()
        # print('attempt_number         ', page_attempts)
        # print('product_idx            ', product_idx)
        # print('question               ', question)
        # print('product_class          ', product_class)
        # print('product_question_number', product_idx + 1)
        # print('total_product_questions', len(cls.PRODUCTS))

        return {
            'attempt_number': page_attempts,
            'product_question_number': product_idx + 1,
            'total_product_questions': len(cls.PRODUCTS),
            'product_class': product_class,
            'question': question,
            'agent_1': C.get_agent_1(player.session),
            'agent_2': C.get_agent_2(player.session),
        }

    @classmethod
    def error_message(cls, player: Player, values) -> str | None:
        page_idx = cls.get_page_idx()
        comprehension_attempts = json.loads(player.comprehension_attempts)
        page_attempts = comprehension_attempts[str(page_idx)]
        product_idx = (page_attempts - 1) % 3
        product_class = cls.PRODUCTS[product_idx]
        question = MANAGER_QUESTIONS[page_idx][product_class]

        answer_a = float(values.get('comprehension_answer_a') or 0)
        answer_b = float(values.get('comprehension_answer_b') or 0)
        correct_a = float(question['correct_a'])
        correct_b = float(question['correct_b'])

        # Store answer
        comprehension_answer = json.loads(player.comprehension_answer)
        comprehension_answer[str(page_idx)].append((answer_a, answer_b))
        player.comprehension_answer = json.dumps(comprehension_answer)

        # Check if both answers are correct (within 0.01 tolerance)
        if max(abs(answer_a - correct_a), abs(answer_b - correct_b)) < 0.01:
            return None

        # Increase the nof attempts
        comprehension_attempts[str(page_idx)] = page_attempts + 1
        player.comprehension_attempts = json.dumps(comprehension_attempts)

        return get_manager_error_message(page_idx, product_class, question)


class ComprehensionCheckManager1(ComprehensionCheckManagerBase):
    """Exact delegation cost - counterpart human & halved transaction costs"""
    pass


class ComprehensionCheckManager2(ComprehensionCheckManagerBase):
    """Exact delegation cost - counterpart human & full transaction costs"""
    pass


class ComprehensionCheckManager3(ComprehensionCheckManagerBase):
    """Exact delegation cost with counterpart AI"""
    pass


class ComprehensionCheckManager4(ComprehensionCheckManagerBase):
    """Expected delegation costs"""
    pass


class ManagementWaitPage(WaitPage):
    def _get_participants_for_this_waitpage(self, group_or_subsession):
        # We override the Base implementation, no need to wait for the employees
        participants = \
            super()._get_participants_for_this_waitpage(group_or_subsession)
        return [participant for participant in list(participants)
                if participant.role in C.ROLES_MANAGEMENT]

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_management


class FirstMover(Page):
    form_model = 'group'

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_management and player.is_first_mover

    @staticmethod
    def get_form_fields(player: Player) -> list[str]:
        return [f"{player.clean_role.lower()}_choice"]

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        # Get the assigned product class for this group
        group_class_data = \
            player.session.vars['group_classes'][player.group.id_in_subsession]
        product_class = group_class_data['class_name'].split(' ')[1]

        return {
            'agent_1': C.get_agent_1(player.session),
            'agent_2': C.get_agent_2(player.session),
            'option_0': C.HUMAN_SENIOR,
            'option_1': C.AI_JUNIOR,
            'role_lower': player.clean_role.lower(),
            'product_class': product_class,
        }


class SecondMover(Page):
    form_model = 'group'

    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_management and not player.is_first_mover

    @staticmethod
    def get_form_fields(player: Player) -> list[str]:
        return [f"{player.clean_role.lower()}_choice"]

    @staticmethod
    def vars_for_template(player: Player) -> dict[str, Any]:
        agent_1 = C.get_agent_1(player.session)
        agent_2 = C.get_agent_2(player.session)

        if player.role == C.ROLE_RETAILER_MANAGER:
            first_choice = player.group.supplier_choice
        else:
            first_choice = player.group.retailer_choice
        choice_display = agent_1 if first_choice == C.HUMAN_SENIOR else agent_2

        # Get the assigned product class for this group
        group_class_data = \
            player.session.vars['group_classes'][player.group.id_in_subsession]
        product_class = group_class_data['class_name'].split(' ')[1]

        return {
            'choice_display': choice_display,
            'first_choice': first_choice,
            'agent_1': agent_1,
            'agent_2': agent_2,
            'option_0': C.HUMAN_SENIOR,
            'option_1': C.AI_JUNIOR,
            'role_lower': player.clean_role.lower(),
            'product_class': product_class,
        }


class ShowChoice(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.is_management

    @staticmethod
    def vars_for_template(player: Player):
        agent_1 = C.get_agent_1(player.session)
        agent_2 = C.get_agent_2(player.session)

        retailer_choice = player.group.retailer_choice
        supplier_choice = player.group.supplier_choice
        retailer_choice_display = agent_1 if retailer_choice == 'A' else agent_2
        supplier_choice_display = agent_1 if supplier_choice == 'A' else agent_2

        return {
            'retailer_choice': retailer_choice,
            'retailer_choice_display': retailer_choice_display,
            'supplier_choice': supplier_choice,
            'supplier_choice_display': supplier_choice_display,
            'first_mover_role': player.session.first_mover_role,
            'agent_1': agent_1,
            'agent_2': agent_2,
        }

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        group: Group = player.group
        participant = player.participant
        if player.role == C.ROLE_RETAILER_MANAGER:
            participant.choice = group.retailer_choice
        elif player.role == C.ROLE_SUPPLIER_MANAGER:
            participant.choice = group.supplier_choice
        else:
            raise NotImplementedError


page_sequence = [
    # Instructions,
    # InstructionsManager,
    # ComprehensionCheck1,
    # ComprehensionCheck2,
    # ComprehensionCheck3,
    # ComprehensionCheck4,
    # ComprehensionCheck5,
    # ComprehensionCheckManager1,
    # ComprehensionCheckManager2,
    # ComprehensionCheckManager3,
    # ComprehensionCheckManager4,
    FirstMover,
    ManagementWaitPage,
    SecondMover,
    ManagementWaitPage,
    ShowChoice
]
