import math

from .constants import C
from .offer import Offer, Evaluation
from .prompts import HYBRID_PROMPTS
from .utils import log_debug

OPTIMAL_OFFER = ("A Wholesale Price of %.2f€ and %d units have expected "
                 "profits of %.1f (Same expected profit for you and your "
                 "counterpart).")


def nash_bargaining_solution(constraint_user: int, constraint_bot: int) \
        -> dict[str, float | tuple[float, int]]:
    market_price = max(constraint_user, constraint_bot)
    production_cost = min(constraint_user, constraint_bot)

    demand_range = C.DEMAND_MAX - C.DEMAND_MIN
    quantity_continuous = demand_range * (
            market_price - production_cost) / market_price
    price_star = round(market_price * (market_price + 3 * production_cost) / (
            2 * (market_price + production_cost)), 2)

    # Choose between floor and ceil by maximizing total profit
    q_candidates = [math.floor(quantity_continuous),
                    math.ceil(quantity_continuous)]

    def sort_function(q):
        return (Offer.profit_supplier(price_star, q, production_cost)
                + Offer.profit_retailer(price_star, q, market_price))

    quantity_star = int(max(q_candidates, key=sort_function))

    profit_supplier = Offer.profit_supplier(
        price_star, quantity_star, production_cost)
    profit_retailer = Offer.profit_retailer(
        price_star, quantity_star, market_price)
    target_profit = (math.floor(profit_supplier * 100) / 100
                     if production_cost == constraint_bot
                     else math.floor(profit_retailer * 100) / 100)

    return {'profit': target_profit, 'offer': (price_star, quantity_star)}


def optimal_wholesale_price_for_quantity(offer: Offer,
                                         constraint_user: int,
                                         constraint_bot: int,
                                         bot_is_supplier: bool) \
        -> tuple[float | None, float | None]:
    q = float(offer.quantity)
    Pm = max(constraint_bot, constraint_user)  # Market price 
    c = min(constraint_bot, constraint_user)  # Production cost
    d_min, d_max = C.DEMAND_MIN, C.DEMAND_MAX
    E = (((q ** 2 - d_min ** 2) / 2) + q * (d_max - q)) / (d_max - d_min)

    # Nash bargaining solution: the minimum acceptable profit for the bot
    target = nash_bargaining_solution(constraint_user, constraint_bot)['profit']

    if bot_is_supplier:
        # rounding up to ensure reaching target profit
        best_p = math.ceil(((target + c * q) / E) * 100) / 100
    else:
        # rounding down to ensure reaching target profit
        best_p = math.floor((Pm - target / E) * 100) / 100

    if best_p > 0:
        return best_p, q
    else:
        return None, None


