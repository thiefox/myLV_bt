import requests
import time
import os

import sys
import time
import logging
from binance import BinanceSpotHttp
from binance import authentication
import binance.binance_spot as bs

from utils import config
#from utils import utility, round_to, dingding_info
from utils import utility
from enum import Enum
import logging
from datetime import datetime, timezone 

import nacl.signing
import nacl.encoding
import base64

DEFAULT_SYMBOL = 'BTCUSDT'

api_key = 'XYCWi1jlDJcOPG8MltM0plnPQlmqFd0wuvCKVuokovxlmwXBADoCI7Ea78h6bX2Y'
api_secret = 'your_api_secret'

#B_PRI_KEY = 'MC4CAQAwBQYDK2VwBCIEIIbtaS8/ONSmV+udv68Ws/nRyvuBYor8XQHsRzgYO0x8'

#比特币交易对BTCUSDT的最小交易量和最小价格
#BTCUSDT minQty='0.00001000', minPrice='0.01000000'
#假设7万一枚，买卖0.001枚，最小交易额是70美元

def get_account_balance(pri_key : str):
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)

    infos = http_client.get_account_info()
    balances = infos['balances']
    for balance in balances:
        if float(balance['free']) > 0 or float(balance['locked']) > 0:
            print('balance={}'.format(balance))
    return


    url = 'https://api.binance.com/api/v3/account'
    headers = {'X-MBX-APIKEY': api_key}

    #datetime.now().uni
    #utc_now = datetime.now(timezone.utc).timestamp()
    #print('utc_now={}'.format(utc_now))
    #print('time.time()={}'.format(time.time()))
    #return

    param_dict = {
        'timestamp': int(time.time() * 1000),
        'recvWindow': 5000
    }
    param_str = BinanceSpotHttp.build_parameters(param_dict)
    sign = authentication.ed25519_signature(pri_key, param_str).decode('utf-8')
    param_str = param_str + '&signature=' + str(sign)
    url += '?' + param_str
    print('新的URL={}'.format(url))

    #response = requests.get(url, headers=headers, params=param_dict)
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        account_info = response.json()
        balances = account_info['balances']
        for balance in balances:
            if float(balance['free']) > 0 or float(balance['locked']) > 0:
                print('balance={}'.format(balance))
                #print(f"Asset: {balance['asset']}, Free: {balance['free']}, Locked: {balance['locked']}")
    else:
        print(f"Error: {response.status_code}")

#获取binance某个交易对的交易深度
def get_depth(pri_key : str, symbol: str, limit = 5):
    url = 'https://api.binance.com/api/v3/depth'
    headers = {'X-MBX-APIKEY': api_key}
    limits = [5, 10, 20, 50, 100, 500, 1000]
    if limit not in limits:
        limit = 5
    if symbol == '':
        symbol = 'BTCUSDT'
    params = {'symbol': symbol, 'limit': limit}

    param_str = BinanceSpotHttp.build_parameters(params)
    #sign = authentication.ed25519_signature(pri_key, param_str).decode('utf-8')
    #param_str = param_str + '&signature=' + str(sign)
    url += '?' + param_str
    #self.request(RequestMethod.GET, path, query_dict)
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        depth = response.json()
        print(depth)
    else:
        print(f"Error: {response.status_code}")
    return    

def test_depth():
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    depth = http_client.get_order_book('BTCUSDT', 5)
    print(depth)
    return

#ACCOUNT=False，获取交易深度
#ACCOUNT=True，获取账户余额
def test_balance(ACCOUNT = False):
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    if not ACCOUNT :
        get_depth(cfg.private_key, 'BTCUSDT', 5)
        http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
        depth = http_client.get_order_book('BTCUSDT', 5)
        print(depth)
    else :
        http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
        infos = http_client.get_account_info()
        if infos is not None :
            assert(isinstance(infos, dict))
            for item in infos['balances']:
                if float(item['free']) > 0  or float(item['locked']) > 0:
                    print(f"Asset: {item['asset']}, Free: {item['free']}, Locked: {item['locked']}")
        else :
            print('异常：GET请求返回None')
    return

