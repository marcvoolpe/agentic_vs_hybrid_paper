"""Persist negotiation telemetry to ExtraModel tables at decision time."""

from __future__ import annotations

import json
import time
from typing import Any

from otree.database import db
from otree.models import Participant

from .constants import C
from .offer import Offer, Evaluation
from .optimal import nash_bargaining_solution
from common import normalize_room_id


def _bound_player(participant_code: str) -> 'Player':
    participant = db.query(Participant).filter_by(code=participant_code).one()
    return participant._get_current_player()


def _context_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """Build denormalized context from bot config snapshot (async-safe)."""
    nash = config.get('optimal_offer') or nash_bargaining_solution(
        config['market_price'], config['production_cost']
    )
    nash_price, nash_quantity = nash['offer']
    roles = config.get('roles', {})
    full_agent = bool(config.get('full_agent', False))
    room_raw = config.get('room', -1)
    try:
        room = int(normalize_room_id(room_raw))
    except (TypeError, ValueError):
        room = -1
    return {
        'session_code': config['session_code'],
        'participant_code': config['code'],
        'round_number': config['round_number'],
        'room': room,
        'arm': 'agentic' if full_agent else 'hybrid',
        'human_role': roles.get('human_role', ''),
        'bot_role': roles.get('bot_role', ''),
        'market_price': config['market_price'],
        'production_cost': config['production_cost'],
        'class_name': config.get('class_name', ''),
        'nash_profit': float(nash['profit']),
        'nash_price': float(nash_price),
        'nash_quantity': int(nash_quantity),
        'agentic_evaluation_help': bool(config.get('agentic_evaluation_help', False)),
        'num_rounds': config.get('num_rounds', 1),
    }


def _player_context(player: 'Player') -> dict[str, Any]:
    """Denormalized session/round context for sync live_method calls."""
    config = player.session.config
    nash = player.group.optimal_offer or nash_bargaining_solution(
        player.group.market_price, player.group.production_cost
    )
    nash_price, nash_quantity = nash['offer']
    full_agent = bool(config.get('full_agent', False))
    room_raw = config.get('room', -1)
    try:
        room = int(normalize_room_id(room_raw))
    except (TypeError, ValueError):
        room = -1
    return {
        'session_code': player.session.code,
        'participant_code': player.participant.code,
        'round_number': player.round_number,
        'room': room,
        'arm': 'agentic' if full_agent else 'hybrid',
        'human_role': player.role,
        'bot_role': player.opposite_role,
        'market_price': player.group.market_price,
        'production_cost': player.group.production_cost,
        'class_name': player.group.class_name,
        'nash_profit': float(nash['profit']),
        'nash_price': float(nash_price),
        'nash_quantity': int(nash_quantity),
        'agentic_evaluation_help': bool(config.get('agentic_evaluation_help', False)),
        'num_rounds': config.get('num_rounds', 1),
    }


def _resolve(player: 'Player', config: dict[str, Any] | None) -> tuple['Player', dict[str, Any]]:
    """Return a DB-bound player and context dict safe for async bot tasks."""
    if config is not None:
        return _bound_player(config['code']), _context_from_config(config)
    return player, _player_context(player)


def profit_constraints(
    bot_role: str,
    market_price: int,
    production_cost: int,
) -> tuple[int, int]:
    """Mirror BotBase.constraint_user / constraint_bot for Offer.profits()."""
    if bot_role == C.ROLE_RETAILER_EMPLOYEE:
        return production_cost, market_price
    if bot_role == C.ROLE_SUPPLIER_EMPLOYEE:
        return market_price, production_cost
    raise ValueError(f'Unknown bot role: {bot_role}')


