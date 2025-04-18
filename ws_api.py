#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import threading
import websocket
import requests
import json
import time
import logging
from datetime import datetime

from com_utils import config
from com_utils import utility
from enum import Enum
from collections import deque

import websocket

str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 

format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=format, filename='log/ws_api_{}.txt'.format(str_now))
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

class MarketWebSocketClient(object):
    def __init__(self, market="spot", proxy_host=None, proxy_port=0, timeout=10, try_counts=5):
        self.host = "wss://ws-api.binance.com:443/ws-api/v3"
        self.market = market
        self.timeout = timeout
        self.try_counts = try_counts  # 失败尝试的次数.
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.ws = websocket.create_connection(self.host, timeout=self.timeout)
        print('连接状态={}'.format(self.ws.getstatus()))
        

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

    def post_kline(self, begin:int=0):
        """
        获取K线数据.
        :param symbol:
        :param interval:
        :param start_time:
        :param end_time:
        :param limit:
        :return:
        """

        query_dict = dict()
        str_now = datetime.strftime(datetime.now(), '%Y%m%d%H%M%S')
        query_dict['id'] = int(str_now)
        query_dict['method'] = 'klines'
        param_dict = {
            "symbol": 'BTCUSDT',
            "interval": '4h',
            "limit": 500
        }

        s_start = "2024-1-1 00:00:00"
        if begin == 0:
            s_start = datetime.strftime(datetime.now(), '%Y-%m-%d 00:00:00')
            #s_start = s_start + ' 00:00:00'
        else :
            s_start = utility.timestamp_to_string(begin)
        print('start_time={}'.format(s_start))
        param_dict['startTime'] = utility.string_to_timestamp(s_start)

        s_end = '2024-1-2 00:00:00'
        timeArray = time.strptime(s_end, "%Y-%m-%d %H:%M:%S")
        # 转换为时间戳
        end_time = int(time.mktime(timeArray))        
        #param_dict['endTime'] = end_time
        param_dict['limit'] = 5
        
        query_dict['params'] = param_dict

        request = json.dumps(query_dict)
        print('URL request={}'.format(request))
        self.ws.send(request)
        return 

class BinanceSpider(object):

    def __init__(self, config : config.Config , proxy_host=None, proxy_port=0, timeout=5, try_counts=5):
        self.config = config
        self.market = self.config.market
        
        # 内置http client和websocket client2个数据通道
        self.http_client = MarketHttpClient(market=config.market,  
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

    def gen_kline_request(self, symbol, interval, start_time=None, end_time=None, limit=500):
        return self.http_client.get_kline(symbol, interval, start_time, end_time, limit)

    def get_ws_client(self) -> websocket.WebSocketApp:
        #现货的websocket API地址
        #如拿K线的历史数据，可以用wss://data.binance.vision
        wss = 'wss://ws-api.binance.com/ws-api/v3'
            
        wss = wss + '/'.join([f"{stream}" for stream in self.config.streams])
        print('wss={}'.format(wss))
        return websocket.WebSocketApp(wss, 
                                on_message=self.on_message,
                                on_error=self.on_error,
                                on_close=self.on_close)
                                    
    def on_open(self, ws):
        print("Websocket connection open")

    def on_message(self, ws, message : str):
        print('time={}, get a message'.format(datetime.now()))
        data = json.loads(message)
        if 'stream' in data:
            print('time={}, receive a ({}) message'.format(datetime.now(), data['stream']))
            print('data={}'.format(data))
            # K线消息
            if data['stream'].lower().find('kline') >= 0:
                self.handle_kline(data['stream'], data['data'])
            # 买一卖一价消息
            elif data['stream'].lower().find('bookticker') >= 0:
                bid_price = float(data['data']['b'])
                bid_qty = float(data['data']['B'])
                ask_price = float(data['data']['a'])
                ask_qty = float(data['data']['A'])
                print("交易对={}。买单={},数量={}。卖单={}, 数量={}。".format(data['data']['s'], bid_price, bid_qty, ask_price, ask_qty))
                
        else:
            print('time={}, get a unknown message'.format(datetime.now()))
            
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

    def handle_kline(self, stream : str, data : dict):
        print('stream={}'.format(stream))
        candle = data['k']
        print (f"{candle['s']} K线({candle['i']}) price = {float(candle['c'])}")
        print(f"data['E'] = {data['E']},candle['t'] = {candle['t']}, candle['T'] = {candle['T']}")
        return

if __name__ == '__main__':
    print("Binance ws_api Monitor Start...")
    
    # Example usage
    Now = datetime.now()
    Now = Now.timestamp()
    print('当前时间={}'.format(Now))

    ws_client = MarketWebSocketClient(timeout=60)
    start = utility.string_to_timestamp('2024-1-1 00:00:00')
    finish = utility.string_to_timestamp('2024-1-2 00:00:00')
    print('start={}, finish={}'.format(start, finish))
    last = start
    while True:
        print('开始请求K线数据，开始时间={}'.format(utility.timestamp_to_string(last)))
        ws_client.post_kline(begin=last)

        # 4、获取返回结果
        result = ws_client.ws.recv()
        #print("接收结果：", result)
        result_dict = json.loads(result)
        if 'id' in result_dict:
            print('find id key')
            print('id={}'.format(result_dict['id']))
        if 'status' in result_dict:
            print('find status key')
            print('status={}'.format(result_dict['status']))
        if 'rateLimits' in result_dict:
            print('find rateLimits key')
            print('rateLimits={}'.format(result_dict['rateLimits']))
        

        if 'result' in result_dict:
            #print('find result key')
            datas = result_dict['result']
            #print('type of datas={}'.format(type(datas)))
            print('count={}'.format(len(datas)))
            
            for i in range(len(datas)):
                data = datas[i]
                print('type of data[0]={}, i={}, finish={}'.format(type(data[0]), i, finish))
                begin = utility.timestamp_to_string(data[0])
                end = utility.timestamp_to_string(data[6])
                #end1 = timestamp_to_string(data[6]+1)
                last = data[6]
                if last + 1 >= finish:
                    print('跳出循环1，begin={}, end={}, last={}, finish={}'.format(begin, end, last, finish))
                    break
                print('开始时间={}，结束时间={}，'.format(begin, end))
                print('data={}'.format(data))
            print('当前结束时间={}'.format(utility.timestamp_to_string(last)))
            last = last + 1
            if last >= finish:
                break
        else:
            break
    print('最后结束时间={}'.format(utility.timestamp_to_string(last)))
    # 5、关闭连接
    ws_client.ws.close()
    print("Binance ws_api Monitor End")


    
   
