import os

from .constants import C, Config


def from_file(base_path: str, file_path: str) -> str:
    with open(os.path.join(base_path, file_path), 'r') as f:
        content = f.read()
    return content.strip() + '\n'


def hybrid_system_final_prompt(config: Config):
    bot_role = config['roles']['bot_role']
    production_cost = config['production_cost']
    market_price = config['market_price']

    before_constraint = HYBRID_PROMPTS[bot_role]['before_constraint']
    bot_constraint = \
        production_cost if bot_role == C.ROLE_SUPPLIER_EMPLOYEE else market_price
    after_constraint = HYBRID_PROMPTS[bot_role]['after_constraint']

    return (before_constraint +
            f"{bot_constraint}€" +
            after_constraint)

def agent_system_final_prompts(config: Config):
    agent_role = config['roles']['bot_role']
    production_cost = config['production_cost']
    market_price = config['market_price']

    before_constraint = AGENT_PROMPTS[agent_role]['before_constraint']
    bot_constraint = \
        production_cost if agent_role == C.ROLE_SUPPLIER_EMPLOYEE else market_price
    after_constraint = AGENT_PROMPTS[agent_role]['after_constraint']

    return (before_constraint +
            f"{bot_constraint}€" +
            after_constraint)


def empty_offer_prompt(config: Config,
                       user_message: str,
                       optimal_offer_str: str,
                       interactions: str) -> str:
    bot_role = config['roles']['bot_role']
    prompts = HYBRID_PROMPTS[bot_role]
    return (prompts['follow_up_prompt_without_offer'] +
            user_message + ' ' +
            prompts['non_profitable_offer_or_deal'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def offer_with_single_unfavourable_term_prompt(config: Config,
                                               user_message: str,
                                               optimal_offer_str: str,
                                               interactions: str) -> str:
    bot_role = config['roles']['bot_role']
    prompts = HYBRID_PROMPTS[bot_role]
    return (prompts['follow_up_prompt_unfavourable_term_offer'] +
            user_message + ' ' +
            prompts['unfavourable_term_offer'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def offer_without_quantity_prompt(config: Config,
                                  user_message: str,
                                  optimal_offer_str: str,
                                  interactions: str) -> str:
    bot_role = config['roles']['bot_role']
    prompts = HYBRID_PROMPTS[bot_role]
    return (prompts['follow_up_prompt_without_quantity'] +
            user_message + ' ' +
            prompts['non_quantity_offer'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def offer_without_price_prompt(config: Config,
                               user_message: str,
                               optimal_offer_str: str,
                               interactions: str) -> str:
    bot_role = config['roles']['bot_role']
    prompts = HYBRID_PROMPTS[bot_role]
    return (prompts['follow_up_prompt_without_price'] +
            user_message + ' ' +
            prompts['non_price_offer'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def not_profitable_prompt(config: Config,
                          user_message: str,
                          optimal_offer_str: str,
                          interactions: str) -> str:
    bot_role = config['roles']['bot_role']
    prompts = HYBRID_PROMPTS[bot_role]
    return (prompts['follow_up_prompt_2nd'] +
            user_message + ' ' +
            prompts['non_profitable_offer'] +
            optimal_offer_str + '\n' +
            prompts['follow_up_conversation'] +
            interactions)


def offer_invalid(config: Config, user_message: str) -> str:
    bot_role = config['roles']['bot_role']
    prompts = HYBRID_PROMPTS[bot_role]
    return (prompts['follow_up_invalid_offer'] +
            user_message + ' ' +
            prompts['invalid_offer_reminder'])


def hybrid_role_prompts(base: str) -> dict[str, str]:
    return {
        'before_constraint': from_file(base, 'system/before_constraint.txt'),
        'after_constraint': from_file(
            base, 'system/after_constraint.txt'),
        'follow_up_prompt_2nd': from_file(base, 'follow_up_user_message.txt'),
        'follow_up_prompt_without_offer': from_file(
            base, 'follow_up_user_message_without_offer.txt'),
        'follow_up_prompt_unfavourable_term_offer': from_file(
            base, 'follow_up_user_message_unfavourable_term_offer.txt'),
        'follow_up_prompt_without_price': from_file(
            base, 'follow_up_user_message_without_price.txt'),
        'follow_up_prompt_without_quantity': from_file(
            base, 'follow_up_user_message_without_quantity.txt'),
        'non_profitable_offer': from_file(
            base, 'non_profitable_Send_Optimal_Offer.txt'),
        'unfavourable_term_offer': from_file(
            base, 'single_term_unfavourable_send_nash.txt'),
        'non_profitable_offer_or_deal': from_file(
            base, 'Send_Optimal_Offer_or_Instructions.txt'),
        'follow_up_conversation': from_file(
            base, 'follow_up_conversation_history.txt'),
        'non_quantity_offer': from_file(
            base, 'Not_Quantity_Send_Optimal_Offer.txt'),
        'follow_up_invalid_offer': from_file(
            base, 'follow_up_user_message_invalid_offer.txt'),
        'invalid_offer_reminder': from_file(
            base, 'invalid_offer_reminder.txt'),
        'non_price_offer': from_file(
            base, 'Not_Price_Send_Optimal_Offer.txt'),
    }

def agent_role_prompts(base: str) -> dict[str, str]:
    return {
        'before_constraint': from_file(base, 'system/before_constraint.txt'),
        'after_constraint': from_file(base, 'system/after_constraint.txt')
    }


HYBRID_PROMPTS = {
    'first_message_PC': "Hi Supplier! I'm excited to start our negotiation. "
                        "As we begin, I'd like to give you the opportunity to "
                        "make an offer first. Or if you prefer, I can make "
                        "the first offer. Just let me know! ",
    'first_message_MP': "Hi Retailer! I'm excited to start our negotiation. "
                        "As we begin, I'd like to give you the opportunity to "
                        "make an offer first. Or if you prefer, I can make "
                        "the first offer. Just let me know! ",
    'offer_string': f"Price of %5.2f€ and quantity of %s",

    # 'constraints': 'Here is the negotiator message you need to read: ',
    # 'context_constraint': {
    #     C.ROLE_RETAILER_EMPLOYEE: 'Base Production Cost (PC)',
    #     C.ROLE_SUPPLIER_EMPLOYEE: 'Base Market Selling Price to Consumer (MP)',
    # },
    # 'constraint_clarify':
    #     'I did not quite understand. '
    #     'Please clarify your current %s at the quantity level of 0.',
    # 'constraint_confirm':
    #     'Confirming: Is %s the correct %s?\n'
    #     'If it is correct, please ONLY enter %s again in the chat bellow.\n'
    #     'Otherwise enter your current %s at the quantity level of 0.',
    # 'constraint_offer':
    #     'I am not ready to respond to your offer yet. '
    #     'Please clarify your current %s at the quantity level of 0 (in the chat bellow).',
    # 'constraint_persist_final_buyer':
    #     'My apologies for persisting.\n'
    #     'Note: My data regarding the normal range of Base Market Selling '
    #     'Prices to Consumers has values between 8 and 10. '
    #     'Thus, I will assume your actual value is 10. \n'
    #     'What combination of Price and Quantity do you have in mind '
    #     'to purchase a 10kg pellet bag?',
    # 'constraint_persist_final_supplier':
    #     'My apologies for persisting.\n'
    #     'Note: My data regarding the normal range of Base Production Cost '
    #     'has values between 1 and 3. Thus, I will assume your actual value '
    #     'is 1. \n'
    #     'What combination of Price and Quantity do you have in mind '
    #     'to sell me a 10kg pellet bag?',
    # 'constraint_final_buyer':
    #     'Thanks, for confirming this information with me.\n'
    #     'What combination of Price and Quantity do you have in mind '
    #     'to purchase a 10kg pellet bag?',
    # 'constraint_final_supplier':
    #     'Thanks, for confirming this information with me.\n'
    #     'What combination of Price and Quantity do you have in mind '
    #     'to sell me a 10kg pellet bag?',

    'understanding_offer':
        'Here is the negotiator message you need to read: ',
    'accept_from_chat': 'Accept the offer sent by your negotiation counterpart '
                        'because the price and quantity terms are favourable, '
                        'thank your counterpart for their understanding but do not '
                        'disclose the existence of your payoff table. '
                        'Also, Ask your counterpart to please click the '
                        'CONFIRM button in the interface, which can be '
                        'found bellow the SEND button.'
                        '(Maximum 30 words and one paragraph) '
                        'Here is the last message from your counterpart: ',
    'accept_from_interface': 'Accept the offer sent by your negotiation counterpart '
                             'because the price and quantity terms are favourable, '
                             'thank your counterpart for their understanding but do not '
                             'disclose the existence of your payoff table. '
                             '(Maximum 30 words and one paragraph) '
                             'Here is the last message from your counterpart: ',

    C.ROLE_RETAILER_EMPLOYEE: hybrid_role_prompts('./prompts/hybrid/retailer/'),
    C.ROLE_SUPPLIER_EMPLOYEE: hybrid_role_prompts('./prompts/hybrid/supplier/'),
}

AGENT_PROMPTS = {
    C.ROLE_RETAILER_EMPLOYEE: agent_role_prompts('./prompts/agent/retailer/'),
    C.ROLE_SUPPLIER_EMPLOYEE: agent_role_prompts('./prompts/agent/supplier/'),
}