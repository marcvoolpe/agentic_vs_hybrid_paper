import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

from .agentic_negotiation import FullAgentBot
from .constants import C

player = MagicMock()
player.opposite_role = C.ROLE_SUPPLIER_EMPLOYEE
player.id_in_group = 2
player.participant.code = 'test_code'
player.session.code = 'test_session'
player.round_number = 1
player.role = C.ROLE_RETAILER_EMPLOYEE
player.group.production_cost = 2
player.group.market_price = 10
player.group.demand = 50
player.bot_vars = {}
player.offers = []
player.llm_interactions = []
player.field_maybe_none.return_value = None
player.session.config = {
    'llm_model': 'llama3',
    'llm_temp': 0.7,
    'llm_user': 'your_user',
    'llm_pass': 'your_pass',
    'llm_host': 'http://localhost:11434',
}

bot = FullAgentBot(player)
asyncio.run(bot._run_loop("Start the negotiation."))