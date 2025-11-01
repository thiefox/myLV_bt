import requests
import time
import os

import sys
import time
import logging
import binance.binance_spot as bs
from binance.binance_spot import BinanceSpotHttp
from binance import authentication

from com_utils import config
#from utils import utility, round_to, dingding_info
from com_utils import utility
from com_utils import log_adapter
from enum import Enum
import logging
from datetime import datetime, timezone 

import nacl.encoding

import mail_template

DEFAULT_SYMBOL = 'BTCUSDT'

#比特币交易对BTCUSDT的最小交易量和最小价格
#BTCUSDT minQty='0.00001000', minPrice='0.01000000'
#假设7万一枚，买卖0.001枚，最小交易额是70美元

def _init_cfg() -> config.Config:
    cfg = config.Config()
    #cfg.loads(config.Config.CONFIG_FILE)
    if cfg.loads() :
        return cfg
    return None

def _get_keys() -> tuple[str, str]:
    api_key = ''
    pri_key = ''
    cfg = _init_cfg()
    if cfg is not None :
        api_key = cfg.api_key
        pri_key = cfg.private_key
    return api_key, pri_key

def get_account_balance():
    price = test_get_ticker()
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])

    infos = http_client.get_account_info()
    balances = infos['balances']
    print('type of balances={}'.format(type(balances)))
    BTC_balance = float(0)
    USDT_balance = float(0)
    for balance in balances:
        if float(balance['free']) > 0 or float(balance['locked']) > 0:
            #print('type of balance={}'.format(type(balance)))
            log_adapter.color_print('打印币种余额={}'.format(balance), log_adapter.COLOR.GREEN)
            if balance['asset'].upper() == 'BTC' :
                BTC_balance = round(float(balance['free']) + float(balance['locked']), 5)
            elif balance['asset'].upper() == 'USDT' :
                USDT_balance = round(float(balance['free']) + float(balance['locked']), 2)
    total_asset = round(USDT_balance + price * BTC_balance, 2)
    log_adapter.color_print('BTC余额={:.5f}, USDT余额={:.2f}'.format(BTC_balance, USDT_balance), log_adapter.COLOR.GREEN)
    log_adapter.color_print('当前价格={}$，总资产={}$.'.format(price, total_asset), log_adapter.COLOR.GREEN)
    mail = mail_template.mail_content('thiefox@qq.com')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    mail.update_balance(now_str, balances, price)
    if not mail.send_mail() :
        log_adapter.color_print('异常：发送邮件失败', log_adapter.COLOR.RED)
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
def get_depth(symbol: str, limit = 5):
    url = 'https://api.binance.com/api/v3/depth'
    keys = _get_keys()
    headers = {'X-MBX-APIKEY': keys[0]}
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
    print('header={}'.format(headers))
    print('url={}'.format(url))
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        depth = response.json()
        print('---开始打印交易深度---')
        print(depth)
        print('---结束打印交易深度---')
    else:
        print(f"Error: {response.status_code}")
    return    

def test_depth():
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    depth = http_client.get_order_book('BTCUSDT', 5)
    print('开始打印get_order_book结果...')
    print(depth)
    return

#ACCOUNT=False，获取交易深度
#ACCOUNT=True，获取账户余额
def test_balance(ACCOUNT = False):
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    if not ACCOUNT :
        #get_depth('BTCUSDT', 5)
        depth = http_client.get_order_book('BTCUSDT', 5)
        print(depth)
    else :
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
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    params = http_client.get_exchange_params(DEFAULT_SYMBOL)
    print('params={}'.format(params))
    min_quantity = params['min_quantity']
    str_min = format(min_quantity, 'f')
    #print('str_min={}'.format(str_min))
    print('最小交易单位={:.6f}, ={}'.format(min_quantity, str_min))
    return

def test_last_price_overview() :
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    last_price = http_client.get_latest_price('BTCUSDT')
    print(last_price)
    return

