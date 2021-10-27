import random
import sys
from collections import deque
from datetime import datetime

from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.models import Coin


class Strategy(AutoTrader):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_coin_candidates = deque()

    def initialize(self):
        super().initialize()
        split_fraction = self.config.SOURCE_COIN_SPLIT_FRACTION
        if not split_fraction or split_fraction >= 1.0:
            raise ValueError(
                f"source_coin_split_fraction={split_fraction} does not make sense for parallel transactions"
                f"strategy. Think of using any other strategy or provide valid split fractions."
            )
        self.initialize_current_coin()

    def scout(self):
        """
        Scout for potential jumps from the current coin to another coin
        """
        if self.current_coin_candidates:
            current_coin = self.current_coin_candidates.popleft()
            self.db.set_current_coin(current_coin)
        else:
            current_coin = self.db.get_current_coin()
        # Display on the console, the current coin+Bridge, so users can see *some* activity and not think the bot has
        # stopped. Not logging though to reduce log size.
        print(
            f"{datetime.now()} - CONSOLE - INFO - I am scouting the best trades. "
            f"Current coin: {current_coin + self.config.BRIDGE} ",
            end="\r",
        )

        current_coin_price = self.manager.get_ticker_price(current_coin + self.config.BRIDGE)

        if current_coin_price is None:
            self.logger.info("Skipping scouting... current coin {} not found".format(current_coin + self.config.BRIDGE))
            return

        self._jump_to_best_coin(current_coin, current_coin_price)

    def _jump_to_best_coin(self, coin: Coin, coin_price: float):
        """
        Given a coin, search for coin(s) to jump to
        """
        trade_happened = False
        split_fraction = self.config.SOURCE_COIN_SPLIT_FRACTION
        ratio_dict = self._get_ratios(coin, coin_price)
        # keep only ratios bigger than zero
        ratio_dict = {k: v for k, v in ratio_dict.items() if v > 0}
        min_notional = self.manager.get_min_notional(coin.symbol, self.config.BRIDGE.symbol)

        # if we have any viable options, pick the one with the biggest ratio
        if ratio_dict:
            best_pairs = sorted(ratio_dict, key=ratio_dict.get)
            self.logger.info(f"Sorted Best Pairs: {best_pairs}")
            for best_pair in best_pairs:
                self.logger.info(f"Best Pair: {best_pair}\t Fraction: {split_fraction}")

                if best_pair.to_coin in self.current_coin_candidates:
                    self.logger.info(f"Skipping buy of {best_pair.to_coin} as it is already available in the queue.")
                    continue

                balance = self.manager.get_currency_balance(coin.symbol)
                balance_in_bridge = balance * coin_price

                destination_balance = self.manager.get_currency_balance(best_pair.to_coin.symbol)
                destination_coin_price = self.manager.get_ticker_price(best_pair.to_coin + self.config.BRIDGE)
                destination_balance_in_bridge = destination_balance * destination_coin_price
                if destination_balance_in_bridge >= self.config.SIGNIFICANT_BALANCE_THRESHOLD:
                    self.logger.info(
                        f"Skipping Buy of {best_pair.to_coin} as it already has balance(in bridge)={destination_balance_in_bridge} >= {self.config.SIGNIFICANT_BALANCE_THRESHOLD}"
                        f" Adding it in the queue."
                    )
                    self.current_coin_candidates.append(best_pair.to_coin)
                    continue

                if balance_in_bridge * split_fraction >= min_notional:
                    balance_to_use = balance * split_fraction
                else:
                    balance_to_use = balance
                    self.logger.info(
                        f"Using full coin's balance as balance={balance} bcz balance_in_bridge*split_fraction={balance_in_bridge * split_fraction} < {min_notional}"
                    )

                self.logger.info(f"Will be jumping from {coin} to {best_pair.to_coin_id}")
                self.logger.info(f"Using {balance_to_use} out of {balance} of {coin}")
                result = self.transaction_through_bridge(best_pair, origin_balance_to_use=balance_to_use)
                self.logger.info(f"Result of transaction: {result}")
                if result is not None:
                    trade_happened = True
                    self.logger.info(f"Adding {best_pair.to_coin} in the queue.")
                    self.current_coin_candidates.append(best_pair.to_coin)

        if not trade_happened:
            self.current_coin_candidates.append(coin)
            return

        new_balance = self.manager.get_currency_balance(coin.symbol)
        new_balance_in_bridge = new_balance * coin_price
        if new_balance_in_bridge >= self.config.MINIMUM_BALANCE_THRESHOLD_FOR_SCOUTING:
            self.logger.info(
                f"Adding current coin {coin} again in the queue as it has significant balance remaining(in bridge)={new_balance_in_bridge} >= {self.config.MINIMUM_BALANCE_THRESHOLD_FOR_SCOUTING}"
            )
            self.current_coin_candidates.append(coin)
        else:
            self.logger.info(
                f"Not adding current coin {coin} again in the queue as it does not has significant balance remaining(in bridge)={new_balance_in_bridge} < {self.config.MINIMUM_BALANCE_THRESHOLD_FOR_SCOUTING}"
            )

    def bridge_scout(self):
        current_coin = self.db.get_current_coin()
        if self.manager.get_currency_balance(current_coin.symbol) > self.manager.get_min_notional(
            current_coin.symbol, self.config.BRIDGE.symbol
        ):
            # Only scout if we don't have enough of the current coin
            return
        new_coin = super().bridge_scout()
        if new_coin is not None:
            self.db.set_current_coin(new_coin)

    def initialize_current_coin(self):
        """
        Decide what is the current coin, and set it up in the DB.
        """
        if self.db.get_current_coin() is None:
            current_coin_symbol = self.config.CURRENT_COIN_SYMBOL
            if not current_coin_symbol:
                current_coin_symbol = random.choice(self.config.SUPPORTED_COIN_LIST)

            self.logger.info(f"Setting initial coin to {current_coin_symbol}")

            if current_coin_symbol not in self.config.SUPPORTED_COIN_LIST:
                sys.exit("***\nERROR!\nSince there is no backup file, a proper coin name must be provided at init\n***")
            self.db.set_current_coin(current_coin_symbol)

            # if we don't have a configuration, we selected a coin at random... Buy it so we can start trading.
            if self.config.CURRENT_COIN_SYMBOL == "":
                current_coin = self.db.get_current_coin()
                self.logger.info(f"Purchasing {current_coin} to begin trading")
                self.manager.buy_alt(current_coin, self.config.BRIDGE)
                self.logger.info("Ready to start trading")
