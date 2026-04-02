from typing import Any

from common import RoleConstants
from cerebras.cloud.sdk import Cerebras
from .secret import API_KEY

Config = dict[str, int | str | bool | dict[str, Any]]

class C(RoleConstants):
    NAME_IN_URL = 'experiment'
    PLAYERS_PER_GROUP = 4
    NUM_ROUNDS = 1

    GROUP_NAME = "live-%s-%s-%s"

    LLM_ERROR = 'No Connection to LLM server'

client = Cerebras(
    api_key=API_KEY
)