def optimal_quantity_for_wholesale_price(offer: Offer,
                                         constraint_user: int,
                                         constraint_bot: int,
                                         bot_is_supplier: bool) \
        -> tuple[float | None, int | None]:
    """
    Formulas:
        retailer_profit(q)    = (market_price - price) * ES(q)
        supplier_profit(q) = price * ES(q) - production_cost * q
        ES(q) = ((q^2 - dmin^2)/2 + q*(dmax - q)) / (dmax - dmin   
    """

    # ========================================
    # 1. EXTRACT AND DEFINE CORE PARAMETERS
    # ========================================

    p = float(offer.price)
    Pm = max(constraint_bot, constraint_user)  # Market price 
    c = min(constraint_bot, constraint_user)  # Production cost
    dmin, dmax = C.DEMAND_MIN, C.DEMAND_MAX

    # Nash bargaining solution: the minimum acceptable profit for the bot
    target = float(
        nash_bargaining_solution(constraint_user, constraint_bot)['profit'])

    # ========================================
    # 2. ASSIGN PROFIT FUNCTIONS BY ROLE
    # ========================================

    def ES(q: float) -> float:
        return ((q * q - dmin * dmin) / 2.0 + q * (dmax - q)) / (dmax - dmin)

    def retailer_profit(q: float) -> float:
        return (Pm - p) * ES(q)

    def supplier_profit(q: float) -> float:
        return p * ES(q) - c * q

    # Creating new functions for counting profits instead of using the ones
    # from Offer module. Since all the parameters except q are fixed

    if bot_is_supplier:
        bot_profit = supplier_profit
        user_profit = retailer_profit
    else:
        bot_profit = retailer_profit
        user_profit = supplier_profit

    # ========================================
    # 3. DEFINE ROOT-FINDING FUNCTIONS
    # ========================================
    # These functions solve for quantity values where profit exactly equals the target

    def retailer_roots(B: float) -> tuple[float | None, float | None]:
        """
        Solves (Pm - p) * ES(q) = B for q (retailer profit = target).
        Returns: tuple of two roots or None if no real solution exists.
        """
        A = Pm - p

        # Discriminant of the quadratic equation
        rad = -A * (dmax - dmin) * (
                2 * B - Pm * (dmax + dmin) + p * (dmax + dmin))
        if rad < -1e-12:  # No real roots
            return None, None

        s = math.sqrt(max(0.0, rad))
        return (dmax * A - s) / A, (dmax * A + s) / A

    def supplier_roots(S: float) -> tuple[float | None, float | None]:
        """
        Solves p * ES(q) - c * q = S for q (supplier profit = target).
        Returns tuple of two roots or None if no real solution exists.
        
        This is a quadratic equation of the form: A*q^2 + Bc*q + C0 = 0
        """
        A = -p
        Bc = 2 * p * dmax - 2 * c * (dmax - dmin)
        C0 = p * dmin * dmin - 2 * S * (dmax - dmin)

        # Calculate discriminant
        disc = Bc * Bc - 4 * A * C0
        if disc < -1e-12:  # No real roots
            return None, None

        s = math.sqrt(max(0.0, disc))
        # Apply quadratic formula: q = (-B +- sqrt(disc)) / (2*A)
        return (-Bc - s) / (2 * A), (-Bc + s) / (2 * A)

    # ========================================
    # 4. IDENTIFY VERTEX POINTS (PROFIT MAXIMA)
    # ========================================
    # These points help locate integer candidates near optimal continuous solutions

    # Retailer profit typically maximizes at high quantity
    retailer_vertex = dmax
    supplier_vertex = (dmax - c * (dmax - dmin) / p
                       if p != 0
                       else (dmin + dmax) / 2)

    # ========================================
    # 5. BUILD INTEGER CANDIDATE SET
    # ========================================
    def build_candidates(roots, extra_vertex=None) -> list[int]:
        """
        Constructs a robust set of integer quantity candidates by sampling:
        - Interval boundaries (dmin, dmax)
        - Integer neighbors around continuous roots
        - Integer neighbors around the profit maximum vertex
        
        Args:
            roots: Tuple of two root values or None
            extra_vertex: Optional additional point to sample around
        
        Returns:
            Sorted list of unique integer candidates
        """
        cand = {int(dmin), int(dmax)}  # Always include boundaries

        # Add integers near the roots
        if roots != (None, None):
            for q in roots:
                q = max(min(q, dmax), dmin)  # Valid range
                b = math.floor(q)
                for k in (-2, -1, 0, 1, 2):  # Sample neighbors
                    qi = int(b + k)
                    if dmin <= qi <= dmax:
                        cand.add(qi)

        # Add integers near the vertex (profit maximum)
        if extra_vertex is not None:
            v = max(min(extra_vertex, dmax), dmin)  # Valid range
            b = math.floor(v)
            for k in (-3, -2, -1, 0, 1, 2, 3):  # Sample neighbors
                qi = int(b + k)
                if dmin <= qi <= dmax:
                    cand.add(qi)

        return sorted(cand)

    # ========================================
    # 6. SELECT OPTIMAL QUANTITY
    # ========================================
    # Selection criteria (in priority order):
    #   1) bot_profit(q) >= target (Nash constraint)
    #   2) Maximize user_profit(q) (efficiency)
    #   3) Tie-break: maximize total profit (bot + user)

    if bot_is_supplier:
        cand = build_candidates(supplier_roots(target),
                                extra_vertex=supplier_vertex)
    else:
        cand = build_candidates(retailer_roots(target),
                                extra_vertex=retailer_vertex)

    # Filter candidates that satisfy the bot's Nash constraint
    feas = [q for q in cand if bot_profit(q) + 1e-9 >= target]

    if feas:
        # Maximize user profit, tie-break by total profit
        best_q = max(feas, key=lambda q: (user_profit(q),
                                          user_profit(q) + bot_profit(q)))
        return round(p, 2), int(best_q)

    # No feasible solution found -> should not happen
    return None, None


def optimal_solution_string(constraint_user: int,
                            constraint_bot: int,
                            evaluation: Evaluation,
                            offer: Offer,
                            bot_is_supplier: bool) -> str:
    args = (offer, constraint_user, constraint_bot, bot_is_supplier)

    if evaluation in (Evaluation.ACCEPT, Evaluation.INVALID_OFFER):
        return ''
    elif evaluation in (Evaluation.OFFER_PRICE,
                        Evaluation.NOT_PROFITABLE_ON_QUANTITY):
        optimal_price, optimal_quantity = \
            optimal_quantity_for_wholesale_price(*args)
    elif evaluation in (Evaluation.OFFER_QUANTITY,
                        Evaluation.NOT_PROFITABLE_ON_PRICE):
        optimal_price, optimal_quantity = \
            optimal_wholesale_price_for_quantity(*args)
    elif evaluation in (Evaluation.NOT_PROFITABLE_ON_BOTH,
                        Evaluation.NOT_OFFER):
        optimal_price, optimal_quantity = \
            nash_bargaining_solution(constraint_bot, constraint_user)['offer']
    else:
        raise Exception(f"Not a valid evaluation: {evaluation.value}")

    target = nash_bargaining_solution(constraint_user, constraint_bot)['profit']
    log_debug(f"[DEBUG optimal_solution_string] optimal_price: {optimal_price},"
              f" optimal_quantity: {optimal_quantity}, target_profit: {target}")
    return HYBRID_PROMPTS['offer_string'] % (optimal_price, optimal_quantity)
