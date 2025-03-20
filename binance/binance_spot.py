#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Binance Spot http requests.
"""
import traceback
import sys
import requests
import time
from enum import Enum
from threading import Lock
import logging

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from binance.authentication import hmac_hashing, rsa_signature, ed25519_signature

class OrderStatus(Enum):
    NEW = "NEW"                             #服务商接受了该订单
    PARTIALLY_FILLED = "PARTIALLY_FILLED"   #该订单已部分成交
    FILLED = "FILLED"                       #该订单已全部成交
    CANCELED = "CANCELED"                   #该订单已取消
    PENDING_CANCEL = "PENDING_CANCEL"       #该订单在取消中？
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"                     #该订单已过期

class OrderType(Enum):
    LIMIT = "LIMIT"     #限价单，要求的参数timeInForce, quantity, price。限价单重点在于按客户预设的价格进行操作	
    MARKET = "MARKET"   #市价单，要求的参数quantity。市价单重点在于立即以当前市场价格完成买卖交易，重点在于尽快完成。
    #止损单，要求的参数quantity, stopPrice, trailingDelta。止损单重点在于当市场价格达到预设的价格时，按照预设的价格进行操作。
    #当条件满足后会下market单，所以不需要price参数。
    #STOP = "STOP"       
    #从文档里查到还有这些，但没有上面的STOP类型
    STOP_LOSS = 'STOP_LOSS'                 #止损市价单，强调到达预设价格后按市价单进行操作（卖出），重点在于尽快完成，不保证价格。
    STOP_LOSS_LIMIT = 'STOP_LOSS_LIMIT'     #限价止损单，强调到达预设价格后按限价单进行操作，重点在于按照预设价格进行操作。
    TAKE_PROFIT = 'TAKE_PROFIT'             #止盈市价单，强调到达预设价格后按市价单进行操作（卖出），重点在于尽快完成，不保证价格。
    TAKE_PROFIT_LIMIT = 'TAKE_PROFIT_LIMIT' #限价止盈单，强调到达预设价格后按限价单进行操作，重点在于按照预设价格进行操作。
    #限价做市单，强调按照预设价格进行操作，不接受市价单，重点在于按照预设价格进行操作。
    #一种订单形式, 其订单会保证成为做市订单(MAKER), 不会立刻成交进而成为TAKER。
    LIMIT_MAKER = "LIMIT_MAKER"

class RequestMethod(Enum):
    """
    请求的方法.
    """
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'

class timeInForce(Enum):
    """
    订单的有效期.
    """
    GTC = 'GTC'  # Good till Canceled。 成交为止。订单会一直有效，直到被成交或者取消。taker/maker
    IOC = 'IOC'  # Immediate Or Cancel，无法立即成交的部分就撤销。订单在失效前会尽量多的成交。taker
    FOK = 'FOK'  # Fill Or Kill，无法全部立即成交就撤销。如果无法全部成交，订单会失效。即要么全部成交，要么全部不成交。

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


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class BinanceSpotHttp(object):
    def __init__(self, api_key=None, api_secret=None, private_key=None, private_key_pass=None, host=None, proxy_host=None, proxy_port=0, timeout=5, try_counts=5):
        self.api_key = api_key
        self.api_secret = api_secret
        self.private_key = private_key
        self.private_key_pass = private_key_pass
        self.host = host if host else "https://api.binance.com"
        self.recv_window = 10000
        self.timeout = timeout
        self.__order_lock = Lock()
        #self.order_count = 1_000_000
        self.__order_index = 0
        self.try_counts = try_counts # 失败尝试的次数.
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port

    @property
    def proxies(self) -> dict:
        if self.proxy_host and self.proxy_port:
            proxy = f"http://{self.proxy_host}:{self.proxy_port}"
            return {"http": proxy, "https": proxy}

        return None

    def build_parameters(params: dict) -> str:
        keys = list(params.keys())
        keys.sort()
        return '&'.join([f"{key}={params[key]}" for key in params.keys()])

    def request(self, req_method: RequestMethod, path: str, requery_dict:dict=None, verify=False) -> dict:
        return self.request_ex(req_method, path, requery_dict, verify)
        url = self.host + path

        if verify:
            query_str = self._sign(requery_dict)
            url += '?' + query_str
        elif requery_dict:
            url += '?' + BinanceSpotHttp.build_parameters(requery_dict)
        headers = {"X-MBX-APIKEY": self.api_key}
        logging.debug('请求url={}'.format(url))
        for i in range(0, self.try_counts):
            try:
                response = requests.request(req_method.value, url=url, headers=headers, timeout=self.timeout, proxies=self.proxies)
                if response.status_code == 200:
                    return response.json()
                else:
                    logging.error('返回异常, status_code={}，data={}'.format(response.status_code, response.json()))
            except Exception as error:
                logging.error('请求失败，原因={}'.format(error))
                time.sleep(3)

    #返回一般为dict/list，看具体请求
    def request_ex(self, method : RequestMethod, url : str, params : dict = None, sign=False) :
        url = self.host + url
        headers = {"X-MBX-APIKEY": self.api_key}
        if sign:
            assert(params is not None)
            query_str = self._sign(params)
            url += '?' + query_str
        elif params is not None:
            url += '?' + BinanceSpotHttp.build_parameters(params)
        logging.debug('请求URL={}'.format(url))
        response = None
        for i in range(0, self.try_counts):
            try :
                #response = requests.get(url, params=param_dict)
                session = requests.Session()
                #session = requests.session()
                session.keep_alive = False
                retry = Retry(connect=5, backoff_factor=0.5)
                adapter = HTTPAdapter(max_retries=retry)
                session.mount('http://', adapter)
                session.mount('https://', adapter)
                logging.debug('请求数据, method={}...'.format(method.value))
                if method == RequestMethod.GET:
                    response = session.get(url, headers=headers, timeout=self.timeout, proxies=self.proxies)
                elif method == RequestMethod.POST:
                    response = session.post(url, headers=headers, timeout=self.timeout, proxies=self.proxies)
                elif method == RequestMethod.DELETE:
                    response = session.delete(url, headers=headers, timeout=self.timeout, proxies=self.proxies)
                elif method == RequestMethod.PUT:
                    response = session.put(url, headers=headers, timeout=self.timeout, proxies=self.proxies)
                logging.debug('请求数据完成')
            except requests.exceptions.ConnectionError as e:
                logging.error('ConnectionError，原因={}'.format(e))
            except requests.exceptions.ConnectTimeout as e:
                logging.error('ConnectTimeout，原因={}'.format(e))
            except requests.exceptions.Timeout as e:
                logging.error('Timeout，原因={}'.format(e))
            except Exception as e:
                logging.error('请求数据失败，原因={}'.format(e))
            finally:
                session.close()
            if response is not None:
                break
            logging.debug('尝试次数={}，休眠3秒...'.format(i))
            time.sleep(3)

        infos = None
        if response is not None:    
            infos = None
            if response.status_code == 200:
                infos = response.json()
            else :
                infos = response.json()
                #code = infos['code']
                #msg = infos['msg']
                logging.error('请求失败, status_code={}, 返回={}。'.format(response.status_code, infos))
            response.close()
        else :
            logging.error('请求失败，Response=None。')
            pass
        return infos

    def get_server_time(self) -> dict:
        # 获取服务器时间
        """
        return:
        {'serverTime': 1733207400464} ->返回的是当地时间而非UTC时间
        """
        path = '/api/v3/time'
        return self.request(req_method=RequestMethod.GET, path=path)

    def get_exchange_info(self, symbol : str) -> dict:
        # 获取交易规则和交易对信息
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
        path = '/api/v3/exchangeInfo'
        query_dict = {'symbol': symbol,
                      'showPermissionSets': 'false'}
        return self.request(RequestMethod.GET, path, query_dict)
    
    def get_exchange_params(self, symbol : str) -> dict:
        params = {'min_quantity': 0,
                  'max_quantity': 0,
                  'min_price': 0,
                  'max_price': 0}
        info = self.get_exchange_info(symbol)
        if info is not None and isinstance(info, dict) :
            if 'symbols' in info :
                symbols = info['symbols']
                for sym in symbols :
                    if sym['symbol'] == symbol :
                        if 'filters' in sym :
                            filters = sym['filters']
                            for filter in filters :
                                if 'filterType' in filter and filter['filterType'] == 'LOT_SIZE' :
                                    logging.debug('filter={}'.format(filter))
                                    if 'minQty' in filter :
                                        params['min_quantity'] = float(filter['minQty'])
                                    if 'maxQty' in filter :
                                        params['max_quantity'] = float(filter['maxQty'])
                                if 'filterType' in filter and filter['filterType'] == 'PRICE_FILTER' :
                                    if 'minPrice' in filter :
                                        params['min_price'] = float(filter['minPrice'])
                                    if 'maxPrice' in filter :
                                        params['max_price'] = float(filter['maxPrice'])

                        break
        return params

    def get_order_book(self, symbol : str, limit=5) -> dict:
        # 获取交易深度，当前的买盘价和卖盘价
        """
        :param symbol: BTCUSDT, BNBUSDT ect, 交易对.
        :param limit: market depth.
        #bidPrice: 买一价(最高买价), bidQty: 买一量, askPrice: 卖一价(最低卖价), askQty: 卖一量
        :return: return order_book in json 返回订单簿，json数据格式.
        """
        limits = [5, 10, 20, 50, 100, 500, 1000]
        if limit not in limits:
            limit = 5
        # 获取交易深度
        path = "/api/v3/depth"
        query_dict = {"symbol": symbol,
                      "limit": limit
                      }

        return self.request(RequestMethod.GET, path, query_dict)

    def get_kline(self, symbol: str, interval: Interval, start_time=None, end_time=None, limit=500, max_try_time=10) -> list:
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
        path = "/api/v3/klines"

        query_dict = {
            "symbol": symbol,
            "interval": interval.value,
            "limit": limit
        }

        if start_time:
            query_dict['startTime'] = start_time

        if end_time:
            query_dict['endTime'] = end_time

        for i in range(max_try_time):
            data = self.request(RequestMethod.GET, path, query_dict)
            if isinstance(data, list) and len(data) > 0:
                return data

    def get_latest_price(self, symbol) -> dict:
        """
        :param symbol: 获取最新的价格. 一般用于OVERVIEW多个交易对的价格.
        :return: {'symbol': 'BTCUSDT', 'price': '9168.90000000'}

        """
        path = "/api/v3/ticker/price"
        query_dict = {"symbol": symbol}
        return self.request(RequestMethod.GET, path, query_dict)

    def get_ticker(self, symbol) -> dict:
        """
        :param symbol: 交易对
        :return: 返回的字典数据如下:
        {
        'symbol': 'BTCUSDT', 'bidPrice': '9168.50000000', 'bidQty': '1.27689900',
        'askPrice': '9168.51000000', 'askQty': '0.93307800'
        }
        bid为买价，最高买价。ask为卖价，最低卖价。
        """
        # 获取当前最优的挂单(最高买单,最低卖单)
        path = "/api/v3/ticker/bookTicker"
        query_dict = {"symbol": symbol}
        return self.request(RequestMethod.GET, path, query_dict)

    #本地函数，生成一个订单ID
    def gen_client_order_id(self) -> str:
        """
        generate the client_order_id for user.
        :return:
        """
        with self.__order_lock:
            self.__order_index += 1
            return "x-A6SIDXVS" + str(self.get_current_timestamp()) + str(self.__order_index)

    #获取毫秒级本地时间
    def get_current_timestamp(self) -> int:
        """
        获取系统的时间.
        :return:
        """
        return int(time.time() * 1000)

    def _get_sign(self, query_str: str) :
        result = ''
        if self.private_key is not None:
            try:
                logging.debug('尝试ed25519签名1..., private_key={}, private_pass={}'.format(self.private_key, self.private_key_pass))
                logging.debug('query_str={}'.format(query_str))
                result = ed25519_signature(self.private_key, query_str, self.private_key_pass).decode("utf-8")
            except Exception as e:
                tb = traceback.format_exc()
                logging.error("ed25519签名失败1， 原因：={}".format(e))
                logging.error("traceback={}".format(tb))
                #info = sys.exc_info()[2]
                #logging.error("sys.exc_info={}".format(info))
                sys.exit(1)
                logging.debug('尝试RSA签名...')
                try :
                    result = rsa_signature(self.private_key, query_str, self.private_key_pass).decode("utf-8")
                except Exception as e:
                    logging.error('RSA签名失败，原因={}。'.format(e))
        else:
            try :
                result = hmac_hashing(self.api_secret, query_str)
            except Exception as e:
                logging.error('hmac_hashing失败，原因={}。'.format(e))
                logging.error('query_str={}'.format(query_str))
                sys.exit(1)
        return result

    def _sign(self, params : dict) -> str:
        """
        签名的方法， signature for the private request.
        :param params: request parameters
        :return:
        """
        query_string = BinanceSpotHttp.build_parameters(params)
        return query_string + '&signature=' + str(self._get_sign(query_string))
 
    def place_order(self, symbol: str, order_side: OrderSide, order_type: OrderType, quantity: float, price: float,
                    client_order_id: str = None, time_inforce=timeInForce.GTC, stop_price=0, quoteOrderQty:float=0) -> dict:
        """

        :param symbol: 交易对名称
        :param order_side: 买或者卖， BUY or SELL
        :param order_type: 订单类型 LIMIT or other order type.
        :param quantity: 数量
        :param price: 价格.
        :param client_order_id: 用户的订单ID
        :param time_inforce:
        :param stop_price:
        :param newOrderRespType: 订单的响应类型
        :param quoteOrderQty:市价买卖单可用quoteOrderQty参数来设置quote asset数量. 正确的quantity取决于市场的流动性与quoteOrderQty
        :return:
        """
        # 下单
        path = '/api/v3/order'

        if client_order_id is None:
            client_order_id = self.gen_client_order_id()

        params = {
            "symbol": symbol,
            "side": order_side.value,
            "type": order_type.value,
            "quantity": quantity,
            "price": price,
            "recvWindow": self.recv_window,
            "timestamp": self.get_current_timestamp(),
            "newClientOrderId": client_order_id
            #市价买卖单可用quoteOrderQty参数来设置quote asset数量. 正确的quantity取决于市场的流动性与quoteOrderQty
            #例如: 市价 BUY BTCUSDT，单子会基于quoteOrderQty- USDT 的数量，购买 BTC.
            #市价 SELL BTCUSDT，单子会卖出 BTC 来满足quoteOrderQty- USDT 的数量.
            #比如我现在有1000USDT，我想用这1000USDT买BTC，那么quoteOrderQty就是1000，quantity就是0
            #quoteOrderQty
        }

        if order_type == OrderType.LIMIT:
            #检查强制要求的参数
            params['timeInForce'] = time_inforce.value
            assert('quantity' in params)
            assert('price' in params)
        elif order_type == OrderType.MARKET:            #市价单不需要price参数
            if 'price' in params:
                del params['price']
            assert('price' not in params)
            assert('quantity' in params)
            if quoteOrderQty > 0:
                params['quoteOrderQty'] = quoteOrderQty
                del params['quantity']

        elif order_type == OrderType.STOP_LOSS or order_type == OrderType.STOP_LOSS_LIMIT:
            if stop_price > 0:
                params["stopPrice"] = stop_price
            else:
                raise ValueError("stopPrice must greater than 0")

        return self.request(RequestMethod.POST, path=path, requery_dict=params, verify=True)

    def get_order(self, symbol: str, client_order_id: str) -> dict:
        """
        获取订单状态.
        :param symbol:
        :param client_order_id:
        :return:
        """
        # 获取订单状态和下单是同一个接口？只是一个是POST，一个是GET？
        path = "/api/v3/order"
        prams = {"symbol": symbol, "timestamp": self.get_current_timestamp(), "origClientOrderId": client_order_id}

        return self.request(RequestMethod.GET, path, prams, verify=True)

    def cancel_order(self, symbol : str, client_order_id : str) -> dict:
        """
        撤销订单.
        :param symbol:
        :param client_order_id:
        :return:
        """
        'origClientOrderId和orderId至少要有一个'
        path = "/api/v3/order"
        params = {"symbol": symbol, "timestamp": self.get_current_timestamp(),
                  "origClientOrderId": client_order_id
                  }
        assert('origClientOrderId' in params or 'orderId' in params)
        # 为什么要重试3次？
        for i in range(0, 3):
            try:
                order = self.request(RequestMethod.DELETE, path, params, verify=True)
                return order
            except Exception as e:
                logging.error('取消订单失败，次数={}，原因={}'.format(i, e))
        return None

    def get_open_orders(self, symbol:str='') -> list:
        """
        获取用户所有开放中的订单.
        :param symbol: BNBUSDT, or BTCUSDT etc.
        :return:
        """
        # 获取当前用户某个交易对的所有挂单
        path = "/api/v3/openOrders"

        params = {"timestamp": self.get_current_timestamp()}
        if symbol != '':
            params["symbol"] = symbol

        return self.request(RequestMethod.GET, path, params, verify=True)

    def cancel_open_orders(self, symbol : str) -> list:
        """
        撤销某个交易对的所有挂单
        :param symbol: symbol
        :return: return a list of orders.
        """
        path = "/api/v3/openOrders"

        params = {"timestamp": self.get_current_timestamp(),
                  "recvWindow": self.recv_window,
                  "symbol": symbol
                  }

        return self.request(RequestMethod.DELETE, path, params, verify=True)

    # 获取账户信息（获取用户的所有持仓）
    def get_account_info(self) -> dict:
        """
        {'feeTier': 2, 'canTrade': True, 'canDeposit': True, 'canWithdraw': True, 'updateTime': 0, 'totalInitialMargin': '0.00000000',
        'totalMaintMargin': '0.00000000', 'totalWalletBalance': '530.21334791', 'totalUnrealizedProfit': '0.00000000',
        'totalMarginBalance': '530.21334791', 'totalPositionInitialMargin': '0.00000000', 'totalOpenOrderInitialMargin': '0.00000000',
        'maxWithdrawAmount': '530.2133479100000', 'assets':
        [{'asset': 'USDT', 'walletBalance': '530.21334791', 'unrealizedProfit': '0.00000000', 'marginBalance': '530.21334791',
        'maintMargin': '0.00000000', 'initialMargin': '0.00000000', 'positionInitialMargin': '0.00000000', 'openOrderInitialMargin': '0.00000000',
        'maxWithdrawAmount': '530.2133479100000'}]}
        :return:
        """
        path = "/api/v3/account"
        params = {"timestamp": self.get_current_timestamp(),
                  "recvWindow": self.recv_window
                  }
        return self.request(RequestMethod.GET, path, params, verify=True)

    def get_balance(self, asset: str = 'BTC') -> float:
        """
        获取某个资产(BTC/USDT)的余额.
        :param asset: 资产名称
        :return:
        """
        account_info = self.get_account_info()
        if account_info is not None and 'balances' in account_info:
            for balance in account_info['balances']:
                if balance['asset'] == asset:
                    return float(balance['free'])
        return float(0)
    
    #amount=0表示清仓卖出
    def sell_market(self, asset : str, amount : float= 0) -> dict:
        """
        卖出所有的某个币种
        :param symbol: 交易对
        :param price: 卖出价格
        :param quantity: 卖出数量
        :return:
        """
        infos = dict()
        remaining = self.get_balance(asset)
        if amount == 0 :
            amount = remaining
        if amount > 0:
            #对卖出数量进行步进处理
            params = self.get_exchange_params(asset + 'USDT')
            if params is not None and 'min_quantity' in params :
                min_quantity = params['min_quantity']
                amount = amount - amount % min_quantity

                s_min = f"{min_quantity:f}".rstrip('0')
                percision = len(str(s_min).split('.')[1])
                logging.debug('最小数量小数位数={}'.format(percision))
                if amount < min_quantity:
                    logging.warning('{}已有数量={:f}({})小于最小卖出数量={:f}({})，交易取消。'.format(asset, remaining, remaining, min_quantity, min_quantity))
                    infos['local_code'] = -1
                    infos['local_msg'] = '{}已有数量={:f}({})小于最小卖出数量={:f}({})，交易取消。'.format(asset, 
                        remaining, remaining, min_quantity, min_quantity)
                    return infos
            else :
                infos['local_code'] = -1
                infos['local_msg'] = '未取到最小交易数量参数。'
                logging.error('sell_market未取到最小交易数量参数。')
                return infos
            symbol = asset + 'USDT'
            quantity = round(amount, percision)
            order_id = self.gen_client_order_id()
            logging.debug('生成本地订单id={}, 卖出数量={}'.format(order_id, quantity))
            infos = self.place_order(symbol, OrderSide.SELL, OrderType.MARKET, quantity, 0, order_id, time_inforce=timeInForce.GTC)
            if infos is None :
                infos = dict()
                infos['local_code'] = -1
                infos['local_msg'] = '卖单返回空结果。'
            else :
                infos['local_code'] = 0
                infos['local_msg'] = '卖单完成。'
        else :
            infos['local_code'] = -100
            infos['local_msg'] = '{}资产余额为0，本地取消卖单。'.format(asset)
            logging.warning('{}资产余额为0'.format(asset))
        return infos
    
    #amount=0表示满仓买入
    def buy_market(self, asset : str, amount : float=0) -> dict:
        """
        买入所有的某个币种
        :param symbol: 交易对
        :param price: 买入价格
        :param quantity: 买入数量
        :return:
        """
        infos = dict()
        #获取USDT余额
        balance = int(self.get_balance('USDT'))
        if balance > 0:
            logging.debug('USDT余额={}'.format(balance))
            #对买入数量进行步进处理
            params = self.get_exchange_params(asset + 'USDT')
            if params is not None and 'min_quantity' in params :
                min_quantity = params['min_quantity']
                if amount > 0:
                    amount = amount - amount % min_quantity
                    assert(amount >= min_quantity)
            else :
                logging.error('buy_market未取到最小交易数量参数。')
                infos['local_code'] = -1
                infos['local_msg'] = '未取到最小交易数量参数。'
                return infos

            symbol = asset + 'USDT'
            #quantity = balance
            order_id = self.gen_client_order_id()
            if amount > 0 :
                balance = 0
            infos = self.place_order(symbol, OrderSide.BUY, OrderType.MARKET, amount, 0, order_id, 
                time_inforce=timeInForce.GTC, quoteOrderQty=balance)
            if infos is None :
                infos = dict()
                infos['local_code'] = -1
                infos['local_msg'] = '买单返回空结果。'
            else :
                infos['local_code'] = 0
                infos['local_msg'] = '买单完成。'
                logging.debug('买单完成，infos={}'.format(infos))
        else :
            logging.warning('USDT资产余额为0，本地取消买单。')
            infos['local_code'] = -100
            infos['local_msg'] = 'USDT资产余额为0，本地取消买单。'
        return infos