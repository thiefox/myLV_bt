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
from datetime import datetime

from utils import config
from utils import utility
from utils import log_adapter
from enum import Enum
from collections import deque
import os

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

    def __init__(self, market="spot", proxy_host=None, proxy_port=0, timeout=5, try_counts=3):
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

    def build_parameters(self, params: dict) -> str:
        keys = list(params.keys())
        keys.sort()
        return '&'.join([f"{key}={params[key]}" for key in params.keys()])

    #请求数据并从json格式中返回数据
    def request(self, req_method: RequestMethod, path: str, requery_dict=None) -> dict:
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

    def get_server_time(self) :
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

    def get_order_book(self, symbol, limit=5) -> dict:
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

    def get_kline(self, symbol, interval, start_time=None, end_time=None, limit=500, max_try_time=10) -> list:
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
        #spot/um_future/cm_future三个市场有什么区别？
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

    def get_latest_price(self, symbol) -> dict:
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

    def get_ticker(self, symbol) -> dict:
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


class BinanceMonitor_EX(object):

    def __init__(self, market : str, streams : dict , proxy_host=None, proxy_port=0, timeout=5, try_counts=5):
        self.market = market
        self.http_client = MarketHttpClient(market=market,  
                                           proxy_host=proxy_host, 
                                           proxy_port=proxy_port,
                                           timeout=timeout,
                                           try_counts=try_counts)
        self.timeout = timeout
        self.try_counts = try_counts  # 失败尝试的次数.
        self.reconnect_count = 0      # reconnect counter
        self.streams = streams      # 订阅的交易K线列表，见配置文件
        self.ws_connected = False
        return

    def get_ws_client(self) -> websocket.WebSocketApp:
        if self.market == "spot":
            wss = "wss://data-stream.binance.vision/stream?streams="
        if self.market == "um_future":
            wss = "wss://fstream.binance.com/stream?streams="
        if self.market == "cm_future":
            wss = "wss://dstream.binance.com/stream?streams="
        wss = wss + '/'.join([f"{stream}" for stream in self.streams])
        print('基准URL={}'.format(wss))
        return websocket.WebSocketApp(wss, 
                                on_message=self.on_message,
                                on_error=self.on_error,
                                on_close=self.on_close)
                                    
    def on_open(self, ws):
        print("Websocket connection open")

    def on_message(self, ws, message):
        data = json.loads(message)
        if 'stream' in data:
            name = str(data['stream'])
            # K线消息
            if name.upper().find('BTCUSDT@KLINE') >= 0:
                begin_time = utility.timestamp_to_string(data['data']['k']['t'])
                end_time = utility.timestamp_to_string(data['data']['k']['T'])
                begin_price = round(float(data['data']['k']['o']), 2)
                end_price = round(float(data['data']['k']['c']), 2)
                high_price = round(float(data['data']['k']['h']), 2)
                low_price = round(float(data['data']['k']['l']), 2)
                interval = data['data']['k']['i']
                finished = data['data']['k']['x']
                print('收到K线{}消息（间隔={}，结束={}），开始时间={}，结束时间={}，开始价={}，结束（最后）价={}，最高价={}，最低价={}...'.format(name,
                    interval, finished, begin_time, end_time, begin_price, end_price, high_price, low_price))
                #self.handle_kline(data['stream'],data['data'])
            # 买一卖一价消息
            #elif data['data']['e'] == "bookTicker":
            elif name.upper() == 'BTCUSDT@BOOKTICKER':
                print('收到买一卖一价消息...')
                bid_price = round(float(data['data']['b']), 2)
                ask_price = round(float(data['data']['a']), 2)
                print('当前买一价={:.2f}, 卖一价={:.2f}'.format(bid_price, ask_price))
            else :
                print('重要：收到其他stream消息，数据={}'.format(data))
        else:
            print('重要：收到非stream类型消息，数据={}'.format(data))
            
    def on_error(self, ws, error):
        print('收到错误消息...')
        if type(error).__name__ == 'KeyboardInterrupt':
            print('收到键盘中断异常, conn={}...'.format(self.ws_connected))
            return
        print(type(error))
        print(error)
        logging.info(type(error))
        logging.info(error)
        self.reconnect_count += 1
        while self.reconnect_count <= self.try_counts:
            print("将在5秒后进行第%d次重连"%self.reconnect_count)
            time.sleep(5)
            self.run()

    def on_close(self, ws, *args, **kwargs):
        print("Websocket connection closed")
        self.ws_connected = False

    def run(self):
        # kwebsocket.enableTrace(True)
        self.ws_client = self.get_ws_client() 
        try:
            if self.ws_client.run_forever() :
                self.ws_connected = True
        except KeyboardInterrupt:
            print("收到键盘中断异常...")
            self.ws_client.close()
        except:
            print("收到其它异常...")
            self.ws_client.close()  
        return

def test():
    print("MACD monitor_EX Start...")
    LOG_FLAG = 0
    if LOG_FLAG == 1:
        str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        #logging.basicConfig(level=logging.INFO, format=format, filename='log/{}_{}_{}H-{}.txt'.format(symbol, year, interval, str_now))
        logging.basicConfig(level=logging.INFO, format=format, filename='log/monitor_EX-{}.txt'.format(str_now))
        logger = logging.getLogger('binance')
        logger.setLevel(logging.INFO)
        #把print输出到日志文件
        tmp_out = sys.stdout
        tmp_err = sys.stderr

        sys.stdout = log_adapter.LoggerWriter(logger, logging.INFO)
        sys.stderr = log_adapter.LoggerWriter(logger, logging.ERROR)

    CONFIG_FILE = 'config_spot.json'
    print("当前目录={}".format(os.getcwd()))
    cf = os.path.join(os.getcwd(), CONFIG_FILE)
    if not os.path.exists(cf):
        print(f"配置文件{cf}不存在")
        return
    cfg = config.Config()
    cfg.loads(cf)

    monitor = BinanceMonitor_EX(market=cfg.market, streams=cfg.streams)
    monitor.run()

    if LOG_FLAG == 1:
        sys.stdout = tmp_out
        sys.stderr = tmp_err
    print("MACD monitor_EX End.")        
    return

#test()   