def test_get_ticker() -> float:
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    last_price = http_client.get_ticker('BTCUSDT')
    if last_price is not None :
        buy_price = round(float(last_price['bidPrice']), 2)
        buy_qty = float(last_price['bidQty'])
        sell_price = round(float(last_price['askPrice']), 2)
        sell_qty = float(last_price['askQty'])
        print('买价（最高）={}, 买量={:.6f}, 卖价（最低）={}, 卖量={:.6f}'.format(buy_price, buy_qty, sell_price, sell_qty))
    return sell_price

def test_get_orders() :
    Keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=Keys[0], private_key=Keys[1])
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
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    info = http_client.buy_market('BTC', amount=amount)
    print('打印买单结果...')
    print(info)
    try:
        if info['local_code'] == 0:    
            request_qty = float(info['origQty'])
            executed_qty = float(info['executedQty'])
            log_adapter.color_print('重要：买单请求数量={}, 成交数量={}'.format(request_qty, executed_qty), log_adapter.COLOR.GREEN)
            fills = info['fills']
            for fill in fills:
                price = round(float(fill['price']), 2)
                qty = round(float(fill['qty']), 5)
                log_adapter.color_print('重要：---成交价格={}, 成交数量={}'.format(price, qty), log_adapter.COLOR.GREEN)
        else :
            log_adapter.color_print('异常：市价买入失败，原因={}'.format(info['local_msg']), log_adapter.COLOR.RED)
    except Exception as e:
        log_adapter.color_print('异常：获取买单信息失败，原因={}'.format(e), log_adapter.COLOR.RED)
    time.sleep(1)
    test_account_balance()
    return

#下市价卖单
def test_sell(amount : float = 0) :
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    info = http_client.sell_market('BTC', amount=amount)
    print('打印卖单结果...')
    print(info)
    try:
        if info['local_code'] == 0:
            request_qty = float(info['origQty'])
            executed_qty = float(info['executedQty'])
            log_adapter.color_print('重要：卖单请求数量={}, 成交数量={}'.format(request_qty, executed_qty), log_adapter.COLOR.GREEN)
            fills = info['fills']
            for fill in fills:
                price = round(float(fill['price']), 2)
                qty = round(float(fill['qty']), 5)
                log_adapter.color_print('重要：---成交价格={}, 成交数量={}'.format(price, qty), log_adapter.COLOR.GREEN)
        else :
            log_adapter.color_print('异常：市价卖出失败，原因={}'.format(info['local_msg']), log_adapter.COLOR.RED)
    except Exception as e:
        log_adapter.color_print('异常：获取卖单信息失败，原因={}'.format(e), log_adapter.COLOR.RED)
    time.sleep(1)
    test_account_balance()
    return

def test_cancel_order(order_id : str) :
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    info = http_client.cancel_order('BTCUSDT', order_id)
    print('打印取消订单结果...')
    print(info)
    return

def test_cancel_all_orders() :
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
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
    print('开始获取账户余额...')
    get_account_balance()
    return

def test_klines():
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    klines = http_client.get_kline('BTCUSDT', bs.Interval.MINUTE_1)
    print(klines)
    return

def test_time():
    keys = _get_keys()
    http_client = BinanceSpotHttp(api_key=keys[0], private_key=keys[1])
    server_time = http_client.get_server_time()
    print(server_time)
    if server_time is not None :
        if 'serverTime' in server_time :
            server_time = server_time['serverTime']
            print('服务器时间={}={}'.format(server_time, utility.timestamp_to_string(server_time)))
    return

#test_depth()                       #获取交易深度
#test_account_balance()             #获取账户余额
#获取账户余额或交易深度, 当ACCOUNT=False时等同于test_depth(), 当ACCOUNT=True时等同于test_account_balance()
#test_balance(ACCOUNT=False)        
#test_exchange_info()               #获取交易对元信息
#test_last_price_overview()         #获取最新价格OVERVIEW
#test_get_ticker()                  #获取最新价格详情
#test_get_orders()                  #获取当前挂单
#test_cancel_all_orders()           #取消所有挂单
#test_buy(amount=0)                  #下单买入
#test_sell(amount=0.05)                #下单卖出

#test_cancel_order('x-A6SIDXVS17307764878541000001')        #取消订单
#test_klines()                       #获取K线数据
#test_time()

#目前采用的币安监控处理器是active_monitor.py