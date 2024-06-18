#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""

   针对指定数字货币，价格监控


"""
import sys
import threading
import websocket
import requests
import json
import time
import logging

from utils import config
from utils import utility, round_to, dingding_info
from enum import Enum
from collections import deque

# websocket stream中的交易对均为小写
#MONITOR_STREAMS = ['btcusd_perp@kline_5m','ethusd_perp@kline_1h']
#MONITOR_STREAMS = ['btcusdt@kline_5m']

format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=format, filename='monitor_log.txt')
logger = logging.getLogger('binance')

class RequestMethod(Enum):
    """
    请求的方法.
    """
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'


class Interval(Enum):
    """
    请求的K线数据..
    """
    MINUTE_1 = '1m'
    MINUTE_3 = '3m'
    MINUTE_5 = '5m'
    MINUTE_15 = '15m'
    MINUTE_30 = '30m'
    HOUR_1 = '1h'
    HOUR_2 = '2h'
    HOUR_4 = '4h'
    HOUR_6 = '6h'
    HOUR_8 = '8h'
    HOUR_12 = '12h'
    DAY_1 = '1d'
    DAY_3 = '3d'
    WEEK_1 = '1w'
    MONTH_1 = '1M'

class MarketHttpClient(object):

    def __init__(self, market="spot", proxy_host=None, proxy_port=0, timeout=5, try_counts=5):
        if market == "spot":
            self.host = "https://api.binance.com"
        if market == "um_future":
            self.host = "https://fapi.binance.com"
        if market == "cm_future":
            self.host = "https://dapi.binance.com"    
        self.market  = market
        self.timeout = timeout
        self.try_counts = try_counts # 失败尝试的次数.
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port

    @property
    def proxies(self):
        if self.proxy_host and self.proxy_port:
            proxy = f"http://{self.proxy_host}:{self.proxy_port}"
            return {"http": proxy, "https": proxy}

        return None

    def build_parameters(self, params: dict):
        keys = list(params.keys())
        keys.sort()
        return '&'.join([f"{key}={params[key]}" for key in params.keys()])

    def request(self, req_method: RequestMethod, path: str, requery_dict=None):
        url = self.host + path

        if requery_dict:
            url += '?' + self.build_parameters(requery_dict)
        # headers = {"X-MBX-APIKEY": self.api_key}
        
        for i in range(0, self.try_counts):
            try:
                response = requests.request(req_method.value, url=url, timeout=self.timeout, proxies=self.proxies)
                if response.status_code == 200:
                    return response.json()
                else:
                    print(response.json(), response.status_code)
            except Exception as error:
                print(f"请求:{path}, 发生了错误: {error}")
                time.sleep(3)

    def get_server_time(self):
        if self.market == "spot":
            path = "/api/v3/time"
        if self.market == "um_future":
            path = "/fapi/v1/time"
        if self.market == "cm_future":
            path = "/dapi/v1/time"
        return self.request(req_method=RequestMethod.GET, path=path)

    def get_exchange_info(self):

        """
        return:
         the exchange info in json format:
        {'timezone': 'UTC', 'serverTime': 1570802268092, 'rateLimits':
        [{'rateLimitType': 'REQUEST_WEIGHT', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 1200},
        {'rateLimitType': 'ORDERS', 'interval': 'MINUTE', 'intervalNum': 1, 'limit': 1200}],
         'exchangeFilters': [], 'symbols':
         [{'symbol': 'BTCUSDT', 'status': 'TRADING', 'maintMarginPercent': '2.5000', 'requiredMarginPercent': '5.0000',
         'baseAsset': 'BTC', 'quoteAsset': 'USDT', 'pricePrecision': 2, 'quantityPrecision': 3, 'baseAssetPrecision': 8,
         'quotePrecision': 8,
         'filters': [{'minPrice': '0.01', 'maxPrice': '100000', 'filterType': 'PRICE_FILTER', 'tickSize': '0.01'},
         {'stepSize': '0.001', 'filterType': 'LOT_SIZE', 'maxQty': '1000', 'minQty': '0.001'},
         {'stepSize': '0.001', 'filterType': 'MARKET_LOT_SIZE', 'maxQty': '1000', 'minQty': '0.001'},
         {'limit': 200, 'filterType': 'MAX_NUM_ORDERS'},
         {'multiplierDown': '0.8500', 'multiplierUp': '1.1500', 'multiplierDecimal': '4', 'filterType': 'PERCENT_PRICE'}],
         'orderTypes': ['LIMIT', 'MARKET', 'STOP'], 'timeInForce': ['GTC', 'IOC', 'FOK', 'GTX']}]}

        """
        if self.market == "spot":
            path = "/api/v3/exchangeInfo"
        if self.market == "um_future":
            path = "/fapi/v1/exchangeInfo"
        if self.market == "cm_future":
            path = "/dapi/v1/exchangeInfo"
        
        return self.request(req_method=RequestMethod.GET, path=path)

    def get_order_book(self, symbol, limit=5):
        """
        :param symbol: BTCUSDT, BNBUSDT ect, 交易对.
        :param limit: market depth.
        :return: return order_book in json 返回订单簿，json数据格式.
        """
        limits = [5, 10, 20, 50, 100, 500, 1000]
        if limit not in limits:
            limit = 5

        if self.market == "spot":
            path = "/api/v3/depth"
        if self.market == "um_future":
            path = "/fapi/v1/depth"
        if self.market == "cm_future":
            path = "/dapi/v1/depth"
        query_dict = {"symbol": symbol,
                      "limit": limit
                      }

        return self.request(RequestMethod.GET, path, query_dict)

    def get_kline(self, symbol, interval, start_time=None, end_time=None, limit=500, max_try_time=10):
        """
        获取K线数据.
        :param symbol:
        :param interval:
        :param start_time:
        :param end_time:
        :param limit:
        :param max_try_time:
        :return:
        """
        if self.market == "spot":
            path = "/api/v3/klines"
        if self.market == "um_future":
            path = "/fapi/v1/klines"
        if self.market == "cm_future":
            path = "/dapi/v1/klines"

        query_dict = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }

        if start_time:
            query_dict['startTime'] = start_time

        if end_time:
            query_dict['endTime'] = end_time

        for i in range(max_try_time):
            data = self.request(RequestMethod.GET, path, query_dict)
            if isinstance(data, list) and len(data):
                return data

    def get_latest_price(self, symbol):
        """
        :param symbol: 获取最新的价格.
        :return: {'symbol': 'BTCUSDT', 'price': '9168.90000000'}

        """
        if self.market == "spot":
            path = "/api/v3/ticker/price"
        if self.market == "um_future":
            path = "/fapi/v1/ticker/price"
        if self.market == "cm_future":
            path = "/dapi/v1/ticker/price"
        query_dict = {"symbol": symbol}
        return self.request(RequestMethod.GET, path, query_dict)

    def get_ticker(self, symbol):
        """
        :param symbol: 交易对
        :return: 返回的数据如下:
        {
        'symbol': 'BTCUSDT', 'bidPrice': '9168.50000000', 'bidQty': '1.27689900',
        'askPrice': '9168.51000000', 'askQty': '0.93307800'
        }
        """
        if self.market == "spot":
            path = "/api/v3/ticker/bookTicker"
        if self.market == "um_future":
            path = "/fapi/v1/ticker/bookTicker"
        if self.market == "cm_future":
            path = "/dapi/v1/ticker/bookTicker"
        query_dict = {"symbol": symbol}
        return self.request(RequestMethod.GET, path, query_dict)


class BinanceMonitor(object):

    def __init__(self, market="spot", proxy_host=None, proxy_port=0, timeout=5, try_counts=5):
        self.market = market
        self.http_client = MarketHttpClient(market=market,  
                                           proxy_host=proxy_host, 
                                           proxy_port=proxy_port,
                                           timeout=timeout,
                                           try_counts=try_counts)
        self.timeout = timeout
        self.try_counts = try_counts  # 失败尝试的次数.
        self.reconnect_count = 0      # reconnect counter

        self.short: int = 6
        self.medium: int = 12
        self.long: int = 24

        self.checkInterval: int = 4_000  # K线最后检测交叉的区间

        self.latest_klines = {}  #存储最近的self.long长度的k线数据， 即当前未定型K线之前的self.long长度的k线数据
        self.sma  = {}       #当前未定型K线之前一个 short MA值
        self.mma  = {}       #当前未定型K线之前一个 medium MA值  
        self.lma  = {}       #当前未定型K线之前一个 long MA值   
        self.ssum = {}       #ssum， msum，lsum对应sma，mma，lma的统计累计值，减少每次的乘法运算可能带来的累积误差  
        self.msum = {}
        self.lsum = {}

    def get_ws_client(self):
        if self.market == "spot":
            wss = "wss://data-stream.binance.vision/stream?streams="
        if self.market == "um_future":
            wss = "wss://fstream.binance.com/stream?streams="
        if self.market == "cm_future":
            wss = "wss://dstream.binance.com/stream?streams="
        wss = wss + '/'.join([f"{stream}" for stream in config.streams])
        #print(f"wss = {wss}")
        return websocket.WebSocketApp(wss, 
                                on_message=self.on_message,
                                on_error=self.on_error,
                                on_close=self.on_close)
                                    
    def on_open(self, ws):
        print("Websocket connection open")

    def on_message(self, ws, message):
        data = json.loads(message)
        if 'stream' in data:
            if data['data']['e'] == 'kline':
                self.handle_kline(data['stream'],data['data'])
            if data['data']['e'] == "bookTicker":
                bid_price = float(data['data']['b'])
                ask_price = float(data['data']['a'])
                print(f"{data['data']['s']} bid_price = {bid_price}, ask_price = {ask_price}")
            
    def on_error(self, ws, error):
        print(type(error))
        print(error)
        logging.info(type(error))
        logging.info(error)
        self.reconnect_count += 1
        while self.reconnect_count <= self.try_counts:
            print("将在5秒后进行第%d次重连"%self.reconnect_count)
            time.sleep(5)
            self.run()


    def on_close(self, ws):
        print("Websocket connection closed")

    def run(self):
        # kwebsocket.enableTrace(True)
        self.ws_client = self.get_ws_client() 
        try:
            self.ws_client.run_forever()
        except KeyboardInterrupt:
            self.ws_client.close()
        except:
            self.ws_client.close()  

    def _check_cross(self, data, prev_sma: float, prev_mma: float, prev_lma: float, sma: float, mma: float, lma: float, flag: bool):
        """
         : 检查短中长三条MA线是否出现交叉
        """
        cross_msg = None
        if prev_sma < prev_lma and sma >= lma :
            cross_msg = "一级买点: MA({})上升穿MA({})".format(self.short, self.long)
        if prev_sma > prev_lma and sma <= lma :
            cross_msg = "一级卖点: MA({})下滑穿MA({})".format(self.short, self.long)
        if prev_sma < prev_mma and sma >= mma and mma >= lma:
            cross_msg = "二级买点: MA({})上升穿MA({})".format(self.short, self.medium)
        if prev_sma > prev_mma and sma <= mma and mma <= lma:
            cross_msg = "二级卖点: MA({})下滑穿MA({})".format(self.short, self.medium)

        if cross_msg is not None:
            if self.market == "spot":
                market_msg = "   "
            if self.market == "um_future":
                market_msg = "U本位"    
            if self.market == "cm_future":
                market_msg = "币本位"
            symbol_msg = f"{data['k']['s']} {market_msg}"
            if flag :
                cross_msg = f"K线({data['k']['i']})" + "已经产生" + cross_msg
            else:
                cross_msg = f"K线({data['k']['i']})" + "即将产生" + cross_msg
            dingding_info(config.dingding_token, config.dingding_prompt, symbol_msg, cross_msg)

    #
    # note: Binance cm_future的get_kline存在bug，输入的start_time不起作用，只返回当前K线的前limit条K线
    #
    def build_latest_klines(self, stream, data):
        print("build latest klines")
        candle = data['k']
        if self.market == "cm_future":
            klines = self.http_client.get_kline(symbol=candle['s'],interval=candle['i'], limit=1+self.long)
            if len(klines) != self.long + 1:
                print(f"get_kline没有获得最近{1+self.long}根K线数据!")
                return
            klines = klines[0:self.long]
        else:
            klines = self.http_client.get_kline(symbol=candle['s'],interval=candle['i'], start_time=candle['t']-self.long*(candle['T']-candle['t']+1), limit=self.long)
            if len(klines) != self.long:
                print(f"get_kline没有获得最近{self.long}根K线数据!")
                return

        self.latest_klines[stream] = deque(klines)
        # 计算当前K线前一根对应的sma， mma, lma值，这些值在当前一个interval周期内是固定值。
        klines = deque(reversed(self.latest_klines[stream]))
        self.lsum[stream] = float(0)
        for i in range(0, self.long):
            if i == self.short:
                self.ssum[stream] = self.lsum[stream]
            if i == self.medium:
                self.msum[stream] = self.lsum[stream]
            self.lsum[stream] += float(klines[i][4])
        self.sma[stream] = self.ssum[stream] / self.short
        self.mma[stream] = self.msum[stream] / self.medium
        self.lma[stream] = self.lsum[stream] / self.long            

    def handle_kline(self, stream, data):
        candle = data['k']
        #print (f"{candle['s']} K线({candle['i']}) price = {float(candle['c'])}")
        #print(f"data['E'] = {data['E']},candle['t'] = {candle['t']}, candle['T'] = {candle['T']}")
        #return
                 
        if stream in self.latest_klines.keys():
            #print(f"candle['t'] ={candle['t']}, latest_klines[stream][-1][6] = {self.latest_klines[stream][-1][6]}")
            if candle['t'] == self.latest_klines[stream][-1][6]+1:
                if candle['x']:
                    # 跨入新K线interval中， latest_klines需更新，self.sma, self.mma, self.lma均需重新计算
                    self.ssum[stream] += float(candle['c']) - float (self.latest_klines[stream][-self.short][4])                        
                    self.msum[stream] += float(candle['c']) - float (self.latest_klines[stream][-self.medium][4])
                    self.lsum[stream] += float(candle['c']) - float (self.latest_klines[stream][0][4])
                    sma = self.sma[stream]
                    mma = self.mma[stream]
                    lma = self.lma[stream]
                    self.sma[stream] = self.ssum[stream] / self.short
                    self.mma[stream] = self.msum[stream] / self.medium
                    self.lma[stream] = self.lsum[stream] / self.long
                    print(f"{candle['s']} price = {float(candle['c'])} K线({candle['i']})完毕 MA({self.short}): {self.sma[stream]}, MA({self.medium}): {self.mma[stream]}, MA({self.long}): {self.lma[stream]}")
                    self._check_cross(data, sma, mma, lma, self.sma[stream], self.mma[stream], self.lma[stream], True)
                    # 先进先出原则，移除latest_klines最左端K线数据，将当前K线加入latest_klines最右端。
                    self.latest_klines[stream].popleft()
                    self.latest_klines[stream].append([candle['t'],candle['o'],candle['h'],candle['l'],
                                                       candle['c'],candle['v'],candle['T'],candle['q'],
                                                       candle['n'],candle['V'],candle['Q'],candle['B']])

                else:
                    # 计算当前K线的sma， mma， lma                
                    sma = (self.ssum[stream] + float(candle['c']) - float (self.latest_klines[stream][-self.short][4])) / self.short
                    mma = (self.msum[stream] + float(candle['c']) - float (self.latest_klines[stream][-self.medium][4])) / self.medium
                    lma = (self.lsum[stream] + float(candle['c']) - float (self.latest_klines[stream][0][4])) / self.long
                    print(f"{candle['s']} price = {float(candle['c'])} K线({candle['i']}) MA({self.short}): {sma}, MA({self.medium}): {mma}, MA({self.long}): {lma}")
                    if data['E'] + self.checkInterval > candle['T']:
                        # 最后10秒内进行MA线交叉判定
                        self._check_cross(data, self.sma[stream], self.mma[stream], self.lma[stream], sma, mma, lma, False)
            else:
                self.build_latest_klines(stream, data)      
                if candle['t'] == self.latest_klines[stream][-1][6]+1:
                    # 计算当前K线的sma， mma， lma                
                    sma = (self.ssum[stream] + float(candle['c']) - float (self.latest_klines[stream][-self.short][4])) / self.short
                    mma = (self.msum[stream] + float(candle['c']) - float (self.latest_klines[stream][-self.medium][4])) / self.medium
                    lma = (self.lsum[stream] + float(candle['c']) - float (self.latest_klines[stream][0][4])) / self.long
                    print(f"{candle['s']} price = {float(candle['c'])} K线({candle['i']}) MA({self.short}): {sma}, MA({self.medium}): {mma}, MA({self.long}): {lma}")  
                    if data['E'] + self.checkInterval > candle['T']:
                        # 最后10秒内进行MA线交叉判定
                        self._check_cross(data, self.sma[stream], self.mma[stream], self.lma[stream], sma, mma, lma, False)  
        else:
            self.build_latest_klines(stream, data)
            if stream in self.latest_klines.keys():
                # 计算当前K线的sma， mma， lma                
                sma = (self.ssum[stream] + float(candle['c']) - float (self.latest_klines[stream][-self.short][4])) / self.short
                mma = (self.msum[stream] + float(candle['c']) - float (self.latest_klines[stream][-self.medium][4])) / self.medium
                lma = (self.lsum[stream] + float(candle['c']) - float (self.latest_klines[stream][0][4])) / self.long
                print(f"{candle['s']} price = {float(candle['c'])} K线({candle['i']}) MA({self.short}): {sma}, MA({self.medium}): {mma}, MA({self.long}): {lma}")
            

if __name__ == '__main__':
    # Binance monitor

    if len(sys.argv) < 2 :
        print("Please input config file path")
        exit(0)

    config.loads(sys.argv[1])
    
    monitor = BinanceMonitor(market=config.market)
    monitor.run()
    
   
