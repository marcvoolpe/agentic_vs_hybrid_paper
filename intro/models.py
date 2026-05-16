import json
import random
from mimetypes import inited

from otree.api import *
from otree.database import LongStringField

from common import JsonField, RoleUtils, ROOM_CONFIGS
from settings import get_active_classes
from .constants import C


class Subsession(BaseSubsession):
    def initialize_subsession(self):
        config = self.session.config

        # Get stuff from settings
        force_retailer = config['force_retailer_first']
        force_supplier = config['force_supplier_first']
        available_classes = get_active_classes(config)

        # Overwrite if room is defined
        if config['room'] in range(1, 13):
            room = ROOM_CONFIGS[config['room']]
            if room['first'] == C.ROLE_SUPPLIER_EMPLOYEE:
                force_supplier = True
            else:
                force_retailer = True
            available_classes = len(self.get_groups()) * room['product_class']
            config['baseline'] = room['baseline']

        # Determine the first mover
        if force_retailer and not force_supplier:
            self.session.first_mover_role = C.ROLE_RETAILER_MANAGER
        elif force_supplier and not force_retailer:
            self.session.first_mover_role = C.ROLE_SUPPLIER_MANAGER
        else:
            # Both False or both True (invalid) -> default to random
            self.session.first_mover_role = random.choice(C.ROLES_MANAGEMENT)

        # Select and store class for each group
        group_classes = self.session.vars['group_classes'] = {}
        for group in self.get_groups():
            group_classes[group.id_in_subsession] = \
                self.select_random_class(available_classes)

            # Set role and copy to participant
            for player in group.get_players():
                player._role = C.ROLES[player.id_in_group - 1]
                player.participant.role = player.role

    @staticmethod
    def select_random_class(available_classes: dict[str, dict[str, int]]) \
            -> dict[str, str | dict[str, int]]:
        # Select random class
        class_name = random.choice(list(available_classes.keys()))
        class_params = available_classes.pop(class_name)
        return {'class_name': class_name,
                'class_params': class_params}

    @staticmethod
    def clean_classes(classes: dict[str, any]) -> list[str]:
        return [k.replace("Class ", "") for k in classes.keys()]


def creating_session(sub_session: Subsession):
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

    @property
    def both_human_or_senior(self) -> bool:
        return self.retailer_choice == self.supplier_choice == C.HUMAN_SENIOR

    @property
    def both_ai_or_junior(self) -> bool:
        return self.retailer_choice == self.supplier_choice == C.AI_JUNIOR


class Player(BasePlayer, RoleUtils):
    # Manager comprehension check answers
    comprehension_answer_a = models.FloatField(blank=True, null=True)
    comprehension_answer_b = models.FloatField(blank=True, null=True)
    # Employee comprehension check answer
    comprehension_check = models.IntegerField()

    # Used by both
    comprehension_answer = LongStringField(
        initial=json.dumps({i: [] for i in range(1, 6)}))
    comprehension_attempts = LongStringField(
        initial=json.dumps({str(i): 1 for i in range(1, 6)}))
