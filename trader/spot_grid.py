#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Module: spot grid trader
"""


from binance import BinanceSpotHttp, OrderStatus, OrderType, OrderSide
from utils import config
from utils import utility, round_to, dingding_info
from enum import Enum
import logging
from datetime import datetime

# 现货网格策略

class BinanceTrader(object):

    def __init__(self):
        """
        :param api_key:
        :param secret:
        :param trade_type: 交易的类型， only support future and spot.
        """
        self.http_client = BinanceSpotHttp(api_key=config.api_key, api_secret=config.api_secret, private_key=config.private_key, private_key_pass=config.private_key_pass, proxy_host=config.proxy_host, proxy_port=config.proxy_port)

        self.buy_orders = []  # 买单.
        self.sell_orders = [] # 卖单.

    # bid_price: 买一价, ask_price: 卖一价
    def get_bid_ask_price(self) -> tuple:

        ticker = self.http_client.get_ticker(config.symbol)

        bid_price = 0
        ask_price = 0
        if ticker:
            bid_price = float(ticker.get('bidPrice', 0))
            ask_price = float(ticker.get('askPrice', 0))

        return bid_price, ask_price

    def grid_trader(self):
        """
        执行核心逻辑，网格交易的逻辑.
        :return:
        """

        bid_price, ask_price = self.get_bid_ask_price()
        print(f"bid_price: {bid_price}, ask_price: {ask_price}")
        # config.quantity和config.min_qty在config.json里定义？
        # 含义是网格单位？
        quantity = round_to(float(config.quantity), float(config.min_qty))
        # 买单和卖单数据什么时候更新？
        self.buy_orders.sort(key=lambda x: float(x['price']), reverse=True)  # 最高价到最低价.
        self.sell_orders.sort(key=lambda x: float(x['price']), reverse=True)  # 最高价到最低价.
        print(f"buy orders: {self.buy_orders}")
        print("------------------------------")
        print(f"sell orders: {self.sell_orders}")

        buy_delete_orders = []  # 需要删除买单
        sell_delete_orders = [] # 需要删除的卖单


        # 买单逻辑,检查成交的情况.
        for buy_order in self.buy_orders:

            check_order = self.http_client.get_order(buy_order.get('symbol', config.symbol),\
                client_order_id=buy_order.get('clientOrderId'))

            if check_order:     # 意思是该order成交？
                if check_order.get('status') == OrderStatus.CANCELED.value: # 是用户取消还是服务端取消？
                    buy_delete_orders.append(buy_order)     # 加入到删除列表
                    print(f"buy order status was canceled: {check_order.get('status')}")
                elif check_order.get('status') == OrderStatus.FILLED.value: # FILLED意思是买单里的数量全部成交？
                    # 买单成交，挂卖单.
                    # logging.info(f"买单成交时间: {datetime.now()}, 价格: {check_order.get('price')}, 数量: {check_order.get('origQty')}")
                    log_msg = "买单成交时间: {}, 价格: {}, 数量: {}".format(datetime.now(), check_order.get('price'), check_order.get('origQty'))
                    logging.info(log_msg)
                    # 发送钉钉消息
                    dingding_info(config.dingding_token, config.dingding_prompt, config.symbol, log_msg)

                    # 有买单成交，马上计算网格卖单价并挂出？
                    sell_price = round_to(float(check_order.get("price")) * (1 + float(config.gap_percent)), float(config.min_price))

                    if 0 < sell_price < ask_price:  # ask_price是卖一价(最低卖价)？
                        # 防止价格
                        sell_price = round_to(ask_price, float(config.min_price))

                    # 挂卖单
                    new_sell_order = self.http_client.place_order(symbol=config.symbol, order_side=OrderSide.SELL, order_type=OrderType.LIMIT, quantity=quantity, price=sell_price)
                    if new_sell_order:  # 挂单成功
                        buy_delete_orders.append(buy_order)     # 只有卖单挂出成功，才删除已经成交的买单？
                        self.sell_orders.append(new_sell_order)
                    # 基于网格计算新的买单价格
                    buy_price = round_to(float(check_order.get("price")) * (1 - float(config.gap_percent)),
                                     config.min_price)
                    if buy_price > bid_price > 0:   # bid_price是买一价(最高买价)？
                        buy_price = round_to(bid_price, float(config.min_price))

                    new_buy_order = self.http_client.place_order(symbol=config.symbol, order_side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=quantity, price=buy_price)
                    if new_buy_order:
                        self.buy_orders.append(new_buy_order)
                    # 只要没挂卖单，已成交的买单就不加入del_orders?
                    # 为什么不直接从sell_orders里删除已成交的买单？
                elif check_order.get('status') == OrderStatus.NEW.value:
                    # OrderStatus.NEW.value的意思是服务端接受了这个订单？
                    print("buy order status is: New")
                else:
                    print(f"buy order status is not above options: {check_order.get('status')}")

        # 过期或者拒绝的订单删除掉.
        for delete_order in buy_delete_orders:
            self.buy_orders.remove(delete_order)    #所以是在del_orders里的订单，才会从buy_orders里删除？

        # 卖单逻辑, 检查卖单成交情况.
        for sell_order in self.sell_orders:

            check_order = self.http_client.get_order(sell_order.get('symbol', config.symbol),
                                               client_order_id=sell_order.get('clientOrderId'))
            if check_order:
                if check_order.get('status') == OrderStatus.CANCELED.value:
                    sell_delete_orders.append(sell_order)
                    # 这里不需要额外动作？
                    print(f"sell order status was canceled: {check_order.get('status')}")
                elif check_order.get('status') == OrderStatus.FILLED.value:
                    log_msg = "卖单成交时间: {}, 价格: {}, 数量: {}".format(datetime.now(), check_order.get('price'), check_order.get('origQty'))
                    logging.info(log_msg)
                    dingding_info(config.dingding_token, config.dingding_prompt, config.symbol, log_msg)

                    # 卖单成交，先下买单.
                    buy_price = round_to(float(check_order.get("price")) * (1 - float(config.gap_percent)), float(config.min_price))
                    if buy_price > bid_price > 0:
                        buy_price = round_to(bid_price, float(config.min_price))

                    new_buy_order = self.http_client.place_order(symbol=config.symbol, order_side=OrderSide.BUY,
                                                             order_type=OrderType.LIMIT, quantity=quantity, price=buy_price)
                    if new_buy_order:
                        sell_delete_orders.append(sell_order)
                        self.buy_orders.append(new_buy_order)

                    sell_price = round_to(float(check_order.get("price")) * (1 + float(config.gap_percent)), float(config.min_price))

                    if 0 < sell_price < ask_price:
                        # 防止价格
                        sell_price = round_to(ask_price, float(config.min_price))

                    new_sell_order = self.http_client.place_order(symbol=config.symbol, order_side=OrderSide.SELL,
                                                                 order_type=OrderType.LIMIT, quantity=quantity,
                                                                 price=sell_price)
                    if new_sell_order:
                        self.sell_orders.append(new_sell_order)

                elif check_order.get('status') == OrderStatus.NEW.value:
                    print("sell order status is: New")
                else:
                    print(f"sell order status is not in above options: {check_order.get('status')}")
            else :
                # 这个卖单在服务端不存在，也不管？是觉得服务端可能有遗落或者网络异常？
                pass
        # 过期或者拒绝的订单删除掉.
        for delete_order in sell_delete_orders:
            self.sell_orders.remove(delete_order)

        # 没有买单的时候.
        if len(self.buy_orders) <= 0:
            if bid_price > 0:
                price = round_to(bid_price * (1 - float(config.gap_percent)), float(config.min_price))
                buy_order = self.http_client.place_order(symbol=config.symbol,order_side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=quantity,price=price)
                if buy_order:
                    self.buy_orders.append(buy_order)

        elif len(self.buy_orders) > int(config.max_orders): # 最多允许的挂单数量.
            # 订单数量比较多的时候.
            self.buy_orders.sort(key=lambda x: float(x['price']), reverse=False)  # 最低价到最高价

            delete_order = self.buy_orders[0]
            # 删除最低价的买单.
            order = self.http_client.cancel_order(delete_order.get('symbol'), client_order_id=delete_order.get('clientOrderId'))
            if order:
                self.buy_orders.remove(delete_order)

        # 没有卖单的时候.
        if len(self.sell_orders) <= 0:
            if ask_price > 0:
                price = round_to(ask_price * (1 + float(config.gap_percent)), float(config.min_price))
                order = self.http_client.place_order(symbol=config.symbol,order_side=OrderSide.SELL, order_type=OrderType.LIMIT, quantity=quantity,price=price)
                if order:
                    self.sell_orders.append(order)

        elif len(self.sell_orders) > int(config.max_orders): # 最多允许的挂单数量.
            # 订单数量比较多的时候.
            self.sell_orders.sort(key=lambda x: x['price'], reverse=True)  # 最高价到最低价

            delete_order = self.sell_orders[0]
            order = self.http_client.cancel_order(delete_order.get('symbol'),
                                                  client_order_id=delete_order.get('clientOrderId'))
            if order:
                self.sell_orders.remove(delete_order)

