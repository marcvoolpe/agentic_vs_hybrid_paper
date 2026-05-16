from .offer import Offer
from .optimal import nash_bargaining_solution

ACTION_TOOLS = {"send_chat", "send_offer", "accept_offer"}


TOOLS = [
{
    "type": "function",
    "function": {
        "name": "send_chat",
        "description": "Send a chat message to the human negotiator. "
                    "Use this to respond conversationally, ask questions, "
                    "or explain your position without making a formal offer.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message text to send to the negotiator"
                }
            },
            "required": ["message"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "propose_offer",
        "description": "Draft three offers and evaluate their profitability BEFORE sending any. "
                    "For each offer, returns your profit, the human's profit, target_profit, and surplus. "
                    "If surplus >= 0 the offer meets your target. "
                    "This does NOT send any offer yet — call send_offer with the offer number to send it.",
        "parameters": {
            "type": "object",
            "properties": {
                "price_1": {
                    "type": "number",
                    "description": "The price of the first offer"
                },
                "quantity_1": {
                    "type": "integer",
                    "description": "The quantity of the first offer"
                },
                "price_2": {
                    "type": "number",
                    "description": "The price of the second offer"
                },
                "quantity_2": {
                    "type": "integer",
                    "description": "The quantity of the second offer"
                },
                "price_3": {
                    "type": "number",
                    "description": "The price of the third offer"
                },
                "quantity_3": {
                    "type": "integer",
                    "description": "The quantity of the third offer"
                }
            },
            "required": ["price_1", "quantity_1", "price_2", "quantity_2", "price_3", "quantity_3"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "send_offer",
        "description": "Send the chosen proposed offer to the human negotiator via the interface and the chat. "
                    "Call this only after calling propose_offer and the chosen pending offer meets your target. "
                    "NEVER use this tool if the chosen offer evaluation yields negative surplus."
                    "Once sent, the negotiator can officially accept or counter. ",
        "parameters": {
            "type": "object",
            "properties": {
                "offer_number": {
                    "type": "integer",
                    "description": "the offer number (1 or 2 or 3) of the proposed offer you want to send to your counterpart."
                },
                "message": {
                    "type": "string",
                    "description": "message that contains the terms of the offer along with a brief explanation based on the context."
                } 
            },
            "required": ["offer_number", "message"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "accept_offer",
        "description": "Accept the last offer from the human negotiator. "
                    "NEVER use this tool if the last offer evaluation yields negative surplus."
                    "This is irreversible — the negotiation ends immediately and "
                    "profits are computed. "
                    "IMPORTANT: You MUST call evaluate_offer first to confirm the "
                    "received offer meets your profit target before calling this.",
        "parameters": {
            "type": "object",
            "properties": {},
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "evaluate_offer",
        "description": "Evaluate the profitability of an offer. "
                       "Call this when you receive an offer - always. "
                       "If no price and quantity are provided in the chat, evaluates the last "
                       "offer received from the human negotiator. "
                       "Returns your profit, the human's profit, target_profit (Nash), "
                       "and surplus (profit - target). "
                       "If surplus >= 0 the offer meets your target; if surplus < 0 it does not.",
        "parameters": {
            "type": "object",
            "properties": {
                "price": {
                    "type": "number",
                    "description": "Price to evaluate. Omit to evaluate last received offer."
                },
                "quantity": {
                    "type": "integer",
                    "description": "Quantity to evaluate. Omit to evaluate last received offer."
                }
            },
            "required": []  #if passed, the llm is evaluating its own offer to send, otherwise it's received
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "evaluate_single",
        "description": "Evaluate if a single term can lead to a profitable offer or no. "
                       "Call this when you receive an offer with a single term - always. "
                       "If no price is provided in the chat, evaluates feasibility of quantity, and viceversa "
                       "Returns True if it's possible to reach a profitable offer by fixing this term. "
                       "If False, there is no feasible offer that maintains this term"
                       "A profitable offer always has surplus >= 0",
        "parameters": {
            "type": "object",
            "properties": {
                "price": {
                    "type": "number",
                    "description": "Price to evaluate."
                },
                "quantity": {
                    "type": "integer",
                    "description": "Quantity to evaluate."
                }
            },
            "required": []
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "compute_nash",
        "description": "Compute the Nash bargaining solution for this negotiation. "
                       "Returns the optimal price, quantity, and profit. "
                       "The Nash profit is your minimum acceptable profit threshold — "
                       "any deal where your profit falls below this should be rejected. "
                       "Use this when you need a reference point to evaluate or propose offers.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
}]

def numeric_offer_evaluation(price: float, quantity: int, role: str,
                            constraint_user: int, constraint_bot: int,
                            include_profitable: bool = True):
    offer = Offer(price=price, quantity=quantity)
    offer.profits(bot_role=role, constraint_user=constraint_user,
                  constraint_bot=constraint_bot)

    target = nash_bargaining_solution(constraint_user, constraint_bot)['profit']

    result = {
        'profit_bot': offer.profit_bot,
        'profit_user': offer.profit_user,
        'target_profit': target,
        'surplus': round(offer.profit_bot - target, 2),
    }
    if include_profitable:
        result['profitable'] = offer.profit_bot - target >= 0
    return result