def test_exchange_info() :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    params = http_client.get_exchange_params(DEFAULT_SYMBOL)
    print('params={}'.format(params))
    min_quantity = params['min_quantity']
    str_min = format(min_quantity, 'f')
    print('str_min={}'.format(str_min))
    print('min_quantity={:.6f}, ={}'.format(min_quantity, str_min))

    return

def test_last_price_overview() :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    last_price = http_client.get_latest_price('BTCUSDT')
    print(last_price)
    return

def test_get_ticker() :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    last_price = http_client.get_ticker('BTCUSDT')
    if last_price is not None :
        buy_price = round(float(last_price['bidPrice']), 2)
        buy_qty = float(last_price['bidQty'])
        sell_price = round(float(last_price['askPrice']), 2)
        sell_qty = float(last_price['askQty'])
        print('买价（最高）={}, 买量={:.6f}, 卖价（最低）={}, 卖量={:.6f}'.format(buy_price, buy_qty, sell_price, sell_qty))
    return

def test_get_orders() :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    orders = http_client.get_open_orders('BTCUSDT')
    if isinstance(orders, list) :
        print('当前挂单数量={}'.format(len(orders)))
        print(orders)
    else :
        assert(False)
    return

#下市价买单
#amount=0表示满仓买入
def test_buy(amount : float = 0) :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    info = http_client.buy_market('BTC', amount=amount)
    if info is not None :
        test_account_balance()
    else :
        print('异常：下单买入失败')
    return

#下市价卖单
def test_sell(amount : float = 0) :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    prec = cfg.general.get_qty_precision()
    print('prec={}'.format(prec))

    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    info = http_client.sell_market('BTC', amount=amount)
    if info is not None :
        test_account_balance()
    else :
        print('异常：下单卖出失败')
    return


    order_id = http_client.gen_client_order_id()
    print('生成本地订单id={}'.format(order_id))
    info = http_client.place_order('BTCUSDT', bs.OrderSide.SELL, bs.OrderType.LIMIT, amount, price, order_id, bs.timeInForce.GTC)
    print('打印下卖单结果...')
    print(info)
    return

def test_cancel_order(order_id : str) :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    info = http_client.cancel_order('BTCUSDT', order_id)
    print('打印取消订单结果...')
    print(info)
    return

def test_cancel_all_orders() :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    orders = http_client.cancel_open_orders('BTCUSDT')
    if isinstance(orders, list) :
        print('取消所有挂单数量（列表）={}'.format(len(orders)))
        print(orders)
    elif isinstance(orders, dict) :
        print('取消所有挂单数量（字典）={}'.format(len(orders)))
    elif orders is None :
        print('取消所有挂单数量=0')
    else :
        print(type(orders))
        assert(False)
    return

def test_account_balance():
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    print('开始获取账户余额...')
    get_account_balance(cfg.private_key)
    return

def test_klines():
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    klines = http_client.get_kline('BTCUSDT', bs.Interval.MINUTE_1)
    print(klines)
    return

def test_time():
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    server_time = http_client.get_server_time()
    print(server_time)
    if server_time is not None :
        if 'serverTime' in server_time :
            server_time = server_time['serverTime']
            print('服务器时间={}={}'.format(server_time, utility.timestamp_to_string(server_time)))
    return

#test_depth()                       #获取交易深度
test_account_balance()             #获取账户余额
#获取账户余额或交易深度, 当ACCOUNT=False时等同于test_depth(), 当ACCOUNT=True时等同于test_account_balance()
#test_balance(ACCOUNT=False)        
#test_exchange_info()               #获取交易对元信息
#test_last_price_overview()         #获取最新价格OVERVIEW
#test_get_ticker()                  #获取最新价格详情
#test_get_orders()                  #获取当前挂单
#test_cancel_all_orders()           #取消所有挂单
#test_buy(amount=0)                          #下单买入
#test_sell(amount=0)             #下单卖出

#test_cancel_order('x-A6SIDXVS17307764878541000001')        #取消订单
#test_klines()                       #获取K线数据
#test_time()