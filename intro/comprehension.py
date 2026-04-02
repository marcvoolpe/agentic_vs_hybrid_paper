MANAGER_QUESTIONS = {
    1: {  # Exact delegation cost - counterpart human & halved transaction costs
        'C': {
            'product_class': 'C',
            'tc': 30,
            'counterpart': 'Human',
            'scenario': 'counterpart human & halved transaction costs',
            'correct_a': 35,  # Human: (30/2) + 20 = 15 + 20 = 35
            'correct_b': 40,  # AI: 30 + 10 = 40
        },
        'A': {
            'product_class': 'A',
            'tc': 50,
            'counterpart': 'Human',
            'scenario': 'counterpart human & halved transaction costs',
            'correct_a': 45,  # Human: (50/2) + 20 = 25 + 20 = 45
            'correct_b': 60,  # AI: 50 + 10 = 60
        },
        'B': {
            'product_class': 'B',
            'tc': 40,
            'counterpart': 'Human',
            'scenario': 'counterpart human & halved transaction costs',
            'correct_a': 40,  # Human: (40/2) + 20 = 20 + 20 = 40
            'correct_b': 50,  # AI: 40 + 10 = 50
        },
    },
    2: {  # Exact delegation cost - counterpart human & full transaction costs
        'C': {
            'product_class': 'C',
            'tc': 30,
            'counterpart': 'Human',
            'scenario': 'counterpart human & full transaction costs',
            'correct_a': 50,  # Human: 30 + 20 = 50
            'correct_b': 40,  # AI: 30 + 10 = 40
        },
        'A': {
            'product_class': 'A',
            'tc': 50,
            'counterpart': 'Human',
            'scenario': 'counterpart human & full transaction costs',
            'correct_a': 70,  # Human: 50 + 20 = 70
            'correct_b': 60,  # AI: 50 + 10 = 60
        },
        'B': {
            'product_class': 'B',
            'tc': 40,
            'counterpart': 'Human',
            'scenario': 'counterpart human & full transaction costs',
            'correct_a': 60,  # Human: 40 + 20 = 60
            'correct_b': 50,  # AI: 40 + 10 = 50
        },
    },
    3: {  # Exact delegation cost with counterpart AI
        'C': {
            'product_class': 'C',
            'tc': 30,
            'counterpart': 'AI',
            'scenario': 'counterpart AI agent',
            'correct_a': 50,  # Human: 30 + 20 = 50
            'correct_b': 40,  # AI: 30 + 10 = 40
        },
        'A': {
            'product_class': 'A',
            'tc': 50,
            'counterpart': 'AI',
            'scenario': 'counterpart AI agent',
            'correct_a': 70,  # Human: 50 + 20 = 70
            'correct_b': 60,  # AI: 50 + 10 = 60
        },
        'B': {
            'product_class': 'B',
            'tc': 40,
            'counterpart': 'AI',
            'scenario': 'counterpart AI agent',
            'correct_a': 60,  # Human: 40 + 20 = 60
            'correct_b': 50,  # AI: 40 + 10 = 50
        },
    },
    4: {  # Expected delegation costs
        'C': {
            'product_class': 'C',
            'tc': 30,
            'counterpart': 'Human',
            'scenario': 'expected delegation costs',
            'correct_a': 42.5,  # Human: 0.75 * 30 + 20 = 22.5 + 20 = 42.5
            'correct_b': 40,  # AI: 30 + 10 = 40
        },
        'A': {
            'product_class': 'A',
            'tc': 50,
            'counterpart': 'Human',
            'scenario': 'expected delegation costs',
            'correct_a': 57.5,  # Human: 0.75 * 50 + 20 = 37.5 + 20 = 57.5
            'correct_b': 60,  # AI: 50 + 10 = 60
        },
        'B': {
            'product_class': 'B',
            'tc': 40,
            'counterpart': 'Human',
            'scenario': 'expected delegation costs',
            'correct_a': 50,  # Human: 0.75 * 40 + 20 = 30 + 20 = 50
            'correct_b': 50,  # AI: 40 + 10 = 50
        },
    },
}


