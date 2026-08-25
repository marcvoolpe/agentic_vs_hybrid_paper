from .constants import *
from .models import *
from .pages import *
from .session_patch import patch_session

patch_session()

doc = """
Your app description
"""


def custom_export(players):
    """Per-app CSV export for telemetry tables (admin Data tab)."""
    yield [
        'table', 'session_code', 'participant_code', 'round_number', 'turn',
        'sender', 'origin', 'price', 'quantity', 'profit_bot', 'profit_user',
        'nash_profit', 'surplus_bot', 'surplus_user', 'joint_profit',
        'evaluation', 'bot_response', 'accepted', 'accepted_by', 'is_mirror',
        'arm', 'human_role', 'bot_role', 'market_price', 'production_cost',
        'class_name',
    ]
    for row in OfferEvent.filter():
        yield [
            'offer_event', row.session_code, row.participant_code,
            row.round_number, row.turn, row.sender, row.origin,
            row.price, row.quantity, row.profit_bot, row.profit_user,
            row.nash_profit, row.surplus_bot, row.surplus_user, row.joint_profit,
            row.evaluation, row.bot_response, row.accepted, row.accepted_by,
            row.is_mirror, row.arm, row.human_role, row.bot_role,
            row.market_price, row.production_cost, row.class_name,
        ]
    for row in DraftOffer.filter():
        yield [
            'draft_offer', row.session_code, row.participant_code,
            row.round_number, row.turn, '', '', row.price, row.quantity,
            row.profit_bot, row.profit_user, row.nash_profit, row.surplus_bot,
            row.surplus_user, row.joint_profit, '', '', row.chosen, '', '',
            row.arm, row.human_role, row.bot_role, row.market_price,
            row.production_cost, row.class_name,
        ]
    for row in LLMCall.filter():
        yield [
            'llm_call', row.session_code, row.participant_code,
            row.round_number, row.turn, '', '', '', '', '', '', '', '', '', '',
            '', row.tool_name, '', '', '', row.arm, row.human_role, row.bot_role,
            row.market_price, row.production_cost, row.class_name,
        ]
