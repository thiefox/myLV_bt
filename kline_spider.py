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
import copy

from enum import Enum

import draw
from base_item import trade_symbol, kline_interval

import data_loader
from fin_util import prices_info

class simple_account() :
    DEFAULT_FEE = 0.001
    MIN_BUY_AMOUNT = 0.0001
    def __init__(self, cash : float = 0) :
        self.__cash = cash
        self.__amount = float(0)
        #simple_account为全买全卖模式
        #如amount>0，day为最后一次买入日期；amount=0，day为最后一次卖出日期。
        self.day = ''       #日期，格式为YYYY-MM-DD
        return
    @property
    def cash(self) -> float:
        return round(self.__cash, 2)
    @property
    def amount(self) -> float:
        return self.__amount
    #充值
    def deposit(self, cash : float) :
        self.__cash += cash
        return
    #提现
    def withdraw(self, cash : float) -> bool :
        if cash > self.__cash:
            return False
        self.__cash = round(self.__cash - cash, 2)
        return True
    #计算最大可买数量
    def max_buy_amount(self, price : float, fee : float = DEFAULT_FEE) -> float :
        return round(self.__cash / price * (1 - fee), 4)
    def _buy(self, amount : float, price : float, fee : float = DEFAULT_FEE) :
        self.__amount += amount
        self.__cash = round(self.__cash - (amount * price) * (1 + fee), 2)
        return
    #买入
    def buy(self, amount : float, price : float, day : str, fee : float) -> bool :
        if amount * price > self.__cash:
            return False
        self._buy(amount, price, fee)
        self.day = day
        return True
    #满仓买入
    def buy_all(self, price : float, day : str, fee : float) -> float:
        amount = self.max_buy_amount(price, fee)
        self.buy(amount, price, day, fee)
        return amount
    
    def _sell(self, amount : float, price : float, fee : float = DEFAULT_FEE) :
        self.__amount -= amount
        self.__cash = round(self.__cash + amount * price * (1 - fee), 2)
        return
    #卖出
    def sell(self, amount : float, price : float, day : str, fee : float) -> bool :
        if amount > self.__amount or amount == 0:
            return False
        self._sell(amount, price, fee)
        self.day = day
        return True
    # 清仓卖出
    def sell_all(self, price : float, day : str, fee : float) :
        self.sell(self.__amount, price, day, fee)
        return
    #计算持仓价值
    def hold_asset(self, price : float) -> float:
        return round(self.__amount * price, 2)
    #计算总价值（资金+持仓）
    def total_asset(self, price : float) -> float:
        return round(self.__cash + self.hold_asset(price), 2)
    #计算持仓天数
    def hold_days(self, day : str) -> int:
        if self.__amount == 0:
            return 0
        assert(self.day != '' and day != '')
        #计算两个YYYY-MM-DD日期之间的天数
        d1 = datetime.strptime(self.day, "%Y-%m-%d")
        d2 = datetime.strptime(day, "%Y-%m-%d")
        delta = d2 - d1
        return delta.days

    def __str__(self) -> str:
        return f"cash={self.__cash}, amount={self.__amount}"

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

#获取一年的K线数据并保存到文件
def get_BTC_klines_year(year : int, interval : kline_interval):
    for i in range(1, 13):
        result = save_kline(trade_symbol.BTCUSDT, year, i, interval)
        if result == 0:
            print('获取({}-{})K线数据已达到或超过当前时间，处理结束。'.format(year, i))
            break
        time.sleep(3)
    return

def draw_klines(b_year : int, e_year : int, interval : kline_interval):
    if e_year - b_year == 1:
        UNIT = 'M'
    else :
        UNIT = 'Y'    
    klines = data_loader.load_klines_years(trade_symbol.BTCUSDT, b_year, e_year, interval)
    if klines:
        print('共获取到K线数据记录={}'.format(len(klines)))
        dates = [utility.timestamp_to_datetime(kline[0]) for kline in klines]
        #把dates转换为numpy数组
        dates = numpy.array(dates)
        closed_prices = [float(kline[4]) for kline in klines]
        draw.draw_kline(dates, closed_prices, XUnit=UNIT)
    else:
        print("Failed to fetch kline data.")
    return