def _offer_metrics(
    ctx: dict[str, Any],
    offer: Offer,
    bot_role: str | None = None,
) -> dict[str, Any]:
    bot_role = bot_role or ctx['bot_role']
    constraint_user, constraint_bot = profit_constraints(
        bot_role, ctx['market_price'], ctx['production_cost'],
    )
    offer.profits(bot_role, constraint_user, constraint_bot)
    nash_profit = ctx['nash_profit']
    profit_bot = offer.profit_bot if offer.profit_bot is not None else 0.0
    profit_user = offer.profit_user if offer.profit_user is not None else 0.0
    surplus_bot = round(profit_bot - nash_profit, 2) if offer.is_valid else None
    surplus_user = round(profit_user - nash_profit, 2) if offer.is_valid else None
    joint = (profit_bot + profit_user) if offer.is_valid else None
    return {
        **ctx,
        'price': offer.price,
        'quantity': offer.quantity,
        'is_valid': offer.is_valid,
        'is_complete': offer.is_complete,
        'profit_bot': profit_bot,
        'profit_user': profit_user,
        'surplus_bot': surplus_bot,
        'surplus_user': surplus_user,
        'joint_profit': joint,
        'price_dev_nash': (round(offer.price - ctx['nash_price'], 2)
                           if offer.price is not None else None),
        'quantity_dev_nash': (offer.quantity - ctx['nash_quantity']
                              if offer.quantity is not None else None),
    }


def current_turn(player: 'Player', config: dict[str, Any] | None = None) -> int:
    if config is not None:
        return _bound_player(config['code']).field_maybe_none('turn_counter') or 0
    return player.field_maybe_none('turn_counter') or 0


