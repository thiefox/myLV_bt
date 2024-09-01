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
import numpy
import talib

from enum import Enum

class kline_interval(str, Enum):
    h1 = '1h'
    h4 = '4h'
    h6 = '6h'
    h12 = '12h'
    d1 = '1d'

#int时间戳转换为字符串时间
def timestamp_to_string(time_stamp : int) -> str:
    #print('input={}'.format(time_stamp/1000))
    
    time_array = time.localtime(float(time_stamp/1000))
    str_date = time.strftime("%Y-%m-%d %H:%M:%S", time_array)
    return str_date

#字符串时间转换为int时间戳
def string_to_timestamp(str_date : str) -> int:
    #print('input={}'.format(str_date))
    time_array = time.strptime(str_date, "%Y-%m-%d %H:%M:%S")
    time_stamp = int(time.mktime(time_array) * 1000)
    return time_stamp

def get_kline_data(symbol : str, inter : kline_interval, begin : int, limit : int) -> list:
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

def get_BTC_klines_year(year : int, interval : kline_interval):
    symbol = "BTCUSDT"
    for i in range(1, 13):
        result = save_kline(symbol, year, i, interval)
        if result == 0:
            print('获取({}-{})K线数据已达到或超过当前时间，处理结束。'.format(year, i))
            break
        time.sleep(3)
    return

#载入K线数据文件
def load_klines(year : int, month : int, interval : kline_interval) -> list:
    file_name = utility.gen_kline_file_name("BTCUSDT", year, month, interval.value)
    if not os.path.exists(file_name):
        file_name = utility.gen_kline_file_name("BTCUSDT", year, month, interval.value.upper())
        if not os.path.exists(file_name):
            print('K线数据文件{}不存在'.format(file_name))
            return list()
    klines = list()
    try :
        with open(file_name, 'r') as f:
            klines = json.load(f)
    except Exception as e:
        print('读取K线数据文件{}失败={}'.format(file_name, e))
    return klines

#载入一年的K线数据
def load_klines_year(year : int, interval : kline_interval) -> list:
    klines = list()
    for i in range(1, 13):
        month_klines = load_klines(year, i, interval)
        if len(month_klines) > 0:
            klines.extend(month_klines)
        else :
            print('异常：未获取到{}年-{}月的K线数据'.format(year, i))
    return klines

def calculate_macd(klines) -> tuple:
    close_prices = [float(kline[4]) for kline in klines]
    #ar = numpy.asarray(close_prices)
    #DIF(macd)=差离值=快线
    #DEA(signal)=差离值平均数=慢线
    #第三个值macd_hist对应于macd的差值，即macd_hist=macd-signal。也即是所谓的红绿能量柱值。
    # /MACD
    # 金叉的意思就是快线（股票行情指标的短期线）向上穿越慢线（长期线）的交叉；死叉反之。通常情况下，金叉是买进信号，死叉为卖出信号。
    macd, signal, hist = talib.MACD(numpy.array(close_prices))
    print('共计算出MACD记录数={}'.format(len(macd)))
    print('开始打印MACD原始值...')
    for i in range(len(macd)):
        if i >= 33 :    #macd和signal的前33个值为0(nan)
            print('index={}, macd={}, signal={}, hits={}'.format(i, macd[i], signal[i], hist[i]))
    print('打印MACD原始值结束.')
    return macd, signal

#计算MACD交叉点
def find_macd_crossovers(macd, signal) -> list:
    crossovers = []
    for i in range(1, len(macd)):
        if macd[i] > signal[i] and macd[i-1] < signal[i-1]:
            if (macd[i] > 0 and signal[i] > 0) or (macd[i] < 0 and signal[i] < 0):  #同在0轴上或同在0轴下
                crossovers.append((i, '金叉', macd[i]-signal[i], macd[i-1]-signal[i-1]))
            else :
                print('异常：金叉时macd={}, signal={}，忽略'.format(macd[i], signal[i]))
        elif macd[i] < signal[i] and macd[i-1] > signal[i-1]:
            if (macd[i] > 0 and signal[i] > 0) or (macd[i] < 0 and signal[i] < 0):  #同在0轴上或同在0轴下
                crossovers.append((i, '死叉', macd[i]-signal[i], macd[i-1]-signal[i-1]))
            else :
                print('异常：死叉时macd={}, signal={}，忽略'.format(macd[i], signal[i]))
    return crossovers