def calculate_macd(klines : list) -> tuple:
    close_prices = [float(kline[4]) for kline in klines]
    #ar = numpy.asarray(close_prices)
    #DIF(macd)=差离值=快线
    #DEA(signal)=差离值平均数=慢线
    #第三个值macd_hist对应于macd的差值，即macd_hist=macd-signal。也即是所谓的红绿能量柱值。
    # /MACD
    # 金叉的意思就是快线（股票行情指标的短期线）向上穿越慢线（长期线）的交叉；死叉反之。通常情况下，金叉是买进信号，死叉为卖出信号。
    macd, signal, hist = getattr(talib, 'MACD')(numpy.array(close_prices),  fastperiod=12, slowperiod=26, signalperiod=9)
    print('共计算出MACD记录数={}'.format(len(macd)))
    print('开始打印MACD原始值...')
    for i in range(len(macd)):
        '''
        if i >= 33 :    #macd和signal的前33个值为0(nan)
            print('index={}, macd={}, signal={}, hits={}'.format(i, macd[i], signal[i], hist[i]))
        '''
        pass
    print('打印MACD原始值结束.')
    return macd, signal

#计算MACD交叉点
def find_macd_crossovers(macd : list, signal : list) -> list:
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
    klines = data_loader.load_klines_years(2017, 2025, interval)
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

#计算总资产
def calc_total_asset(cash : float, amount : float, price : float) -> float:
    #assert(isinstance(amount, float))
    assert(isinstance(price, float))
    return round(cash + amount * price, 2)

#以每个峰值为起点，找出最大的一段连续回撤（即最大的一段连续下降区间）
#bi和ei为最大连续回撤的开始和结束索引，ei为有效区间
def calc_max_drawdown_with_every_peak(prices : list) -> tuple:
    max_drawdown = 0        #最大回撤
    max_asset = 0           #最大资产
    bi = ei = 0
    for i in range(1, len(prices)):
        asset = prices[i]
        if asset > max_asset or asset == prices[i-1] :
            max_asset = asset
            temp_bi = i
        else :
            drawdown = (max_asset - asset) / max_asset
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                bi = temp_bi
                ei = i
    return max_drawdown, bi, ei


#打印列表区间, hint=0不检查，1检查升序，2检查降序
def print_list_range(lst: list, start: int, end: int, hint : int=0):
    if start < 0 or end > len(lst) or start > end:
        print("异常：无效列表或区间！")
        return
    for i in range(start, end+1):
        print('第{}个={}'.format(i, lst[i]))
    #检查区间的值是否有序
    if hint == 1 or hint == 2:
        for i in range(start+1, end+1):
            if hint == 1:
                if lst[i] < lst[i-1]:
                    print('异常：第{}个值{}小于第{}个值{}'.format(i, lst[i], i-1, lst[i-1]))
            elif hint == 2:
                if lst[i] > lst[i-1]:
                    print('异常：第{}个值{}大于第{}个值{}'.format(i, lst[i], i-1, lst[i-1]))
    return

#计算持仓总天数和最长的一次持仓天数
def calc_hold_days_with_profit(profits : list) -> tuple:
    all_days = 0
    longest = 0
    cur_days = 0
    for i in range(1, len(profits)):
        if profits[i] - profits[i-1] != 0:
            all_days += 1
            cur_days += 1
        else :
            if cur_days > longest :
                longest = cur_days
            cur_days = 0
    return all_days, longest

def calc_hold_days_with_accounts(accounts : list) -> tuple:
    all_days = 0
    longest = 0
    cur_days = 0
    for i in range(0, len(accounts)):
        if accounts[i].amount > 0:
            all_days += 1
            cur_days += 1
        else :
            if cur_days > longest :
                longest = cur_days
            cur_days = 0
    return all_days, longest

