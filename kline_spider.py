from __future__ import annotations
from typing import List, Dict

import os
import sys
import requests
import json
import logging
import time
from urllib.parse import urlencode
from datetime import datetime, timedelta
from utils import utility
from utils import log_adapter
#import pandas
from pandas import DataFrame
import numpy as np
import talib
import copy

from enum import Enum

import draw
from base_item import trade_symbol, kline_interval, MACD_CROSS

import data_loader
from fin_util import prices_info
import fin_util

def get_kline_data(symbol : str, inter : kline_interval, begin : int, limit : int) -> list:
    '''
        [
            1499040000000,      // 开盘时间
            "0.01634790",       // 开盘价
            "0.80000000",       // 最高价
            "0.01575800",       // 最低价
            "0.01577100",       // 收盘价(当前K线未结束的即为最新价)
            "148976.11427815",  // 成交量
            1499644799999,      // 收盘时间
            "2434.19055334",    // 成交额
            308,                // 成交笔数
            "1756.87402397",    // 主动买入成交量
            "28.46694368",      // 主动买入成交额
            "17928899.62484339" // 请忽略该参数
        ]
    '''

    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={inter}&limit={limit}"
    url = "https://api.binance.com/api/v3/klines"

    param_dict = {
        "symbol": 'BTCUSDT',
    }
    #param_dict["interval"] = '{}h'.format(interval)
    assert(isinstance(inter.value, str))
    assert(inter.value in ['1h', '4h', '6h', '12h', '1d'])
    param_dict["interval"] = inter.value
    if begin > 0:
        param_dict["startTime"] = begin
    param_dict["limit"] = limit

    params = urlencode(param_dict)
    print('params={}'.format(params))

    #response = requests.get(url)
    response = requests.get(url, params=param_dict)

    print('response={}'.format(response))
    if response.status_code == 200:
        return response.json()
    else:
        return None

#保存获取的K线数据到文件
def save_kline(symbol : str, year : int, month : int, interval : kline_interval) -> int:
    limit = 100
    print('开始获取({}-{})K线数据，interval={}, limit={}...'.format(year, month, interval, limit))
    Now = datetime.now().timestamp() * 1000
    print('当前时间={}, value={}'.format(utility.timestamp_to_string(Now), Now))
    month_klines = list()
    begin = utility.string_to_timestamp('{}-{}-01 00:00:00'.format(year, str(month).zfill(2)))
    if month == 12:
        end = utility.string_to_timestamp('{}-01-01 00:00:00'.format(year+1))
    else :
        end = utility.string_to_timestamp('{}-{}-01 00:00:00'.format(year, str(month+1).zfill(2)))
    cur = begin
    cn = 0
    int_interval = int(interval.value[:-1])
    end_char = interval.value[-1]
    if end_char == 'h':
        delta = timedelta(hours=int_interval).total_seconds() * 1000
    elif end_char == 'd':
        delta = timedelta(days=int_interval).total_seconds() * 1000
    else :
        assert(False)
    failed = False
    expired = False
    while True:
        if cur >= Now:
            print('请求时间戳={}={}已达到或超过当前时间{}，处理结束。'.format(cur, 
                utility.timestamp_to_string(cur), utility.timestamp_to_string(Now)))
            expired = True
            break
        print('第{}次请求K线数据，cur={}...'.format(cn, utility.timestamp_to_string(cur)))
        klines = get_kline_data(symbol, interval, cur, limit)
        if klines is None or len(klines) == 0:
            break
        assert(isinstance(klines, list))
        print('获取到K线数据记录={}'.format(len(klines)))
        for i in range(len(klines)):
            kline = klines[i]
            if i == 0 :
                print('第{}/{}条K线数据的开始时间={}'.format(i, len(klines), utility.timestamp_to_string(kline[0])))
                if abs(kline[0]-cur) > delta:
                    print('K线数据异常，cur={}={}，kline[0]={}={}'.format(cur, utility.timestamp_to_string(cur), 
                        kline[0], utility.timestamp_to_string(kline[0])))
                    failed = True
                    break
            '''
            if kline[6] > end :
                print('异常：当前K线({}/{})结束时间戳{}={}超过结束时间'.format(i, len(klines), 
                    kline[6], utility.timestamp_to_string(kline[6])))
                failed = True
            '''
            month_klines.append(kline)
            cur = kline[6] + 1
            if cur >= end :
                print('当前K线({}/{})结束时间戳{}={}已达到或超过结束时间，处理结束。'.format(i, len(klines), 
                    kline[6], utility.timestamp_to_string(kline[6])))
                break
        if failed or cur >= end:
            break
        time.sleep(1)   #防止请求过快
        cn += 1

    if failed:
        print('获取({}-{})K线数据failed'.format(year, month))
        return -1
    if len(month_klines) > 0:
        print('获取({}-{})K线数据完成，记录={}'.format(year, month, len(month_klines)))
        try :
            file_name = utility.gen_kline_file_name(symbol, year, month, interval.value)
            with open(file_name, 'w') as f:
                json.dump(month_klines, f, indent=4, ensure_ascii=False)
                print('保存({}-{})K线数据到文件{}成功，记录={}'.format(year, month, file_name, len(month_klines)))
        except Exception as e:
            print('保存K线数据到文件{}失败={}'.format(file_name, e))
    else :
        print('未获取到({}-{})K线数据'.format(year, month))
    if expired:
        return 0
    else :
        return 1

#获取一年的K线数据并保存到文件
def save_BTC_klines_year(year : int, interval : kline_interval):
    for i in range(1, 13):
        result = save_kline(trade_symbol.BTCUSDT, year, i, interval)
        if result == 0:
            print('获取({}-{})K线数据已达到或超过当前时间，处理结束。'.format(year, i))
            break
        time.sleep(3)
    return

def _test() :
    print("KLine Spider Start...")
    str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 
    format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    #logging.basicConfig(level=logging.INFO, format=format, filename='log/{}_{}_{}H-{}.txt'.format(symbol, year, interval, str_now))
    logging.basicConfig(level=logging.INFO, format=format, filename='log/kline_spider-{}.txt'.format(str_now))
    logger = logging.getLogger('binance')
    logger.setLevel(logging.INFO)
    #把print输出到日志文件
    tmp_out = sys.stdout
    tmp_err = sys.stderr

    #sys.stdout = log_adapter.LoggerWriter(logger, logging.INFO)
    #sys.stderr = log_adapter.LoggerWriter(logger, logging.ERROR)

    #save_BTC_klines_year(2024, kline_interval.d1)

    sys.stdout = tmp_out
    sys.stderr = tmp_err
    print("KLine Spider End.")
    return

#_test()