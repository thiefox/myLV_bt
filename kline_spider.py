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

DEFAULT_LIMIT = 500

#如begin=0，表示获取最新的K线数据
def _get_kline_data(symbol : trade_symbol, inter : kline_interval, begin : int, limit : int) -> list:
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
    #print('params={}'.format(params))

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
        #print('response={}'.format(response))
        infos = None
        if response.status_code == 200:
            infos = response.json()
        response.close()
    else :
        pass
    return infos

#begin为时间戳，如begin=0，表示获取最新的K线数据
#count为获取的K线数量。如count=0，表示获取到最新的K线数据为止
def get_klines(symbol : trade_symbol, inter : kline_interval, begin : int, count=0) -> list:
    #print('get_klines, interval={}, begin={}({}), count={}'.format(inter.value, begin, utility.timestamp_to_string(begin), count))
    all_klines = list()
    need_all = count <= 0
    limit = DEFAULT_LIMIT
    while True:
        if not need_all and  count < limit:
            limit = count
        klines = _get_kline_data(symbol, inter, begin, limit)
        if klines is None or len(klines) == 0:
            print('异常：获取K线数据失败, begin={}({}), limit={}'.format(begin, utility.timestamp_to_string(begin), limit))
            break
        assert(isinstance(klines, list))
        all_klines.extend(klines)
        if not need_all:
            count -= len(klines)
            assert(count >= 0)
        if len(klines) < limit:
            #print('获取K线数据已达到最新时间1, limit={}, len={}，处理结束。'.format(limit, len(klines)))
            break
        begin = klines[-1][6] + 1
        now = int(datetime.now().timestamp() * 1000)
        if begin >= now:
            '''
            print('获取K线数据已达到最新时间2, begin={}({}), now={}({})，处理结束。'.format(begin, utility.timestamp_to_string(begin),
                now, utility.timestamp_to_string(now)))
            '''
            break
        if not need_all and count <= 0:
            #print('获取K线数据已达到最新时间3，count={}, 处理结束。'.format(count))
            break
        time.sleep(1)   #防止请求过快
    return all_klines

def _save(symbol : trade_symbol, su : save_unit, begin : int, klines : list) -> bool:
    begin_t = utility.timestamp_to_datetime(begin)
    if len(klines) == 0:
        print('异常：({}-{}-{})的K线数据为空，无需保存'.format(begin_t.year, begin_t.month, begin_t.day))
        return False
    try :
        file_name = fin_util.get_kline_file_name(symbol, su, begin_t, DIR_MUST_EXISTS=True)
        print('数据文件名={}'.format(file_name))
        with open(file_name, 'w') as f:
            json.dump(klines, f, indent=4, ensure_ascii=False)
            print('保存({}-{}-{})K线数据到文件{}成功，记录={}'.format(begin_t.year, begin_t.month, begin_t.day, file_name, len(klines)))
        return True    
    except Exception as e:
        print('保存K线数据到文件{}失败={}'.format(file_name, e))
        return False

