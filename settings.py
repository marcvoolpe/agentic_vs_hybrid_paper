import socket
from os import environ

# --- LLM cloud provider (agentic / full_agent sessions) ---
# Valid values: "openrouter", "cerebras". Override with env LLM_PROVIDER.
_VALID_LLM_PROVIDERS = frozenset({'openrouter', 'cerebras'})


def _default_llm_provider() -> str:
    raw = (environ.get('LLM_PROVIDER', 'cerebras') or 'cerebras').strip().lower()
    if raw in _VALID_LLM_PROVIDERS:
        return raw
    return 'cerebras'


def _secret_api_key(attr: str) -> str:
    try:
        import importlib.util
        from pathlib import Path

        secret_path = Path(__file__).resolve().parent / 'experiment' / 'secret.py'
        spec = importlib.util.spec_from_file_location('_local_secret', secret_path)
        secret_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(secret_mod)
        return (getattr(secret_mod, attr, None) or '').strip()
    except Exception:
        return ''


def _default_llm_api_key(provider: str) -> str:
    """Prefer LLM_API_KEY; otherwise provider-specific env vars or secret.py."""
    key = (environ.get('LLM_API_KEY', '') or '').strip()
    if key:
        return key
    if provider == 'cerebras':
        return (
            (environ.get('CEREBRAS_API_KEY', '') or '').strip()
            or _secret_api_key('CEREBRAS_API_KEY')
        )
    key = (
        (environ.get('OPENROUTER_API_KEY', '') or '').strip()
        or (environ.get('OPEN_ROUTER_API_KEY', '') or '').strip()
    )
    return (
        key
        or _secret_api_key('OPEN_ROUTER_API_KEY')
        or _secret_api_key('KLAUS_OPEN_ROUTER_API_KEY')
    )


_LLM_PROVIDER = _default_llm_provider()

# LLM model presets
gpt_oss = 'gpt-oss-120b'  # Cerebras
cerebras_qwen = 'qwen-3-235b-a22b-instruct-2507'
zai_glm = 'zai-glm-4.7'  # Cerebras
gemma_4_31b = 'gemma-4-31b'  # Cerebras
open_qwen = 'qwen/qwen3-coder:free'
open_nemotron = 'nvidia/nemotron-3-super-120b-a12b:free'
open_gpt_oss = 'openai/gpt-oss-120b:free'
open_deepseek_flash = 'deepseek/deepseek-v4-flash-0731'
open_deepseek_v32 = 'deepseek/deepseek-v3.2'
open_tencent_hy3 = 'tencent/hy3'
open_qwen_vl = 'qwen/qwen3-vl-235b-a22b-instruct'

# OpenRouter Nemotron (previous default). Swap ACTIVE_* to restore it.
OPENROUTER_NEMOTRON_PRESET = dict(
    llm_provider='openrouter',
    llm_model=open_nemotron,
    llm_api_key=_default_llm_api_key('openrouter'),
)

# Active model for agentic sessions
ACTIVE_LLM_PROVIDER = 'openrouter'
ACTIVE_LLM_MODEL = open_tencent_hy3

# Local Ollama models for hybrid sessions (generation + offer parsing)
HYBRID_LLM_MODEL = 'llama3'
HYBRID_LLM_READER = 'offer_reader_v2'

LOCAL_NAMES = ['glendronach', 'awesom-o-4000',
               'Klauss-MacBook-Pro.local', 'Asus-Tuf-Dash-f15', 'mac.home']

RUNTIME_ROOM_ALIASES = [
    (101, 'agentic_retailer_no_help'),
    (102, 'agentic_supplier_no_help'),
    (103, 'agentic_retailer_help'),
    (104, 'agentic_supplier_help'),
    (105, 'hybrid_retailer'),
    (106, 'hybrid_supplier'),
    (107, 'agentic_supplier_bot_no_help'),
    (108, 'hybrid_supplier_bot'),
]

SIMULATION_ROOM_IDS = frozenset({107, 108})


def session_config_for_room(room_id: int, alias: str) -> dict:
    # Keep this free of `common` imports: common → otree.api → settings (circular).
    # Match AGENT_ROOM_CONFIGS: agentic rooms are full_agent; hybrid rooms are not.
    full_agent = alias.startswith('agentic_')
    config = dict(
        name=f"Experiment_{room_id}",
        display_name=f"Experiment {room_id}: {alias.replace('_', ' ').title()}",
        app_sequence=['experiment'],
        num_demo_participants=1,
        room=room_id,
        baseline=False,
        full_agent=full_agent,
        num_rounds=60 if room_id in SIMULATION_ROOM_IDS else 1,
    )
    if full_agent:
        config.update(
            llm_provider=ACTIVE_LLM_PROVIDER,
            llm_model=ACTIVE_LLM_MODEL,
        )
    else:
        config.update(
            llm_model=HYBRID_LLM_MODEL,
            llm_reader=HYBRID_LLM_READER,
        )
    return config


