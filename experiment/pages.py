from typing import Any

from otree.api import *

from common import normalize_room_id
from settings import SIMULATION_ROOM_IDS

from .models import Player, Group
from .optimal import OPTIMAL_OFFER
from .persona_scripts.load_persona import load_p1_supplier_script
from .utils import now_datetime


# RoundSkip carries no experimental content; it only burns through the
# rounds left unused by num_rounds. oTree treats any timeout under 2s as
# already expired, so this just removes dead waiting time.
ROUND_SKIP_TIMEOUT_SECONDS = 0.1


def stop_after_round(player: Player) -> int | None:
    return player.session.vars.get('stop_after_round')


def round_is_active(player: Player) -> bool:
    num_rounds = player.session.config.get('num_rounds', 1)
    stop_after = stop_after_round(player)
    if stop_after is not None:
        # Keep the round the stop was requested in fully active so its
        # ResultsWaitPage still runs set_payoff().
        num_rounds = min(num_rounds, stop_after)
    return player.round_number <= num_rounds


def simulation_session(player: Player) -> bool:
    config = player.session.config
    room_id = normalize_room_id(config.get('room', -1))
    if room_id in SIMULATION_ROOM_IDS:
        return True
    return config.get('num_rounds', 1) > 1


class ExperimentWaitPage(WaitPage):
    @staticmethod
    def is_displayed(player: Player) -> bool:
        return round_is_active(player)

    @staticmethod
    def after_all_players_arrive(group: Group):
        group.set_opponents()


class Experiment(Page):
    @staticmethod
    def is_displayed(player: Player) -> bool:
        return player.is_active and round_is_active(player)

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

        persona_auto = simulation_session(player)
        return {
            'id_in_group': player.id_in_group,
            'bot_opponent': player.bot_opponent,
            'messages': player.chat_data,
            'offers': player.offers,
            'persona_auto': persona_auto,
            'persona_script': load_p1_supplier_script() if persona_auto else [],
            'can_stop_room': persona_auto,
            'stop_requested': stop_after_round(player) is not None,

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

        if data['type'] == 'stop_room':
            # session.vars is read-only as a whole; mutate in place.
            player.session.vars['stop_after_round'] = player.round_number
            return {idx: {'stopping': player.round_number}
                    for idx in player.live_ids}

        if data['type'] == 'chat':
            return player.process_chat(data)

        price = data['price']
        quantity = data['quantity']
        if data['type'] == 'propose':
            offers = player.process_offer(
                price, quantity, body=data.get('body'))
            payload = {'offers': offers, 'chat': player.chat_data}
            return {idx: payload for idx in player.live_ids}
        if data['type'] == 'accept':
            player.process_accept(price, quantity, accepted_by='human')
            return {idx: {'finished': True} for idx in player.live_ids}

        raise NotImplementedError


class RoundSkip(Page):
    @staticmethod
    def is_displayed(player: Player) -> bool:
        return not round_is_active(player)

    @staticmethod
    def get_timeout_seconds(player: Player):
        return ROUND_SKIP_TIMEOUT_SECONDS


class ResultsWaitPage(WaitPage):
    @staticmethod
    def is_displayed(player: Player) -> bool:
        return round_is_active(player)

    @staticmethod
    def after_all_players_arrive(group: Group):
        group.set_payoff()


class Results(Page):
    @staticmethod
    def is_displayed(player: Player) -> bool:
        return round_is_active(player)

    @staticmethod
    def get_timeout_seconds(player: Player):
        if not simulation_session(player):
            return None
        num_rounds = player.session.config.get('num_rounds', 1)
        if player.round_number >= num_rounds:
            return None
        return 3

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
    Results,
    RoundSkip,
]