def increment_bot_turn(
    player: 'Player' | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> int:
    bound, _ = _resolve(player, config) if config else (player, {})
    bound.turn_counter = current_turn(bound) + 1
    db.commit()
    return bound.turn_counter


def log_offer_event(
    player: 'Player',
    offer: Offer,
    *,
    sender: str,
    origin: str,
    turn: int | None = None,
    evaluation: Evaluation | str | None = None,
    bot_response: str = '',
    is_mirror: bool = False,
    n_generations: int = 1,
    bot_role: str | None = None,
    config: dict[str, Any] | None = None,
) -> 'OfferEvent':
    from .models import OfferEvent

    bound, ctx = _resolve(player, config)
    metrics = _offer_metrics(ctx, offer, bot_role=bot_role)
    eval_value = evaluation.value if isinstance(evaluation, Evaluation) else (evaluation or '')
    row = OfferEvent.create(
        player=bound,
        turn=turn if turn is not None else current_turn(bound),
        stamp=offer.stamp or time.time(),
        sender=sender,
        origin=origin,
        price=metrics['price'],
        quantity=metrics['quantity'],
        is_valid=metrics['is_valid'],
        is_complete=metrics['is_complete'],
        profit_bot=metrics['profit_bot'],
        profit_user=metrics['profit_user'],
        nash_profit=metrics['nash_profit'],
        nash_price=metrics['nash_price'],
        nash_quantity=metrics['nash_quantity'],
        surplus_bot=metrics['surplus_bot'],
        surplus_user=metrics['surplus_user'],
        joint_profit=metrics['joint_profit'],
        evaluation=eval_value,
        bot_response=bot_response or '',
        accepted=False,
        accepted_by='',
        is_mirror=is_mirror,
        n_generations=n_generations,
        session_code=metrics['session_code'],
        participant_code=metrics['participant_code'],
        round_number=metrics['round_number'],
        room=metrics['room'],
        arm=metrics['arm'],
        human_role=metrics['human_role'],
        bot_role=metrics['bot_role'],
        market_price=metrics['market_price'],
        production_cost=metrics['production_cost'],
        class_name=metrics['class_name'],
        agentic_evaluation_help=metrics['agentic_evaluation_help'],
        num_rounds=metrics['num_rounds'],
    )
    db.commit()
    return row


def log_drafts(
    player: 'Player',
    call_id: str,
    turn: int,
    step: int,
    offers: list[Offer],
    evaluations: list[dict[str, Any]],
    bot_role: str | None = None,
    config: dict[str, Any] | None = None,
) -> list:
    from .models import DraftOffer

    bound, ctx = _resolve(player, config)
    rows = []
    for slot, (offer, _evaluation) in enumerate(zip(offers, evaluations), start=1):
        metrics = _offer_metrics(ctx, offer, bot_role=bot_role)
        row = DraftOffer.create(
            player=bound,
            turn=turn,
            step=step,
            call_id=call_id or f'turn{turn}-step{step}',
            slot=slot,
            price=metrics['price'],
            quantity=metrics['quantity'],
            profit_bot=metrics['profit_bot'],
            profit_user=metrics['profit_user'],
            nash_profit=metrics['nash_profit'],
            nash_price=metrics['nash_price'],
            nash_quantity=metrics['nash_quantity'],
            surplus_bot=metrics['surplus_bot'],
            surplus_user=metrics['surplus_user'],
            joint_profit=metrics['joint_profit'],
            price_dev_nash=metrics['price_dev_nash'],
            quantity_dev_nash=metrics['quantity_dev_nash'],
            chosen=False,
            sent=False,
            session_code=ctx['session_code'],
            participant_code=ctx['participant_code'],
            round_number=ctx['round_number'],
            room=ctx['room'],
            arm=ctx['arm'],
            human_role=ctx['human_role'],
            bot_role=ctx['bot_role'],
            market_price=ctx['market_price'],
            production_cost=ctx['production_cost'],
            class_name=ctx['class_name'],
            agentic_evaluation_help=ctx['agentic_evaluation_help'],
            num_rounds=ctx['num_rounds'],
        )
        rows.append(row)
    db.commit()
    return rows


def mark_chosen(
    player: 'Player',
    call_id: str,
    slot: int,
    sent: bool,
    config: dict[str, Any] | None = None,
) -> None:
    from .models import DraftOffer

    bound, _ = _resolve(player, config)
    for draft in DraftOffer.filter(player=bound):
        if draft.call_id == call_id and draft.slot == slot:
            draft.chosen = True
            draft.sent = sent
    db.commit()


def mark_accepted(
    player: 'Player',
    price: float,
    quantity: int,
    accepted_by: str,
    config: dict[str, Any] | None = None,
) -> None:
    from .models import OfferEvent

    bound, _ = _resolve(player, config)
    sender = 'human' if accepted_by == 'bot' else 'bot'
    candidates = [
        ev for ev in OfferEvent.filter(player=bound)
        if ev.sender == sender and not ev.accepted
        and ev.price == price and ev.quantity == quantity
    ]
    if not candidates:
        candidates = [
            ev for ev in OfferEvent.filter(player=bound)
            if ev.sender == sender and not ev.accepted
        ]
    if candidates:
        ev = max(candidates, key=lambda row: row.stamp)
        ev.accepted = True
        ev.accepted_by = accepted_by
        if accepted_by == 'bot':
            ev.bot_response = 'accept'
    bound.deal = True
    bound.accepted_by = accepted_by
    db.commit()


def set_bot_response(
    player: 'Player',
    turn: int,
    response: str,
    evaluation: Evaluation | str | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    from .models import OfferEvent

    bound, _ = _resolve(player, config)
    eval_value = evaluation.value if isinstance(evaluation, Evaluation) else evaluation
    candidates = [
        ev for ev in OfferEvent.filter(player=bound)
        if ev.sender == 'human' and ev.turn == turn
    ]
    if not candidates:
        candidates = [
            ev for ev in OfferEvent.filter(player=bound)
            if ev.sender == 'human'
        ]
    if candidates:
        ev = max(candidates, key=lambda row: row.stamp)
        ev.bot_response = response
        if eval_value:
            ev.evaluation = eval_value
        db.commit()


def log_llm_call(
    player: 'Player',
    *,
    config: dict[str, Any] | None = None,
    **kwargs,
) -> None:
    from .models import LLMCall

    bound, ctx = _resolve(player, config)
    messages = kwargs.pop('messages_sent', None)
    tool_arguments = kwargs.pop('tool_arguments', None)
    LLMCall.create(
        player=bound,
        session_code=ctx['session_code'],
        participant_code=ctx['participant_code'],
        round_number=ctx['round_number'],
        room=ctx['room'],
        arm=ctx['arm'],
        human_role=ctx['human_role'],
        bot_role=ctx['bot_role'],
        market_price=ctx['market_price'],
        production_cost=ctx['production_cost'],
        class_name=ctx['class_name'],
        agentic_evaluation_help=ctx['agentic_evaluation_help'],
        num_rounds=ctx['num_rounds'],
        messages_sent=json.dumps(messages) if messages is not None else '',
        tool_arguments=json.dumps(tool_arguments) if tool_arguments is not None else '',
        **kwargs,
    )
    db.commit()