def get_manager_error_message(q_type: int, product_class: str, question: dict) \
        -> str:
    """Generate error message for manager comprehension checks"""
    correct_a = question['correct_a']
    correct_b = question['correct_b']
    tc = question['tc']
    counterpart = question['counterpart']

    # Determine the formula based on question type
    if q_type == 1:  # Halved transaction costs
        formula_human = f"({tc}/2) + 20 = {tc / 2} + 20 = {correct_a}"
        formula_ai = f"{tc} + 10 = {correct_b}"
        explanation = (
            f"<strong>Scenario:</strong> Counterpart delegates to {counterpart}, "
            f"transaction costs are <strong>halved</strong><br><br>"
            f"<strong>Solution:</strong><br>"
            f"Human Agent Delegation Cost = {formula_human}<br>"
            f"AI Agent Delegation Cost = {formula_ai}<br><br>"
        )
    elif q_type == 2:  # Full transaction costs
        formula_human = f"{tc} + 20 = {correct_a}"
        formula_ai = f"{tc} + 10 = {correct_b}"
        explanation = (
            f"<strong>Scenario:</strong> Counterpart delegates to {counterpart}, "
            f"transaction costs are <strong>NOT halved</strong><br><br>"
            f"<strong>Solution:</strong><br>"
            f"Human Agent Delegation Cost = {formula_human}<br>"
            f"AI Agent Delegation Cost = {formula_ai}<br><br>"
        )
    elif q_type == 3:  # Counterpart AI
        formula_human = f"{tc} + 20 = {correct_a}"
        formula_ai = f"{tc} + 10 = {correct_b}"
        explanation = (
            f"<strong>Scenario:</strong> Counterpart delegates to <strong>AI Agent</strong><br><br>"
            f"<strong>Solution:</strong><br>"
            f"Human Agent Delegation Cost = {formula_human}<br>"
            f"AI Agent Delegation Cost = {formula_ai}<br><br>"
        )
    else:  # q_type == 4, Expected costs
        formula_human = f"0.75 × {tc} + 20 = {0.75 * tc} + 20 = {correct_a}"
        formula_ai = f"{tc} + 10 = {correct_b}"
        explanation = (
            f"<strong>Scenario:</strong> <strong>Expected</strong> delegation costs "
            f"when counterpart delegates to {counterpart}<br><br>"
            f"<strong>Solution:</strong><br>"
            f"Expected Human Agent Cost = {formula_human}<br>"
            f"AI Agent Cost = {formula_ai}<br><br>"
        )

    return (
        f"<strong>Oops! You entered incorrect values.</strong><br><br>"
        f"<strong>Product Class {product_class}:</strong><br>"
        f"{explanation}"
        f"<strong>Please try again!</strong>"
    )


def get_employee_error_message(player: 'Player', profit_calc: str,
                               market_price: int, price: int,
                               production_cost: int, quantity: int, demand: int) \
        -> str:
    if player.is_retailer:
        return (
            f"Oops! You entered the incorrect profit.<br><br>"
            f"<b>The Solution:</b><br>"
            f"Retail Price: {market_price}<br>"
            f"Agreed Wholesale Price: {price}<br>"
            f"Agreed Quantity: {quantity}<br>"
            f"The Random Demand from the market: {demand}<br>"
            f"Your profit (as a {player.clean_role}) is calculated as:<br>"
            f"<b>Profit = (Retail Price - Wholesale Price) * Quantity Sold</b><br>"
            f"{profit_calc}<br><br>"
            f"<b>Please try again!</b> (Note: the wholesale price and the constraint are different.)"
        )
    else:
        return (
            f"Oops! You entered the incorrect profit.<br><br>"
            f"<b>The Solution:</b><br>"
            f"Production Cost: {production_cost}<br>"
            f"Agreed Wholesale Price: {price}<br>"
            f"Agreed Quantity: {quantity}<br>"
            f"The Random Demand from the market: {demand}<br>"
            f"Your profit (as a {player.clean_role}) is calculated as:<br>"
            f"<b>Profit = ((Wholesale Price - Production Cost) * Quantity Sold) + "
            f"(Production Cost * Unsold Quantity)</b><br>"
            f"{profit_calc}<br><br>"
            f"<b>Please try again!</b> (Note: the wholesale price and production cost are different.)"
        )


EMPLOYEE_RETAILER_PROFIT = "Profit = (%d - %d) * %d = %d"
EMPLOYEE_SUPPLIER_PROFIT = "Profit = ((%d - %d) * %d) - (%d * %d) = %d"
