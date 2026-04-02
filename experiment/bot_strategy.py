import asyncio
import random
import sys

from .bot_base import BotBase
from .bot_llm import BotLLM
from .offer import Offer, Evaluation
from .constants import C
from .prompts import (HYBRID_PROMPTS, not_profitable_prompt, empty_offer_prompt,
                      offer_without_price_prompt, offer_without_quantity_prompt,
                      offer_invalid, offer_with_single_unfavourable_term_prompt)
from .optimal import optimal_solution_string
from .utils import log_debug, log_function


class BotStrategy(BotBase, BotLLM):
    def initial(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        if self.role == C.ROLE_RETAILER_EMPLOYEE:
            message = HYBRID_PROMPTS['first_message_PC']
        else:
            message = HYBRID_PROMPTS['first_message_MP']
        self.store_send_data(llm_output=message)

    async def follow_up(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        # Extract possible offer, add to the list if valid
        self.offer_user = await self.interpret_offer(self.user_message)
        self.offer_list.append(self.offer_user)
        await self.evaluate()

    async def interface_offer(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        # Offer already added to the list in Player.process_offer()
        self.offer_user = self.offer_list[-1]

        # Evaluate the profitability of user offer and respond
        await self.evaluate()

    async def evaluate(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        # Add profits for user and bot to the offers
        for offer in self.offer_list:
            self.add_profits(offer)

        # Evaluate the profitability of user offer and respond
        evaluation = self.offer_user.evaluate(self.constraint_user,
                                              self.constraint_bot,
                                              self.bot_is_supplier)

        self.optimal_offer_str = optimal_solution_string(self.constraint_user,
                                                         self.constraint_bot,
                                                         evaluation,
                                                         self.offer_user,
                                                         self.bot_is_supplier)

        if evaluation == Evaluation.ACCEPT:
            await self.accept_offer()
        else:
            await self.respond_to_offer(evaluation)

    async def accept_offer(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        if self.offer_user.from_chat:
            content = HYBRID_PROMPTS['accept_from_chat'] + self.user_message
        else:
            content = HYBRID_PROMPTS['accept_from_interface'] + self.user_message

        response = await self.get_llm_response(content)
        llm_output = self.extract_content(response)
        self.store_send_data(llm_output=llm_output)

        if self.offer_user.from_chat:
            await self.accept_final_chat()
        else:
            await self.accept_final_interface()

    async def accept_final_chat(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        await asyncio.sleep(4)
        # Create offer matching offer for user to accept
        bot_offer = Offer(idx=-1,
                          price=self.offer_user.price,
                          quantity=self.offer_user.quantity,
                          test="accept_final_chat")
        self.add_profits(bot_offer)
        self.offer_list.append(bot_offer)
        self.store_send_data()

    async def accept_final_interface(self):
        log_function(__class__, sys._getframe().f_code.co_name)

        await asyncio.sleep(4)
        # Accept on the model
        player, participant = self.get_player_participant()
        player.process_accept(self.offer_user.price, self.offer_user.quantity)
        # Accept in the interface
        self.send_asyncio_data({'finished': True})

    def get_respond_prompt(self, evaluation: Evaluation | None) -> str:
        log_function(__class__, sys._getframe().f_code.co_name)

        if evaluation == Evaluation.NOT_OFFER:
            return empty_offer_prompt(
                self.config, self.user_message,
                self.optimal_offer_str, str(self.interaction_list))
        elif evaluation == Evaluation.NOT_PROFITABLE_ON_BOTH:
            return offer_with_single_unfavourable_term_prompt(
                self.config, self.user_message,
                self.optimal_offer_str, str(self.interaction_list))
        elif evaluation == Evaluation.OFFER_QUANTITY:
            return offer_without_price_prompt(
                self.config, self.user_message,
                self.optimal_offer_str, str(self.interaction_list))
        elif evaluation == Evaluation.OFFER_PRICE:
            return offer_without_quantity_prompt(
                self.config, self.user_message,
                self.optimal_offer_str, str(self.interaction_list))
        elif evaluation == Evaluation.INVALID_OFFER:
            return offer_invalid(self.config, self.user_message)
        else:
            return not_profitable_prompt(
                self.config, self.user_message,
                self.optimal_offer_str, str(self.interaction_list))

    async def respond_to_offer(self, evaluation: Evaluation):
        log_function(__class__, sys._getframe().f_code.co_name)

        content1 = self.get_respond_prompt(evaluation)
        content2 = self.get_respond_prompt(None)
        respond_to_non_offer = evaluation.is_non_offer

        llm_offers = []
        last_offer = llm_output = None
        while len(llm_offers) < 3:
            content = content1 if len(llm_offers) < 2 else content2
            response = await self.get_llm_response(content)
            log_debug(f"[DEBUG Bot_strategy.respond_to_offer] 1 - "
                      "Bot internal message", response.message.content)
            llm_output = self.extract_content(response)
            log_debug(f"[DEBUG Bot_strategy.respond_to_offer] 2 - "
                      "LLM output", llm_output)
            last_offer = await self.interpret_offer(llm_output, -1)

            if last_offer.is_complete:
                self.add_profits(last_offer)
                evaluation = last_offer.evaluate(self.constraint_user,
                                                 self.constraint_bot,
                                                 self.bot_is_supplier)
                log_debug(f"[DEBUG Bot_strategy.respond_to_offer] 3 - "
                          "Evaluation of bot offer", evaluation.value)
                if evaluation == Evaluation.ACCEPT:
                    break
            elif respond_to_non_offer:
                log_debug(f"[DEBUG Bot_strategy.respond_to_offer] 5 - "
                          f"Not complete and respond_to_non_offer")
                last_offer.profit_bot = last_offer.profit_user = 0
                self.send_response(llm_output, last_offer)
                return
            else:
                # If the offer is not complete, set profits to 0 and continue
                last_offer.profit_bot = last_offer.profit_user = 0
                log_debug(f"[DEBUG Bot_strategy.respond_to_offer] 4 - "
                          f"Not complete")

            # Append the offer to the list and continue generating
            llm_offers.append([last_offer.profit_bot, llm_output, last_offer])

        # No profitable offer after 3 attempts: choose the best among the worst
        if evaluation != Evaluation.ACCEPT:
            _, llm_output, last_offer = self.best_last_offer(llm_offers)

        self.send_response(llm_output, last_offer)

    @staticmethod
    def best_last_offer(llm_offers: list[tuple[int, str, Offer]]) \
            -> tuple[int, str, Offer]:
        log_function(__class__, sys._getframe().f_code.co_name)

        max_profit = max(llm_offer[0] for llm_offer in llm_offers)
        best_offer = random.choice([llm_offer for llm_offer in llm_offers
                                    if llm_offer[0] == max_profit])
        return best_offer

    def send_response(self, llm_output: str, last_offer: Offer):
        log_function(__class__, sys._getframe().f_code.co_name)

        if last_offer is not None and last_offer.is_valid:
            self.offer_list.append(last_offer)
        if llm_output is not None:
            self.store_send_data(llm_output=llm_output)