def test_calc_macd(interval : kline_interval):
    #begin = utility.string_to_timestamp('2024-01-01 00:00:00')
    #klines = get_kline_data("BTCUSDT", 6, begin, 100)
    klines = list()
    for i in range(2017, 2025):
        print('处理年份={}'.format(i))
        klines.extend(load_klines_year(i, interval))

    if klines:
        print('共获取到K线数据记录={}'.format(len(klines)))
        macd, signal = calculate_macd(klines)
        print('共获取到MACD记录数={}'.format(len(macd)))
        assert(len(macd) == len(klines))
        #print("MACD:", macd)
        #print("Signal:", signal)

        crossovers = find_macd_crossovers(macd, signal)
        print('共找到{}个MACD交叉点'.format(len(crossovers)))
        for crossover in crossovers:
            index, type, cur, before = crossover
            closed_price = klines[index][4]
            print(f"MACD {type} crossover at index {index}, 收盘价={closed_price}, 当前值={cur}, 前一个={before}")
    else:
        print("Failed to fetch kline data.")
    return

#原始资金1万，遇到金叉买入，遇到死叉卖出，交易手续费0.1%，计算收益
def calc_macd_profit(year_begin : int, year_end : int, interval : kline_interval) :
    cash = float(10000)     #初始资金
    amount = float(0)       #持有的币数量
    fee = 0.001
    buy_price = 0
    klines = list()
    for i in range(year_begin, year_end):
        print('处理年份={}'.format(i))
        year_lines = load_klines_year(i, interval)
        print('载入{}年的K线数据记录={}'.format(i, len(year_lines)))
        klines.extend(year_lines)
    #klines = load_klines_year(year, interval)
    print('共载入的K线数据记录={}'.format(len(klines)))
    print('开始计算历年的MACD总收益...')
    if not klines:
        return
    macd, signal = calculate_macd(klines)
    crossovers = find_macd_crossovers(macd, signal)
    print('共找到{}个MACD交叉点'.format(len(crossovers)))
    year = ''
    for crossover in crossovers:
        index, type, cur, before = crossover
        closed_price = klines[index][4]
        closed_price = float(closed_price)
        time_str = timestamp_to_string(klines[index][0])
        if year == '':
            print('第一个统计年份={}, 资金={}，持币={}，币价={}'.format(time_str[:4], cash, amount, closed_price))
            year = time_str[:4]
        elif year != time_str[:4]:
            print('------------------------------------')
            print('进入新年份={}, 资金={}，持币={}，币价={}. 合计={}'.format(time_str[:4], cash, amount, closed_price, 
                round(cash + amount * closed_price, 2)))
            year = time_str[:4]
            
        if type == '金叉':
            if cash > 0:
                buy_price = float(klines[index][4])
                useable_cash = cash * (1 - fee)
                buy_amount = round(useable_cash/buy_price, 4)
                print('金叉：可买资金={}, 币价格={}, 可买数量={}'.format(useable_cash, buy_price, buy_amount))
                cash -= (buy_amount * buy_price) * (1 + fee)
                cash = round(cash, 2)
                assert(amount >= 0)
                amount += buy_amount
                print('金叉买入({})，价格={}, 币总数量={}, 金额={}，剩余总资金={}'.format(time_str, buy_price, amount, amount*buy_price, cash))
            else :
                print('金叉买入，资金不足={}'.format(cash))
        else :
            if amount > 0:
                sell_price = float(klines[index][4])
                sell_cash = amount * sell_price * (1 - fee)
                cash += sell_cash
                cash = round(cash, 2)
                print('死叉卖出({})，价格={}, 数量={}, 卖出获利={}，剩余总资金={}'.format(time_str, sell_price, amount, sell_cash, cash))
                amount = 0
            else :
                print('死叉卖出，无持仓. 资金={}'.format(cash))

    if amount > 0:
        sell_price = float(klines[-1][4])
        time_str = timestamp_to_string(klines[-1][0])
        cash += amount * sell_price * (1 - fee)
        amount = 0
        print('最后卖出({})，价格={}, 数量={}, 金额={}'.format(time_str, sell_price, amount, amount*buy_price))
    print('最终资金={}, 收益={}'.format(cash, cash-10000))
    return 


if __name__ == '__main__':
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
    sys.stdout = log_adapter.LoggerWriter(logger, logging.INFO)
    sys.stderr = log_adapter.LoggerWriter(logger, logging.ERROR)

    #get_BTC_klines_year(2024, kline_interval.d1)
    #test_calc_macd(kline_interval.d1)
    calc_macd_profit(2017, 2025, kline_interval.d1)

    sys.stdout = tmp_out
    sys.stderr = tmp_err
    print("KLine Spider End.")