#生成MACD模式的每日收益曲线
def calc_MACD_daily_profit(year_begin : int, year_end : int, interval : kline_interval) -> list:
    MAX_DRAWDOWN = 0.1          #最大允许回撤
    INIT_CASH = 10000
    cash = float(INIT_CASH)     #初始资金
    amount = float(0)       #持有的币数量
    fee = 0.001
    buy_price = 0
    klines = data_loader.load_klines_years(trade_symbol.BTCUSDT, year_begin, year_end, interval)
    print('共载入的K线数据记录={}'.format(len(klines)))
    if len(klines) == 0:
        return list()
    INIT_PRICE = round(float(klines[0][1]), 4)
    print('开始计算MACD模式的每日收益...')
    dates = [utility.timestamp_to_string(kline[0]) for kline in klines]
    #把dates转换为numpy数组
    dates = numpy.array(dates)
    closed_prices = [float(kline[4]) for kline in klines]
    macd, signal = calculate_macd(klines)
    assert(isinstance(macd, numpy.ndarray))
    assert(len(macd) == len(klines))
    profits = [0] * len(macd)       #每日的收益
    profits[0] = cash
    crossovers = find_macd_crossovers(macd, signal)
    print('共找到{}个MACD交叉点'.format(len(crossovers)))
    for crossover in crossovers:        #叉叉处理(金叉买入，死叉卖出)
        index, type, cur, before = crossover
        closed_price = klines[index][4]
        closed_price = float(closed_price)
        time_str = utility.timestamp_to_string(klines[index][0])
        #计算这个叉跟前个叉之间的每日收益
        for i in range(index-1, 0, -1):
            if profits[i] == 0:
                profits[i] = calc_total_asset(cash, amount, float(klines[i][4]))
            else :
                break
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
                print('金叉买入({})，价格={}, 币总数量={}, 金额={}，剩余总资金={}.合计={}'.format(time_str, buy_price, amount, 
                    amount*buy_price, cash, calc_total_asset(cash, amount, buy_price)))
                profits[index] = calc_total_asset(cash, amount, closed_price)
            else :
                print('金叉买入，资金不足={}'.format(cash))
        else :  #死叉
            if amount > 0:
                sell_price = float(klines[index][4])
                sell_cash = amount * sell_price * (1 - fee)
                cash += sell_cash
                cash = round(cash, 2)
                print('死叉卖出({})，价格={}, 数量={}, 卖出获利={}. 合计={}'.format(time_str, sell_price, amount, sell_cash, cash))
                amount = 0
                profits[index] = calc_total_asset(cash, amount, closed_price)
            else :
                print('死叉卖出，无持仓. 合计={}'.format(cash))

    for i in range(len(profits)-1, 0, -1):
        if profits[i] == 0:
            profits[i] = calc_total_asset(cash, amount, float(klines[i][4]))
        else :
            break
    #最后一天卖出
    if amount > 0:
        sell_price = float(closed_prices[-1])
        time_str = utility.timestamp_to_string(klines[-1][0])
        cash += round(amount * sell_price * (1 - fee), 2)
        amount = 0
        print('最后卖出({})，价格={}, 数量={}, 合计={}'.format(time_str, sell_price, amount, cash))
    LAST_PRICE = float(closed_prices[-1])
    print('起始资金={}, 起始币数量={}, 起始币价格={}'.format(INIT_CASH, 0, INIT_PRICE))
    print('最终资金={}, 收益={}. 最终币价格={}'.format(cash, cash-INIT_CASH, LAST_PRICE))
    if profits[-1] == 0:
        profits[-1] = calc_total_asset(cash, amount, float(closed_prices[-1]))
    info = calc_max_drawdown_with_every_peak(profits)
    print('MACD最大连续回撤={:.2f}%, bi={}, ei={}'.format(info[0]*100, info[1], info[2]))
    before = profits[info[1]-1]
    after = profits[info[2]]
    print('MACD模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
    print('MACD模式最大连续回撤的前一天={}'.format(before))
    print_list_range(profits, info[1]-1, info[2]+1, hint=0)
    print('MACD模式最大连续回撤的后一天={}'.format(after))
    info = calc_hold_days_with_profit(profits)
    print('MACD模式PROFIT计算，总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))

    #开始计算起始买币，最终卖币收益
    amount = INIT_CASH/INIT_PRICE
    cash = round(amount * LAST_PRICE * (1 - fee), 2)
    print('持仓模式最终资金={}, 收益={}'.format(cash, cash-INIT_CASH))        
    info = calc_max_drawdown_with_every_peak(closed_prices)
    print('持仓模式最大连续回撤={:.2f}%, bi={}, ei={}'.format(info[0]*100, info[1], info[2]))
    before = closed_prices[info[1]-1]
    after = closed_prices[info[2]]
    print('持仓模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
    print('持仓模式最大连续回撤的前一天={}'.format(before))
    print_list_range(closed_prices, info[1]-1, info[2]+1, hint=0)
    print('持仓模式最大连续回撤的后一天={}'.format(after))
    '''
    print('开始打印每日收益...')
    for i in range(len(profits)):
        print('index={}, date={}, profit={}'.format(i, dates[i], profits[i]))
    print('打印每日收益结束.')
    '''
    return profits

#生成带最大回撤的MACD模式每日收益曲线
#默认最大回撤为10%
def calc_MACD_daily_profit_with_drawdown(year_begin : int, year_end : int, interval : kline_interval, MAX_DRAWDOWN = 0.1) -> list:
    INIT_CASH = 10000
    cash = float(INIT_CASH)     #初始资金
    amount = float(0)       #持有的币数量
    fee = 0.001
    buy_price = 0
    klines = data_loader.load_klines_years(trade_symbol.BTCUSDT, year_begin, year_end, interval)
    print('共载入的K线数据记录={}'.format(len(klines)))
    if len(klines) == 0:
        return list()
    INIT_PRICE = round(float(klines[0][1]), 4)
    print('开始计算MACD模式的每日收益...')
    dates = [utility.timestamp_to_string(kline[0]) for kline in klines]
    #把dates转换为numpy数组
    dates = numpy.array(dates)
    closed_prices = [float(kline[4]) for kline in klines]
    pi = prices_info(closed_prices)
    macd, signal = calculate_macd(klines)
    assert(isinstance(macd, numpy.ndarray))
    assert(len(macd) == len(klines))
    crossovers = find_macd_crossovers(macd, signal)
    print('共找到{}个MACD交叉点'.format(len(crossovers)))
    accounts = [simple_account()] * len(macd)       #每日的账户信息
    accounts[0].deposit(INIT_CASH)                  #初始资金
    gold_ops = list()       #金叉操作
    dead_ops = list()       #死叉操作
    draw_ops = list()       #回撤操作
    gold_ignore_ops = list()    #忽略的金叉
    dead_ignore_ops = list()    #忽略的死叉
    operations = list()     #操作记录
    for i in range(1, len(klines)):
        handled = False
        accounts[i] = copy.deepcopy(accounts[i-1])  #复制前一天的账户信息
        date_str = datetime.strptime(dates[i], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        print('处理第{}天={}...'.format(i, date_str))
        if accounts[i].amount > 0:  #当前为持仓状态
            # 只保留年月日
            hold_days = accounts[i].hold_days(date_str)
            assert(i > hold_days)
            prefit = pi.calc_profit_scale(i-hold_days, i)
            print('持仓天数={}，日期={}，币价={}，持仓收益={:.2f}%'.format(hold_days, date_str, closed_prices[i], prefit*100))
            info = pi.find_prev_peak(i)
            assert(info[1] >= 0)
            print('前一个峰值币价={}，索引={}'.format(info[0], info[1]))
            prefit = pi.calc_profit_scale(info[1], i)
            print('前一个峰值到当前日期的收益={:.2f}%'.format(prefit*100))
            #info = calc_max_drawdown_with_every_peak(closed_prices[i-hold_days:i])
            #if info[0] > MAX_DRAWDOWN:
            if prefit < -MAX_DRAWDOWN:
                print('重要：日期={}，持仓{}天后的回撤已超过上限={:.2f}%，清仓...'.format(date_str, hold_days, prefit*100))
                sell_price = closed_prices[i]
                print('通知：日期={}，操作=卖出(回撤)，价格={}, 数量={}...'.format(date_str, sell_price, accounts[i].amount))
                accounts[i].sell_all(sell_price, date_str, fee)
                print('通知：回撤卖出操作完成，当前资金={}, 当前币数={}。'.format(accounts[i].cash, accounts[i].amount))
                draw_ops.append(i)
                operations.append(i)
                handled = True

        if not handled and i in [c[0] for c in crossovers]:
            index = [c[0] for c in crossovers].index(i)
            if crossovers[index][1] == '金叉':
                if accounts[i].amount == 0:
                    buy_price = float(klines[i][4])
                    print('重要：日期={}，出现金叉，可用资金={}, 币价={}, 可买数量={}'.format(date_str, accounts[i].cash, 
                        buy_price, accounts[i].max_buy_amount(buy_price, fee)))
                    amount = accounts[i].buy_all(buy_price, date_str, fee)
                    assert(amount > 0)
                    print('重要：日期={}, 金叉买入操作完成，当前资金={}, 当前币数={}。'.format(date_str, accounts[i].cash, accounts[i].amount))
                    gold_ops.append(i)
                    operations.append(i)
                    handled = True
                else :
                    gold_ignore_ops.append(i)
                    print('异常：日期={}, 金叉买入信号，已为持仓状态(资金={}，持币={})，放弃该金叉。'.format(date_str, 
                        accounts[i].cash, accounts[i].amount))
            else :
                assert(crossovers[index][1] == '死叉')
                if accounts[i].amount > 0:
                    sell_price = float(klines[i][4])
                    print('重要：日期={}，出现死叉，卖出操作，价格={}, 数量={}...'.format(date_str, sell_price, accounts[i].amount))
                    accounts[i].sell_all(sell_price, date_str, fee)
                    print('重要：日期={}, 死叉卖出操作完成，当前资金={}, 当前币数={}。'.format(date_str, accounts[i].cash, accounts[i].amount))
                    dead_ops.append(i)
                    operations.append(i)
                    handled = True
                else :
                    dead_ignore_ops.append(i)
                    print('异常：日期={}, 死叉卖出信号，无持仓状态(资金={}，持币={})，放弃该死叉。'.format(date_str, accounts[i].cash, accounts[i].amount))
        else :
            #保持上一天的状态
            if i in [c[0] for c in crossovers] :
                index = [c[0] for c in crossovers].index(i)
                if crossovers[index][1] == '金叉':
                    gold_ignore_ops.append(i)
                else :
                    assert(crossovers[index][1] == '死叉')
                    dead_ignore_ops.append(i)
            pass
            
    #最后一天卖出
    if accounts[-1].amount > 0:
        sell_price = float(klines[-1][4])
        date_str = datetime.strptime(dates[-1], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        print('重要：最后一天卖出操作，日期={}, 价格={}, 数量={}...'.format(date_str, sell_price, accounts[-1].amount))
        accounts[-1].sell_all(sell_price, date_str, fee)
        operations.append(len(accounts)-1)
        
    print('------------------------------------------------------------')
    assert(accounts[-1].amount == 0)
    print('重要：MACD模式最终资金=={}, 最终币数={}。'.format(accounts[-1].cash, accounts[-1].amount))

    profits = [0] * len(accounts)
    for i in range(len(accounts)):
        profits[i] = accounts[i].total_asset(closed_prices[i])

    print('起始资金={}, 起始币数量={}, 起始币价格={}, 结束币价格={}'.format(INIT_CASH, 0, INIT_PRICE, closed_prices[-1]))
    print('MACD模式最终资金={}, 最终收益={}.'.format(accounts[-1].cash, accounts[-1].cash-INIT_CASH))
    
    print('金叉买入次数={}, 金叉买入列表={}.'.format(len(gold_ops), ', '.join([str(x) for x in gold_ops])))
    print('死叉卖出次数={}, 死叉卖出列表={}.'.format(len(dead_ops), ', '.join([str(x) for x in dead_ops])))
    print('回撤卖出次数={}, 回撤卖出列表={}.'.format(len(draw_ops), ', '.join([str(x) for x in draw_ops])))
    print('忽略金叉次数={}, 忽略金叉列表={}.'.format(len(gold_ignore_ops), ', '.join([str(x) for x in gold_ignore_ops])))
    print('忽略死叉次数={}, 忽略死叉列表={}.'.format(len(dead_ignore_ops), ', '.join([str(x) for x in dead_ignore_ops])))
    print('开始打印买卖操作...')
    BUY_OP = True
    for index in range(0, len(operations)):
        i = operations[index]
        date_str = datetime.strptime(dates[i], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        if BUY_OP:
            print('金叉买入：i={}，日期={}，价格={}，数量={}，剩余资金={}. 总值={}.'.format(i, date_str, closed_prices[i],
                accounts[i].amount, accounts[i].cash, profits[i]))
            BUY_OP = False
        else :
            REASON = '死叉'
            buy_i = operations[index-1]
            profit = pi.calc_profit_scale(buy_i, i)
            if i in draw_ops:
                REASON = '回撤'
            print('({})卖出：i={}，日期={}，价格={}，数量={}，操作收益={:.2f}%. 剩余资金={}. 总值={}.'.format(REASON, i,
                date_str, closed_prices[i], accounts[i-1].amount, profit*100, accounts[i].cash, profits[i]))
            BUY_OP = True
    print('打印买卖操作结束.')
    info = calc_max_drawdown_with_every_peak(profits)
    begin_str = datetime.strptime(dates[info[1]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    end_str = datetime.strptime(dates[info[2]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    print('MACD最大连续回撤={:.2f}%, bi={}={}, ei={}={}'.format(info[0]*100, info[1], begin_str, info[2], end_str))
    before = profits[info[1]-1]
    after = profits[info[2]+1]
    print('MACD模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
    print('MACD模式最大连续回撤的前一天={}'.format(before))
    print_list_range(profits, info[1], info[2], hint=0)
    print('MACD模式最大连续回撤的后一天={}'.format(after))
    info = calc_hold_days_with_accounts(accounts)
    print('MACD模式ACCOUNTS计算，总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    info = calc_hold_days_with_profit(profits)
    print('MACD模式PROFIT计算，总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    print('------------------------------------------------------------')
    #开始计算起始买币，最终卖币收益
    amount = INIT_CASH/INIT_PRICE
    cash = round(amount * closed_prices[-1] * (1 - fee), 2)
    print('持仓模式最终资金={}, 最终收益={}'.format(cash, cash-INIT_CASH))        
    info = calc_max_drawdown_with_every_peak(closed_prices)
    begin_str = datetime.strptime(dates[info[1]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    end_str = datetime.strptime(dates[info[2]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    print('持仓模式最大连续回撤={:.2f}%, bi={}={}, ei={}={}'.format(info[0]*100, info[1], begin_str, info[2], end_str))
    before = closed_prices[info[1]-1]
    after = closed_prices[info[2]+1]
    print('持仓模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
    print('持仓模式最大连续回撤的前一天={}'.format(before))
    #print_list_range(closed_prices, info[1], info[2], hint=0)
    print('持仓模式最大连续回撤的后一天={}'.format(after))
    '''
    print('开始打印每日收益...')
    for i in range(len(profits)):
        print('index={}, date={}, profit={}'.format(i, dates[i], profits[i]))
    print('打印每日收益结束.')
    '''
    return profits


def draw_kline_and_profit(b_year : int, e_year : int, interval : kline_interval):
    if e_year - b_year == 1:
        UNIT = 'M'
    else :
        UNIT = 'Y'
    klines = data_loader.load_klines_years(trade_symbol.BTCUSDT, b_year, e_year, interval)
    if klines:
        print('共获取到K线数据记录={}'.format(len(klines)))
        dates = [utility.timestamp_to_datetime(kline[0]) for kline in klines]
        #把dates转换为numpy数组
        dates = numpy.array(dates)
        closed_prices = [float(kline[4]) for kline in klines]
        #profits = calc_MACD_daily_profit(b_year, e_year, interval)
        profits = calc_MACD_daily_profit_with_drawdown(b_year, e_year, interval, MAX_DRAWDOWN=0.1)
        draw.draw_kline_and_profile(dates, closed_prices, profits, XUnit=UNIT)
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

    #sys.stdout = log_adapter.LoggerWriter(logger, logging.INFO)
    #sys.stderr = log_adapter.LoggerWriter(logger, logging.ERROR)

    #get_BTC_klines_year(2024, kline_interval.d1)
    #test_calc_macd(kline_interval.d1)
    #calc_MACD_daily_profit(2018, 2019, kline_interval.d1)
    #calc_MACD_daily_profit(2017, 2025, kline_interval.d1)
    #draw_klines(2023, 2024, kline_interval.d1)
    draw_kline_and_profit(2017, 2025, kline_interval.d1)

    sys.stdout = tmp_out
    sys.stderr = tmp_err
    print("KLine Spider End.")

