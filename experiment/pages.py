from typing import Any

from otree.api import *

from .constants import C
from .models import Player, Group
from .optimal import OPTIMAL_OFFER
from .utils import now_datetime


class ExperimentWaitPage(WaitPage):
    @staticmethod
    def after_all_players_arrive(group: Group):
        group.set_opponents()


class Experiment(Page):
    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_active

    @staticmethod
    def get_timeout_seconds(player: Player) -> int:
        return player.session.config['timeout_experiment']

    @staticmethod
    def get_formatted_optimal_offer(player: Player) -> str:
        formatted_optimal_offer = player.group.optimal_offer
        profit = formatted_optimal_offer['profit']
        price, quantity = formatted_optimal_offer['offer']
        formatted_optimal_offer = OPTIMAL_OFFER % (price, quantity, profit)
        return formatted_optimal_offer

    @staticmethod
    def js_vars(player: Player) -> dict[str, Any]:
        if player.field_maybe_none('time_start') is None:
            player.time_start = now_datetime()

        return {
            'id_in_group': player.id_in_group,
            'bot_opponent': player.bot_opponent,
            'messages': player.chat_data,
            'offers': player.offers,

            # Parameters for Decision Support System
            'market_price': player.group.market_price,
            'production_cost': player.group.production_cost,
            # Dynamic demand calculation parameters
            'demand_min': player.session.config['demand_min'],
            'demand_max': player.session.config['demand_max'],
        }

    @staticmethod
    def live_method(player: Player, data: dict[str, Any]) \
            -> dict[int, dict[str, Any]] | None:
        if data['type'] == 'ping':
            return {}

        if data['type'] == 'initial':
            assert player.bot_opponent
            player.other.start_initial()
            player.participant.vars['first'] = False
            return {}

        if data['type'] == 'chat':
            return player.process_chat(data)

        price = data['price']
        quantity = data['quantity']
        if data['type'] == 'propose':
            offers = player.process_offer(price, quantity)
            return {idx: {'offers': offers} for idx in player.live_ids}
        if data['type'] == 'accept':
            player.process_accept(price, quantity)
            return {idx: {'finished': True} for idx in player.live_ids}

        raise NotImplementedError


class ResultsWaitPage(WaitPage):
    @staticmethod
    def after_all_players_arrive(group: Group):
        group.set_payoff()


class Results(Page):
    @staticmethod
    def get_params(player: Player) -> tuple[str, str, str, str]:
        deal_price, deal_quantity, deal_profits, payoff = "", "", "€ 0", "€ 0"
        if player.field_maybe_none("price_accepted") is not None:
            deal_price = f"{player.price_accepted:.2f}"
            deal_quantity = str(player.quantity_accepted)
            deal_profits = f"{player.profit:.2f}"
            payoff = f"{player.payoff:.2f}"

        return deal_price, deal_quantity, deal_profits, payoff

    @classmethod
    def vars_for_template(cls, player: Player) -> dict[str, Any]:
        if player.is_management:
            # For managers, get the employee's deal information
            employee = player.employee_player
            price, quantity, profit, payoff = cls.get_params(employee)
            
            # Get the other manager to check their choice
            if player.role == C.ROLE_RETAILER_MANAGER:
                other_manager = player.group.get_player_by_role(C.ROLE_SUPPLIER_MANAGER)
            else:
                other_manager = player.group.get_player_by_role(C.ROLE_RETAILER_MANAGER)
            
            # Use the stored values from calculate_profits_manager
            return {
                'formatted_deal_price': price,
                'formatted_deal_quantity': quantity,
                'formatted_profit': profit,  # Employee's deal profit
                'formatted_final_payment': f"{player.payoff:.2f}",
                'transaction_cost': f"{player.transaction_cost:.2f}",
                'base_cost': f"{player.base_cost:.2f}",
                'bonus_delegee': f"{player.bonus_delegee:.2f}",
                'delegation_cost': f"{player.delegation_cost:.2f}",
                'company_profit': f"{player.company_profit:.2f}",
                'other_manager_choice': other_manager.participant.choice,
                'deal_made': employee.price_accepted is not None,
            }
        else:
            # For employees, use their own data
            price, quantity, profit, payoff = cls.get_params(player)
            return {
                'formatted_deal_price': price,
                'formatted_deal_quantity': quantity,
                'formatted_profit': profit,
                'formatted_final_payment': payoff,
            }




page_sequence = [
    ExperimentWaitPage,
    Experiment,

    ResultsWaitPage,
    Results
]
