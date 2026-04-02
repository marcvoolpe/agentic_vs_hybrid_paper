from otree.api import *
from otree.models import Session
from otree.database import wrap_column, OTreeColumn, AUTO_SUBMIT_DEFAULTS
from sqlalchemy.sql import sqltypes as st

AUTO_SUBMIT_DEFAULTS[st.JSON] = {}


# Do not user .append / += [] (list), .update (dict) or form_fields!
def JsonField(**kwargs) -> OTreeColumn:
    return wrap_column(st.JSON, **kwargs)


class ConstraintsConstants(BaseConstants):
    PRICE_MIN = 1
    PRICE_MAX = 12
    PRICE_RANGE = [x / 100 for x in range(PRICE_MIN * 100, PRICE_MAX * 100 + 1)]
    QUANTITY_MIN = 1
    QUANTITY_MAX = 100
    QUANTITY_RANGE = [x for x in range(QUANTITY_MIN, QUANTITY_MAX + 1)]
    DEMAND_MIN = 0
    DEMAND_MAX = 100


class RoleConstants(ConstraintsConstants):
    # Role identifiers
    ROLE_RETAILER_MANAGER = 'Retailer Manager'  # id_in_group == 1
    ROLE_SUPPLIER_MANAGER = 'Supplier Manager'  # id_in_group == 2
    ROLE_RETAILER_EMPLOYEE = 'Retailer'  # id_in_group == 3
    ROLE_SUPPLIER_EMPLOYEE = 'Supplier'  # id_in_group == 4
    ROLES_MANAGEMENT = [ROLE_RETAILER_MANAGER, ROLE_SUPPLIER_MANAGER]
    ROLES_EMPLOYEE = [ROLE_RETAILER_EMPLOYEE, ROLE_SUPPLIER_EMPLOYEE]
    ROLES = ROLES_MANAGEMENT + ROLES_EMPLOYEE
    ROLES_RETAILER = [ROLE_RETAILER_MANAGER, ROLE_RETAILER_EMPLOYEE]
    ROLES_SUPPLIER = [ROLE_SUPPLIER_MANAGER, ROLE_SUPPLIER_EMPLOYEE]
    assert set(ROLES) == set(ROLES_RETAILER + ROLES_SUPPLIER)

    # Agents
    AGENT_JUNIOR = 'Junior Agent'
    AGENT_SENIOR = 'Senior Agent'
    AGENT_AI = 'AI Agent'
    AGENT_HUMAN = 'Human Agent'
    AGENT_INDIFFERENT = 'Indifferent'

    HUMAN_SENIOR = 'HS'  # HUMAN_AGENT / SENIOR_AGENT
    AI_JUNIOR = 'AJ'  # AI_AGENT / JUNIOR_AGENT
    INDIFFERENT = 'I'

    # get_human_agent_label
    @classmethod
    def get_agent_1(cls, session: Session):
        if session.config['baseline']:
            return cls.AGENT_SENIOR
        return cls.AGENT_HUMAN

    # get_ai_agent_label
    @classmethod
    def get_agent_2(cls, session: Session):
        if session.config['baseline']:
            return cls.AGENT_JUNIOR
        return cls.AGENT_AI


class RoleUtils:
    session = None
    group = None
    id_in_group = None
    role = None

    @property
    def is_management(self) -> bool:
        return self.role in RoleConstants.ROLES_MANAGEMENT

    @property
    def is_first_mover(self) -> bool:
        return self.role == self.session.first_mover_role

    @property
    def is_supplier(self) -> bool:
        return self.role in RoleConstants.ROLES_SUPPLIER

    @property
    def is_retailer(self) -> bool:
        return self.role in RoleConstants.ROLES_RETAILER

    @property
    def opposite_id(self):
        if self.id_in_group < 3:
            return 1 + (self.id_in_group == 1)
        else:
            return 3 + (self.id_in_group == 3)

    @property
    def opposite_role(self) -> str:
        return RoleConstants.ROLES[self.opposite_id - 1]

    @property
    def clean_role(self) -> str:
        return self.role.split(' ')[0]

    @property
    def clean_opposite_role(self) -> str:
        return self.opposite_role.split(' ')[0]

    @property
    def idle_player(self) -> 'Player':
        assert self.role in RoleConstants.ROLES_EMPLOYEE
        idle_id = 3 if self.id_in_group == 4 else 4
        return self.group.get_player_by_id(idle_id)

    @property
    def employee_player(self) -> 'Player':
        assert self.role in RoleConstants.ROLES_MANAGEMENT
        employee_id = 3 if self.id_in_group == 1 else 4
        return self.group.get_player_by_id(employee_id)


CLASS_A = 'Class A'
CLASS_B = 'Class B'
CLASS_C = 'Class C'

CLASS_DICT = {
    CLASS_A: {'market_price': 11, 'production_cost': 3,
              'transaction_costs': [25, 50], },
    CLASS_B: {'market_price': 11, 'production_cost': 4,
              'transaction_costs': [20, 40], },
    CLASS_C: {'market_price': 11, 'production_cost': 5,
              'transaction_costs': [15, 30], },
}

RC = RoleConstants
ROOM_CONFIGS = {
    1: {'product_class': CLASS_C,
        'first': RC.ROLE_SUPPLIER_EMPLOYEE, 'baseline': False},
    2: {'product_class': CLASS_C,
        'first': RC.ROLE_SUPPLIER_EMPLOYEE, 'baseline': True},
    3: {'product_class': CLASS_B,
        'first': RC.ROLE_RETAILER_EMPLOYEE, 'baseline': False},
    4: {'product_class': CLASS_B,
        'first': RC.ROLE_RETAILER_EMPLOYEE, 'baseline': True},
    5: {'product_class': CLASS_A,
        'first': RC.ROLE_SUPPLIER_EMPLOYEE, 'baseline': False},
    6: {'product_class': CLASS_A,
        'first': RC.ROLE_SUPPLIER_EMPLOYEE, 'baseline': True},
    7: {'product_class': CLASS_C,
        'first': RC.ROLE_RETAILER_EMPLOYEE, 'baseline': False},
    8: {'product_class': CLASS_C,
        'first': RC.ROLE_RETAILER_EMPLOYEE, 'baseline': True},
    9: {'product_class': CLASS_B,
        'first': RC.ROLE_SUPPLIER_EMPLOYEE, 'baseline': False},
    10: {'product_class': CLASS_B,
         'first': RC.ROLE_SUPPLIER_EMPLOYEE, 'baseline': True},
    11: {'product_class': CLASS_A,
         'first': RC.ROLE_RETAILER_EMPLOYEE, 'baseline': False},
    12: {'product_class': CLASS_A,
         'first': RC.ROLE_RETAILER_EMPLOYEE, 'baseline': True},
}


def employee_retailer_profit(market_price: float, price: float,
                             quantity_sold: int) -> float:
    return (market_price - price) * quantity_sold


def employee_supplier_profit(price: float, production_cost: float,
                             quantity_sold: int, quantity_unsold: int) -> float:
    return (price - production_cost) * quantity_sold \
        - production_cost * quantity_unsold