def get_active_classes(config: dict) -> dict[str, dict[str, int]]:
    from common import CLASS_DICT
    return {class_name: params
            for class_name, params in CLASS_DICT.items()
            if config.get(class_name) is True}

SESSION_CONFIGS = [
    dict(
        name='Full_Experiment',
        display_name='Full Experiment',
        app_sequence=['intro', 'experiment'],
        num_demo_participants=4,
        llm_provider=ACTIVE_LLM_PROVIDER,
        llm_model=ACTIVE_LLM_MODEL,
    ),
    dict(
        name='Experiment',
        app_sequence=['experiment'],
        num_demo_participants=1,
        llm_provider=ACTIVE_LLM_PROVIDER,
        llm_model=ACTIVE_LLM_MODEL,
    ),
    dict(
        name='Intro',
        app_sequence=['intro'],
        num_demo_participants=4,
    ),
]

SESSION_CONFIGS += [
    session_config_for_room(room_id, alias)
    for room_id, alias in RUNTIME_ROOM_ALIASES
]

ROOMS = [
    dict(name=alias, display_name=f"{room_id}: {alias.replace('_', ' ').title()}")
    for room_id, alias in RUNTIME_ROOM_ALIASES
]

SESSION_CONFIG_DEFAULTS = {
    'room': -1,

    'full_agent': True,

    'force_retailer_first': False,
    'force_supplier_first': False,
    'baseline': False,

    'agentic_evaluation_help': False,

    'num_rounds': 1,

    'timeout_experiment': 5 * 60,

    # Fixed market price and production cost are only used in test
    # Will be randomized if not set to >= 0
    'market_price': -1,
    'production_cost': -1,

    # For experiment, always randomize the values
    'market_price_low': 10,
    'market_price_high': 12,
    'production_cost_low': 3,
    'production_cost_high': 5,
    'demand_min': 0,
    'demand_max': 100,

    'delegation_cost_1': 20,
    'delegation_cost_2': 10,

    "Class A": True,
    "Class B": True,
    "Class C": True,

    'llm_user': 'otree',
    'llm_pass': 'ped+GlubbomOnEc4',
    'llm_provider': ACTIVE_LLM_PROVIDER,
    'llm_api_key': _default_llm_api_key(ACTIVE_LLM_PROVIDER),
    'llm_model': ACTIVE_LLM_MODEL,
    'llm_temp': 0,
    'llm_reader': HYBRID_LLM_READER,

    "https://ollama1.src-automating.src.surf-hosted.nl": False,
    "https://ollama2.src-automating.src.surf-hosted.nl": False,
    "https://ollama3.src-automating.src.surf-hosted.nl": False,
    "https://ollama4.src-automating.src.surf-hosted.nl": False,
    "https://ollama5.src-automating.src.surf-hosted.nl": False,
    "https://ollama6.src-automating.src.surf-hosted.nl": False,
    "https://ollama7.src-automating.src.surf-hosted.nl": False,

    'real_world_currency_per_point': 1.00,
    'participation_fee': 0.00,

    'doc': "",
}

CONFIG = SESSION_CONFIG_DEFAULTS

SERVER_NAMES = ['glendronach', 'awesom-o-4000']

hostname = socket.gethostname()
if hostname in LOCAL_NAMES[:2]:
    CONFIG['timeout_experiment'] *= 100

if hostname in LOCAL_NAMES:
    # Each non-existent host adds 5 seconds to Session initialization
    for key in [k for k in CONFIG.keys() if k.startswith('http')]:
        CONFIG[key] = False
    # Otree on Awesom-o with Ollama on Glendronach
    if hostname == LOCAL_NAMES[1]:  # and False:
        CONFIG["http://192.168.199.13:11434"] = True
    else:
        CONFIG["http://localhost:11434"] = True
elif hostname in SERVER_NAMES:
    for key in [k for k in CONFIG.keys() if k.startswith('https://ollama')]:
        CONFIG[key] = True

PARTICIPANT_FIELDS = ['role', 'choice']
SESSION_FIELDS = ['first_mover_role', 'llm_hosts']

# ISO-639 code
# for example: de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'

# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'EUR'
USE_POINTS = False

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """ """

SECRET_KEY = '5388071882920'
