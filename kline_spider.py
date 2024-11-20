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

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils import utility
from utils import log_adapter
#import pandas
from pandas import DataFrame
import numpy as np
import talib
import copy

from enum import Enum

#import draw
from base_item import trade_symbol, kline_interval, MACD_CROSS, save_unit

import fin_util

def get_kline_data(symbol : trade_symbol, inter : kline_interval, begin : int, limit : int) -> list:
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

    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.value}&interval={inter}&limit={limit}"
    url = "https://api.binance.com/api/v3/klines"
    #如果未发送startTime和endTime，将返回最近的K线数据
    #limit为请求的K线数量，最大值为1000
    param_dict = {
        "symbol": symbol.value,
    }
    #param_dict["interval"] = '{}h'.format(interval)
    assert(isinstance(inter.value, str))
    #assert(inter.value in ['1h', '4h', '6h', '12h', '1d'])
    param_dict["interval"] = inter.value
    if begin > 0:
        param_dict["startTime"] = begin
    param_dict["limit"] = limit

    params = urlencode(param_dict)
    print('params={}'.format(params))

    response = None
    for i in range(0, 3):
        try :
            #response = requests.get(url, params=param_dict)

            session = requests.Session()
            #session = requests.session()
            session.keep_alive = False
            retry = Retry(connect=5, backoff_factor=0.5)
            adapter = HTTPAdapter(max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            response = session.get(url, params=param_dict)
            
        except requests.exceptions.ConnectionError:
            print('异常:requests.exceptions.ConnectionError')
        except requests.exceptions.ConnectTimeout:
            print('异常:requests.exceptions.ConnectTimeout')
        except requests.exceptions.Timeout:
            print('异常:requests.exceptions.Timeout')
        except Exception as e:
            print('请求数据失败={}'.format(e))
        finally:
            session.close()
        if response is not None:
            break
        time.sleep(10)

    infos = None
    if response is not None:    
        print('response={}'.format(response))
        infos = None
        if response.status_code == 200:
            infos = response.json()
        response.close()
    else :
        pass
    return infos

def _save_klines(symbol : trade_symbol, su : save_unit, begin : int, klines : list) -> bool:
    begin_t = utility.timestamp_to_datetime(begin)
    if len(klines) == 0:
        print('异常：({}-{}-{})的K线数据为空，无需保存'.format(begin_t.year, begin_t.month, begin_t.day))
        return False
    try :
        file_name = fin_util.get_kline_file_name(symbol, su, begin_t)
        print('数据文件名={}'.format(file_name))
        with open(file_name, 'w') as f:
            json.dump(klines, f, indent=4, ensure_ascii=False)
            print('保存({}-{}-{})K线数据到文件{}成功，记录={}'.format(begin_t.year, begin_t.month, begin_t.day, file_name, len(klines)))
        return True    
    except Exception as e:
        print('保存K线数据到文件{}失败={}'.format(file_name, e))
        return False

#begin和end为币安的时间戳，单位为毫秒
#如end为0，则表示获取从begin到最新的K线数据
def save_klines(symbol : trade_symbol, interval : kline_interval, begin : int, end : int) -> tuple:
    assert(begin > 0)
    if end == 0 :
        end = int(datetime.now().timestamp() * 1000)
    assert(end > begin)
    begin_t = utility.timestamp_to_datetime(begin)
    end_t = utility.timestamp_to_datetime(end)
    print('开始获取{}的K线数据，inter={}, begin={}, end={}...'.format(symbol.value, interval.value, 
        begin_t.strftime("%Y-%m-%d %H:%M:%S"), end_t.strftime("%Y-%m-%d %H:%M:%S")))
    klines = list()
    cur_year = begin_t.year
    cur_month = begin_t.month
    info = (0, klines)
    while cur_year < end_t.year or (cur_year == end_t.year and cur_month <= end_t.month):
        print('开始获取({}-{})的K线数据...'.format(cur_year, cur_month))
        info = save_klines_1M(symbol, cur_year, cur_month, interval)
        print('获取({}-{})K线数据完成，结果={}, K线数={}'.format(cur_year, cur_month, info[0], len(info[1])))
        klines.extend(info[1])
        if info[0] == 0:
            print('获取({}-{})K线数据已达到最新时间，处理结束。'.format(cur_year, cur_month))
            break
        elif info[0] == 1:
            pass
        elif info[0] < 0:
            print('异常：获取({}-{})K线数据失败'.format(cur_year, cur_month))
            break
        else :
            assert(False)
        cur_month += 1
        if cur_month > 12:
            cur_year += 1
            cur_month = 1
        time.sleep(3)
    print('获取{}的K线数据全部完成，inter={}, begin={}, end={}。结果={}，K线数={}'.format(symbol.value, interval.value, 
        begin_t.strftime("%Y-%m-%d %H:%M:%S"), end_t.strftime("%Y-%m-%d %H:%M:%S"), info[0], len(klines)))
    return info[0], klines

# 获取一月的K线数据并保存到文件
# tuple[0]=1表示已全部获取成功。
# tuple[0]=0表示month为当前月，已获取到最新时间的K线（当月未满）。
# tuple[0]=-1表示获取失败。
def save_klines_1M(symbol : trade_symbol, year : int, month : int, su : save_unit) -> tuple:
    limit = 100
    print('开始获取({}-{})K线数据，interval={}, limit={}...'.format(year, month, su.interval.value, limit))
    Now = int(datetime.now().timestamp() * 1000)
    print('当前时间={}, value={}'.format(utility.timestamp_to_string(Now), Now))
    month_klines = list()
    begin = utility.string_to_timestamp('{}-{}-01 00:00:00'.format(year, str(month).zfill(2)))
    if month == 12:
        end = utility.string_to_timestamp('{}-01-01 00:00:00'.format(year+1))
    else :
        end = utility.string_to_timestamp('{}-{}-01 00:00:00'.format(year, str(month+1).zfill(2)))
    cur = begin
    cn = 0

    delta = su.interval.get_delta().total_seconds() * 1000
    print('K线时间间隔={}毫秒'.format(delta))
    failed = False
    expired = False
    while True:
        if cur >= Now:
            print('重要：请求时间戳={}={}已达到或超过当前时间{}，处理结束。'.format(cur, 
                utility.timestamp_to_string(cur), utility.timestamp_to_string(Now)))
            expired = True
            break
        print('第{}次请求K线数据，cur={},limit={}...'.format(cn, utility.timestamp_to_string(cur), limit))
        klines = get_kline_data(symbol, su.interval, cur, limit)
        if klines is None or len(klines) == 0:
            break
        assert(isinstance(klines, list))
        print('获取到K线数据数量={}'.format(len(klines)))
        for i in range(len(klines)):
            kline = klines[i]
            #if i == 0 :
            if i >= 0:
                print('第{}/{}条K线数据的开始时间={}，结束时间={}。'.format(i, len(klines), 
                    utility.timestamp_to_string(kline[0]), utility.timestamp_to_string(kline[6])))
                if abs(kline[0]-cur) > delta:
                    print('K线数据异常，cur={}={}，kline[0]={}={}. real={}, delta={}'.format(cur, utility.timestamp_to_string(cur), 
                        kline[0], utility.timestamp_to_string(kline[0]), kline[6]+1-kline[0], delta))
                    failed = True
                    break
            month_klines.append(kline)
            cur = kline[6] + 1
            real_delta = cur - kline[0]
            if real_delta < delta:
                print('重要：当前K线({}/{})结束时间戳{}={}与开始时间戳{}={}的时间差{}<{}ms，判断为最新的未完成K线，结束处理。'.format(i, len(klines), 
                    kline[6], utility.timestamp_to_string(kline[6]), kline[0], utility.timestamp_to_string(kline[0]), 
                    real_delta, delta))
                break
            if cur >= end :
                print('重要：当前K线({}/{})结束时间戳{}={}已达到或超过结束时间，结束处理。'.format(i, len(klines), 
                    kline[6], utility.timestamp_to_string(kline[6])))
                break
        if failed or cur >= end:
            break
        time.sleep(1)   #防止请求过快
        cn += 1

    if failed:
        print('获取({}-{})K线数据failed'.format(year, month))
        return -1, month_klines
    
    if _save_klines(symbol, su, begin, month_klines) :
        if expired:
            return 0, month_klines
        else :
            return 1, month_klines
    else :
        return -1, month_klines

#获取一年的K线数据并保存到文件
def save_klines_1Y(symbol : trade_symbol, year : int, su : save_unit) -> tuple:
    year_lines = list()
    for i in range(1, 13):
        info = save_klines_1M(symbol, year, i, su)
        year_lines.extend(info[1])
        if info[0] == 0:
            print('获取({}-{})K线数据已达到最新时间，处理结束。'.format(year, i))
            break
        elif info[0] < 0:
            print('异常：获取({}-{})K线数据失败'.format(year, i))
            break
        time.sleep(3)
    return info[0], year_lines

def save_current_kline(symbol : trade_symbol, su : save_unit):
    all_klines = list()
    unit_begin = 0
    MAX_COUNT = 1000
    while True :
        klines = get_kline_data(symbol, su.interval, 0, 1)
        if klines is None or len(klines) == 0:
            print('获取当前K线数据失败')
            break
        assert(isinstance(klines, list))
        print('内存K线数={}，获取到当前K线数据数量={}'.format(len(all_klines), len(klines)))
        assert(len(klines) == 1)
        kline = klines[0]
        print('获取K线的开始时间={}，结束时间={}。开盘价={}，收盘价={}'.format(utility.timestamp_to_string(kline[0]), 
            utility.timestamp_to_string(kline[6]), round(float(kline[1]),2), round(float(kline[4]), 2)))
        if len(all_klines) == 0:
            all_klines.append(kline)
        elif all_klines[-1][0] == kline[0]:
            print('重要：未完成K线数据更新。')
        else :
            print('重要：已生成新的K线！')
            begin = all_klines[unit_begin][0]
            check = kline[0]
            if not su.is_same_unit(begin, check) :
                print('重要：一个保存周期完成，all={}, unit_begin={}，保存klines...'.format(len(all_klines), unit_begin))
                if _save_klines(symbol, su, begin, all_klines[unit_begin:]) :
                    print('保存当前K线数据成功')
                    all_klines.clear()
                else :
                    print('保存当前K线数据失败')
                    all_klines.clear()
                    assert(False)
                unit_begin = len(all_klines)
            all_klines.append(kline)
        time.sleep(60)
        if len(all_klines) >= MAX_COUNT:
            print('达到最大K线数量={}，退出.'.format(MAX_COUNT))
            break
    
    if len(all_klines) > unit_begin:
        print('结束循环的收尾：all={}, unit_begin={}，保存klines...'.format(len(all_klines), unit_begin))
        begin = all_klines[unit_begin][0]
        if _save_klines(symbol, su, begin, all_klines[unit_begin:]) :
            print('保存当前K线数据成功')
        else :
            print('保存当前K线数据失败')
            assert(False)   
        unit_begin = len(all_klines)
    return 

def _test() :
    print("KLine Spider Start...")

    LOG_FLAG = 0
    if LOG_FLAG == 1 :
        str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        #logging.basicConfig(level=logging.INFO, format=format, filename='log/{}_{}_{}H-{}.txt'.format(symbol, year, interval, str_now))
        logging.basicConfig(level=logging.INFO, format=format, filename='log/kline_spider-{}.txt'.format(str_now))
        logger = logging.getLogger('binance')
        logger.setLevel(logging.INFO)
        #把print输出到日志文件
        tmp_out = sys.stdout
        tmp_err = sys.stderr

        sys.stdout = log_adapter.LoggerWriter(logger, logging.INFO)
        sys.stderr = log_adapter.LoggerWriter(logger, logging.ERROR)

    su = save_unit(kline_interval.h1)
    #info = save_klines_1M(trade_symbol.BTCUSDT, 2022, 10, su)
    su = save_unit(kline_interval.m3, multiple=5)
    save_current_kline(trade_symbol.BTCUSDT, su)

    if LOG_FLAG == 1 :
        sys.stdout = tmp_out
        sys.stderr = tmp_err
    print("KLine Spider End.")
    return

_test()
