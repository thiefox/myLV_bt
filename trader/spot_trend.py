#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Module: spot trend trader
"""


from binance import BinanceSpotHttp, OrderStatus, OrderType, OrderSide, Interval
from com_utils.config import Config as config
from com_utils import utility
from enum import Enum
import logging
from datetime import datetime
#from queue import Queue
from collections import deque

# 现货趋势策略，基于K线的金叉死叉进行交易
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

        """
         :K线信息设置
        """
        self.kline_interval = Interval.HOUR_1
        # self.short: int = 7
        # self.medium: int = 25
        # self.long: int = 99
        # 取6小时/12小时/24小时的K线为金叉死叉判断依据
        self.short: int = 6         #短周期MA线长度，时间可以为小时/日/周/月
        self.medium: int = 12       #中周期MA线长度
        self.long: int = 24         #长周期MA线长度
        self.intervalTS: int = 0   #当前k线的interval time ticks 
        self.latest_klines = None  #存储最近的self.long长度的k线数据， 即当前未定型K线之前的self.long长度的k线数据
        self.sma: float = 0       #当前未定型K线之前一个 short MA值
        self.mma: float = 0       #当前未定型K线之前一个 medium MA值  
        self.lma: float = 0       #当前未定型K线之前一个 long MA值   
        self.ssum: float = 0      #ssum， msum，lsum对应sma，mma，lma的统计累计值，减少每次的乘法运算可能带来的累积误差  
        self.msum: float = 0
        self.lsum: float = 0

    # 获取当前的买一卖一价格
    def get_bid_ask_price(self) -> tuple:

        ticker = self.http_client.get_ticker(config.symbol)

        bid_price = 0
        ask_price = 0
        if ticker:
            bid_price = float(ticker.get('bidPrice', 0))
            ask_price = float(ticker.get('askPrice', 0))

        return bid_price, ask_price
    
    # short/medium/long三条MA线交叉检查
    # 前三个参数是之前的ma值，后三个参数是当前的ma值
    def _check_cross(self, prev_sma: float, prev_mma: float, prev_lma: float, sma: float, mma: float, lma: float, passed: bool):
        """
         : 检查短中长三条MA线是否出现交叉
        """
        cross_msg = None
        # 金叉：短期MA线上升穿过长期MA线，买入信号
        if prev_sma < prev_lma and sma >= lma :
            cross_msg = "一级买点: MA({})上升穿MA({})".format(self.short, self.long)
        # 死叉：短期MA线下滑穿过长期MA线，卖出信号
        if prev_sma > prev_lma and sma <= lma :
            cross_msg = "一级卖点: MA({})下滑穿MA({})".format(self.short, self.long)
        # 二级买卖点：短期MA线上升穿过中期MA线，买入信号
        if prev_sma < prev_mma and sma >= mma and mma >= lma:
            cross_msg = "二级买点: MA({})上升穿MA({})".format(self.short, self.medium)
        # 二级买卖点：短期MA线下滑穿过中期MA线，卖出信号
        if prev_sma > prev_mma and sma <= mma and mma <= lma:
            cross_msg = "二级卖点: MA({})下滑穿MA({})".format(self.short, self.medium)

        if cross_msg is not None:
            if passed :
                cross_msg = "已经产生" + cross_msg
            else:
                cross_msg = "即将产生" + cross_msg
            utility.dingding_info(config.dingding_token, config.dingding_prompt, config.symbol, cross_msg)

    # 这个才是趋势交易的核心逻辑？
    def handle_data(self):
        if self.latest_klines is None:
            # 向服务器查询self.long+1根K线数据， 其中最后一根是未定型K线，前self.long根已定型。
            klines = self.http_client.get_kline(symbol=config.symbol, interval=self.kline_interval, limit=1+self.long)  
            if len(klines) == 1 + self.long:
                # 当前K线数据（未定型）
                now_kline = klines[-1] 
                # 从K线数据获取K线的interval time ， in unix time tickers
                # [6]是K线的结束时间， [0]是K线的开始时间
                self.intervalTS = now_kline[6] - now_kline[0] + 1   # 左开右闭区间，所以要+1。intervalTS是K线的时间长度
                # 将前self.long根已定型的K线数据保存在latest_klines, +1根已丢弃
                self.latest_klines = deque(klines[0:self.long])
                # 计算当前K线前一根对应的sma， mma, lma值，这些值在当前一个interval周期内是固定值。
                klines = deque(reversed(self.latest_klines))
                for i in range(0, self.long):
                    if i == self.short:
                        self.ssum = self.lsum
                    if i == self.medium:
                        self.msum = self.lsum
                    # klines[i][4]是K线的收盘价
                    # 所以lsum就是最近self.long根K线的收盘价之和
                    self.lsum += float(klines[i][4])    
                # 所以macd的值就是最近self.long根K线的收盘价之和除以self.long？
                # 加权在哪里体现？-> 这个模型是简单的K线移动平均线模型，不是MACD也没有加权。
                self.sma = self.ssum / self.short
                self.mma = self.msum / self.medium
                self.lma = self.lsum / self.long
                # 以当前未定型的K线数据来估算当前K线的sma，mma，lma值
                # 去掉最早的K线数据，加上当前K线数据，计算sma，mma，lma
                lma = (self.lsum + float(now_kline[4]) - float (self.latest_klines[0][4])) / self.long
                mma = (self.msum + float(now_kline[4]) - float (self.latest_klines[-self.medium][4])) / self.medium
                sma = (self.ssum + float(now_kline[4]) - float (self.latest_klines[-self.short][4])) / self.short
                print(f"MA({self.short}): {sma}, MA({self.medium}): {mma}, MA({self.long}): {lma}")
                # 未定型K线的最后1/10的interval区间判断三条MA线是否交叉
                # [X][6]是K线的结束时间， [X][0]是K线的开始时间
                if self.http_client.get_current_timestamp() > self.latest_klines[-1][6] + self.intervalTS*9/10:
                    self._check_cross(self.sma, self.mma, self.lma, sma, mma, lma, False)
            else:
                print(f"get_kline没有获得最近{1+self.long}根K线数据!")

        else: 
            # 向服务器查询当前K线数据
            kline = self.http_client.get_kline(symbol=config.symbol, interval=self.kline_interval, limit=1)
            if len(kline) == 1:
                # [X][0]是K线的开始时间，为什么是不等于而不是大于
                # 这个条件满足的话，说明之前的未定K线已完成（完成态）。
                if kline[0][0] != self.latest_klines[-1][0] + self.intervalTS:
                    # 问题1：上面这个条件满足说明是有跳线吗？即可能因为网络原因，漏过了N条K线数据？
                    # 跨入新K线interval中， latest_klines需更新，self.sma, self.mma, self.lma均需重新计算
                    # 向服务器查询lastest_klines之后的一根K线数据，为什么只拿一根，就不会有多根？
                    # 问题2：漏过了N条K线，下面只拿一条是为了简化处理？
                    prev_kline = self.http_client.get_kline(symbol=config.symbol, interval=self.kline_interval, \
                        start_time=self.latest_klines[-1][0]+self.intervalTS, limit=1)
                    if len(prev_kline) == 1:  
                        # 窗口向右移动1格                                              
                        self.ssum += float(prev_kline[0][4]) - float (self.latest_klines[-self.short][4])                        
                        self.msum += float(prev_kline[0][4]) - float (self.latest_klines[-self.medium][4])
                        self.lsum += float(prev_kline[0][4]) - float (self.latest_klines[0][4])
                        sma = self.sma
                        mma = self.mma
                        lma = self.lma
                        self.sma = self.ssum / self.short
                        self.mma = self.msum / self.medium
                        self.lma = self.lsum / self.long
                        # 问题3：如果拿到的只是一根历史数据跳线，为什么还要判断是否交叉（会触发买卖action）？因为这根跳线并不是当前最新K线啊？？？
                        self._check_cross(sma, mma, lma, self.sma, self.mma, self.lma, True)
                        # 先进先出原则，移除latest_klines最左端K线数据，将prev K线加入latest_klines最右端。
                        self.latest_klines.popleft()
                        self.latest_klines.append(prev_kline[0])
                        # 问题4：这里是不是应该return? 不然到问题5还会再触发check_cross
                    else:
                        print("get_kline没有获得prev K线的数据")
                        return
                    
                # 计算当前K线的sma， mma， lma        
                # 未定K线的数据更新（但仍处于未定态）     
                sma = (self.ssum + float(kline[0][4]) - float (self.latest_klines[-self.short][4])) / self.short
                mma = (self.msum + float(kline[0][4]) - float (self.latest_klines[-self.medium][4])) / self.medium
                lma = (self.lsum + float(kline[0][4]) - float (self.latest_klines[0][4])) / self.long
                print(f"MA({self.short}): {sma}, MA({self.medium}): {mma}, MA({self.long}): {lma}")
                # 当前K线的最后1/10的interval区间判断三条MA线是否交叉
                # 问题5：为什么要当前K线窗口的最后1/10的interval区间判断三条MA线是否交叉？？？
                if self.http_client.get_current_timestamp() > kline[0][0] + self.intervalTS*9/10:
                    self._check_cross(self.sma, self.mma, self.lma, sma, mma, lma, False)
            else:
                print("get_kline没有获得当前K线数据!")

    # 这个函数怎么是网格交易的逻辑？？？跟趋势无关？？？
    def trend_trader(self):
        """
        执行核心逻辑，趋势交易的逻辑.
        :return:
        """
        # 若刚启动，构建short，medium，long MA线跟踪
        if self.mma is None:
            # 请求一个长线周期（self.long）的K线数据
            # 问题：为什么要请求self.long长度的K线数据？？？下面根本没有用到。如果别的地方需要，为什么不在别的地方请求？？？
            self.latest_klines = self.http_client.get_kline(symbol=config.symbol, interval= Interval.HOUR_1, limit=self.long)


        bid_price, ask_price = self.get_bid_ask_price()
        print(f"bid_price: {bid_price}, ask_price: {ask_price}")

        quantity = utility.round_to(float(config.quantity), float(config.min_qty))

        self.buy_orders.sort(key=lambda x: float(x['price']), reverse=True)  # 最高价到最低价.
        self.sell_orders.sort(key=lambda x: float(x['price']), reverse=True)  # 最高价到最低价.
        print(f"buy orders: {self.buy_orders}")
        print("------------------------------")
        print(f"sell orders: {self.sell_orders}")

        buy_delete_orders = []  # 需要删除买单
        sell_delete_orders = [] # 需要删除的卖单

        # 买单逻辑,检查成交的情况.
        for buy_order in self.buy_orders:
            check_order = self.http_client.get_order(buy_order.get('symbol', config.symbol), \
                client_order_id=buy_order.get('clientOrderId'))
            if check_order:     #问题：条件不满足，说明什么呢？服务端已经查不到该订单了？那怎么处理？
                if check_order.get('status') == OrderStatus.CANCELED.value:
                    buy_delete_orders.append(buy_order)
                    print(f"buy order status was canceled: {check_order.get('status')}")
                elif check_order.get('status') == OrderStatus.FILLED.value:
                    # 买单成交，挂卖单.
                    # logging.info(f"买单成交时间: {datetime.now()}, 价格: {check_order.get('price')}, 数量: {check_order.get('origQty')}")
                    log_msg = "买单成交时间: {}, 价格: {}, 数量: {}".format(datetime.now(), check_order.get('price'), check_order.get('origQty'))
                    logging.info(log_msg)
                    utility.dingding_info(config.dingding_token, config.dingding_prompt, config.symbol, log_msg)

                    sell_price = utility.round_to(float(check_order.get("price")) * (1 + float(config.gap_percent)), float(config.min_price))

                    if 0 < sell_price < ask_price:
                        # 防止价格
                        sell_price = utility.round_to(ask_price, float(config.min_price))

                    new_sell_order = self.http_client.place_order(symbol=config.symbol, order_side=OrderSide.SELL, order_type=OrderType.LIMIT, quantity=quantity, price=sell_price)
                    if new_sell_order:
                        buy_delete_orders.append(buy_order)
                        self.sell_orders.append(new_sell_order)

                    buy_price = utility.round_to(float(check_order.get("price")) * (1 - float(config.gap_percent)),
                                     config.min_price)
                    if buy_price > bid_price > 0:
                        buy_price = utility.round_to(bid_price, float(config.min_price))

                    new_buy_order = self.http_client.place_order(symbol=config.symbol, order_side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=quantity, price=buy_price)
                    if new_buy_order:
                        self.buy_orders.append(new_buy_order)

                elif check_order.get('status') == OrderStatus.NEW.value:
                    print("buy order status is: New")
                else:
                    print(f"buy order status is not above options: {check_order.get('status')}")

        # 过期或者拒绝的订单删除掉.
        for delete_order in buy_delete_orders:
            self.buy_orders.remove(delete_order)

        # 卖单逻辑, 检查卖单成交情况.
        for sell_order in self.sell_orders:

            check_order = self.http_client.get_order(sell_order.get('symbol', config.symbol),
                                               client_order_id=sell_order.get('clientOrderId'))
            if check_order:
                if check_order.get('status') == OrderStatus.CANCELED.value:
                    sell_delete_orders.append(sell_order)

                    print(f"sell order status was canceled: {check_order.get('status')}")
                elif check_order.get('status') == OrderStatus.FILLED.value:
                    log_msg = "卖单成交时间: {}, 价格: {}, 数量: {}".format(datetime.now(), check_order.get('price'), check_order.get('origQty'))
                    logging.info(log_msg)
                    utility.dingding_info(config.dingding_token, config.dingding_prompt, config.symbol, log_msg)

                    # 卖单成交，先下买单.
                    buy_price = utility.round_to(float(check_order.get("price")) * (1 - float(config.gap_percent)), float(config.min_price))
                    if buy_price > bid_price > 0:
                        buy_price = utility.round_to(bid_price, float(config.min_price))

                    new_buy_order = self.http_client.place_order(symbol=config.symbol, order_side=OrderSide.BUY,
                                                             order_type=OrderType.LIMIT, quantity=quantity, price=buy_price)
                    if new_buy_order:
                        sell_delete_orders.append(sell_order)
                        self.buy_orders.append(new_buy_order)

                    sell_price = utility.round_to(float(check_order.get("price")) * (1 + float(config.gap_percent)), float(config.min_price))

                    if 0 < sell_price < ask_price:
                        # 防止价格
                        sell_price = utility.round_to(ask_price, float(config.min_price))

                    new_sell_order = self.http_client.place_order(symbol=config.symbol, order_side=OrderSide.SELL,
                                                                 order_type=OrderType.LIMIT, quantity=quantity,
                                                                 price=sell_price)
                    if new_sell_order:
                        self.sell_orders.append(new_sell_order)

                elif check_order.get('status') == OrderStatus.NEW.value:
                    print("sell order status is: New")
                else:
                    print(f"sell order status is not in above options: {check_order.get('status')}")

        # 过期或者拒绝的订单删除掉.
        for delete_order in sell_delete_orders:
            self.sell_orders.remove(delete_order)

        # 没有买单的时候.
        if len(self.buy_orders) <= 0:
            if bid_price > 0:
                price = utility.round_to(bid_price * (1 - float(config.gap_percent)), float(config.min_price))
                buy_order = self.http_client.place_order(symbol=config.symbol,order_side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=quantity,price=price)
                if buy_order:
                    self.buy_orders.append(buy_order)

        elif len(self.buy_orders) > int(config.max_orders): # 最多允许的挂单数量.
            # 订单数量比较多的时候.
            self.buy_orders.sort(key=lambda x: float(x['price']), reverse=False)  # 最低价到最高价

            delete_order = self.buy_orders[0]
            order = self.http_client.cancel_order(delete_order.get('symbol'), client_order_id=delete_order.get('clientOrderId'))
            if order:
                self.buy_orders.remove(delete_order)

        # 没有卖单的时候.
        if len(self.sell_orders) <= 0:
            if ask_price > 0:
                price = utility.round_to(ask_price * (1 + float(config.gap_percent)), float(config.min_price))
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