def save_klines(symbol : trade_symbol, su : save_unit, year : int, month : int, day : int) -> bool:
    LIMIT = DEFAULT_LIMIT   #每次请求的K线数量
    log_adapter.color_print('通知：开始获取({}-{}-{})K线数据，间隔={}, 倍数={}, LIMIT={}...'.format(year, 
        month, day, su.interval.value, su.multiple, LIMIT), log_adapter.COLOR.GREEN)
    now = int(datetime.now().timestamp() * 1000)
    print('通知：当前时间={}...'.format(utility.timestamp_to_string(now)))

    all_klines = list()
    assert(year >= 2017)
    if month > 0 :
        assert(month >= 1 and month <= 12)
    if day > 0 :
        assert(day >= 1 and day <= 31)
    begin = end = 0
    if month > 0 :
        if day > 0 :
            begin = utility.string_to_timestamp('{}-{}-{} 00:00:00'.format(year, str(month).zfill(2), str(day).zfill(2)))
            if utility.is_last_day(year, month, day):   #当月最后一天
                if month == 12: #当年最后一天
                    end = utility.string_to_timestamp('{}-01-01 00:00:00'.format(year+1))
                else :
                    end = utility.string_to_timestamp('{}-{}-01 00:00:00'.format(year, str(month+1).zfill(2)))
            else :
                end = utility.string_to_timestamp('{}-{}-{} 00:00:00'.format(year, str(month).zfill(2), str(day+1).zfill(2)))
        else :
            begin = utility.string_to_timestamp('{}-{}-01 00:00:00'.format(year, str(month).zfill(2)))
            if month == 12:
                end = utility.string_to_timestamp('{}-01-01 00:00:00'.format(year+1))
            else :
                end = utility.string_to_timestamp('{}-{}-01 00:00:00'.format(year, str(month+1).zfill(2)))
    else :
        begin = utility.string_to_timestamp('{}-01-01 00:00:00'.format(year))
        end = utility.string_to_timestamp('{}-01-01 00:00:00'.format(year+1))

    cur = begin

    failed = False
    expired = False
    cn = 0
    log_adapter.color_print('通知：启动K线处理循环，开始={}, 结束={}...'.format(utility.timestamp_to_string(begin), 
        utility.timestamp_to_string(end)), log_adapter.COLOR.GREEN)

    while True :
        now = int(datetime.now().timestamp() * 1000)
        if cur >= now:
            print('重要：请求时间戳={}({})已达到或超过当前时间{}，处理循环1。'.format(cur, 
                utility.timestamp_to_string(cur), utility.timestamp_to_string(now)))
            expired = True
            break
        print('通知：第{}次请求K线数据，cur={},LIMIT={}...'.format(cn, utility.timestamp_to_string(cur), LIMIT))
        klines = _get_kline_data(symbol, su.interval, cur, LIMIT)
        if klines is None or len(klines) == 0:
            log_adapter.color_print('异常：获取K线数据失败，结束循环。', log_adapter.COLOR.RED)
            break
        assert(isinstance(klines, list))
        print('通知：获取到K线数据数量={}'.format(len(klines)))
        cn += 1
        for i in range(len(klines)):
            kline = klines[i]
            if len(all_klines) == 0:
                print('通知：空槽直接加入。第{}/{}条K线数据的开始时间={}，结束时间={}。'.format(i, len(klines),
                    utility.timestamp_to_string(kline[0]), utility.timestamp_to_string(kline[6])))
                assert(kline[6] < end)
                all_klines.append(kline)
            else :
                begin = all_klines[0][0]
                check = kline[0]        
                
                if not su.is_same_unit(begin, check, HEADER=True) :
                    log_adapter.color_print('重要：一个保存周期完成，K线数={}, begin={}，end={}...'.format(len(all_klines), 
                        utility.timestamp_to_string(begin), utility.timestamp_to_string(all_klines[-1][6])), log_adapter.COLOR.YELLOW)
                    if _save(symbol, su, begin, all_klines) :
                        log_adapter.color_print('重要：保存当前K线数据成功。', log_adapter.COLOR.GREEN)
                        all_klines.clear()
                        all_klines.append(kline)
                    else :
                        log_adapter.color_print('异常：保存K线数据单元失败。', log_adapter.COLOR.RED)
                        all_klines.clear()
                        failed = True
                        break
                else :
                    all_klines.append(kline)            
            cur = kline[6] + 1      #结束时间戳+1，即下一个K线的开始时间戳
            if cur >= end :
                log_adapter.color_print('重要：当前K线({}/{})结束时间戳={}({})已达到或超过结束时间，结束循环2。'.format(i, len(klines), 
                    kline[6], utility.timestamp_to_string(kline[6])), log_adapter.COLOR.YELLOW)
                expired = True
                break

        if len(klines) < LIMIT:
            log_adapter.color_print('重要：获取K线量={}，小于LIMIT({})，结束循环3。'.format(len(klines), LIMIT), log_adapter.COLOR.YELLOW)
            expired = True
            break

        if failed or cur >= end:
            break
        time.sleep(1)   #防止请求过快

    if failed:
        log_adapter.color_print('异常：保存({}-{}-{})K线数据过程中出错！'.format(year, month, day), log_adapter.COLOR.RED)
        return False
    if len(all_klines) > 0:
        begin = all_klines[0][0]
        log_adapter.color_print('重要：结束循环的收尾：剩余K线数量={}, begin={}，end={}...'.format(len(all_klines),
            utility.timestamp_to_string(begin), utility.timestamp_to_string(all_klines[-1][6])), log_adapter.COLOR.YELLOW)
        if _save(symbol, su, begin, all_klines) :
            log_adapter.color_print('重要：收尾保存K线单元数据成功，K线数={}。'.format(len(all_klines)), log_adapter.COLOR.GREEN)
            all_klines.clear()
        else :
            log_adapter.color_print('异常：收尾保存K线单元数据失败，K线数={}。'.format(len(all_klines)), log_adapter.COLOR.RED)
            return False
    
    return True

def _spider_days() :
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

    su = save_unit(kline_interval.d1)
    #su = save_unit(kline_interval.m3, multiple=5)
    for year in range(2025, 2026):
        if save_klines(trade_symbol.BTCUSDT, su, year, 0, 0) :
            log_adapter.color_print('重要：获取并保存({}年)K线数据完成。'.format(year), log_adapter.COLOR.GREEN)
        else :
            log_adapter.color_print('异常：获取并保存({}年)K线数据失败'.format(year), log_adapter.COLOR.RED)
            break
        time.sleep(2)

    if LOG_FLAG == 1 :
        sys.stdout = tmp_out
        sys.stderr = tmp_err
    print("KLine Spider End.")
    return

def _spider_hours() :
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
    #su = save_unit(kline_interval.m3, multiple=5)

    YEAR = 2025
    for month in range(1, 3):
        if save_klines(trade_symbol.BTCUSDT, su, YEAR, month, 0) :
            log_adapter.color_print('重要：获取并保存({}-{})K线数据完成。'.format(YEAR, month), log_adapter.COLOR.GREEN)
        else :
            log_adapter.color_print('异常：获取并保存({}-{})K线数据失败'.format(YEAR, month), log_adapter.COLOR.RED)
            break
        time.sleep(2)

    if LOG_FLAG == 1 :
        sys.stdout = tmp_out
        sys.stderr = tmp_err
    print("KLine Spider End.")
    return

#_spider_days()
#_spider_hours()
