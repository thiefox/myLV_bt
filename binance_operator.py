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

class binance_operator:
    def __init__(self) :
        self.cfg = config.Config()
        return
    def init(self) -> bool:
        if not self.cfg.loads():
            print('异常：加载配置文件{}失败。'.format(config.Config.CONFIG_FILE))
            return False
        return True
    

#比特币交易对BTCUSDT的最小交易量和最小价格
#BTCUSDT minQty='0.00001000', minPrice='0.01000000'
#假设7万一枚，买卖0.001枚，最小交易额是70美元

def get_account_balance(pri_key : str):
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
                print(f"Asset: {balance['asset']}, Free: {balance['free']}, Locked: {balance['locked']}")
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
        #get_account_balance(cfg.private_key)
        get_depth(cfg.private_key, 'BTCUSDT', 5)
    else :
        http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
        infos = http_client.get_account_info()
        if infos is not None :
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
    exchange_info = http_client.get_exchange_info('BTCUSDT')
    print(exchange_info)
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
    print(last_price)
    return

def test_get_orders() :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    orders = http_client.get_open_orders('BTCUSDT')
    print(orders)
    return

#下市价买单
def test_buy(amount : float = 0.001) :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    order_id = http_client.gen_client_order_id()
    print('生成本地订单id={}'.format(order_id))
    info = http_client.place_order('BTCUSDT', bs.OrderSide.BUY, bs.OrderType.MARKET, amount, 0, order_id, bs.timeInForce.GTC)
    print('打印下买单结果...')
    print(info)
    return

#下限价卖单
def test_sell(price : float, amount : float) :
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    http_client = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
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

def test_account_balance():
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    get_account_balance(cfg.private_key)
    return

test_depth()                       #获取交易深度
#test_account_balance()             #获取账户余额
#获取账户余额或交易深度, 当ACCOUNT=False时等同于test_depth(), 当ACCOUNT=True时等同于test_account_balance()
#test_balance(ACCOUNT=False)        
#test_exchange_info()               #获取交易对元信息
#test_last_price_overview()         #获取最新价格OVERVIEW
#test_get_ticker()                  #获取最新价格详情
#test_get_orders()                  #获取当前挂单

#test_buy(0.001)                          #下单买入
#test_sell(68900, 0.00099)             #下单卖出

#test_cancel_order('x-A6SIDXVS17307764878541000001')        #取消订单