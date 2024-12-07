from __future__ import annotations
import copy
from enum import Enum
from typing import Dict
import os
from threading import Lock

import math
from datetime import datetime, timedelta
from utils import utility

# K线周期枚举
class kline_interval(str, Enum):
    m3 = '3m'
    h1 = '1h'
    h4 = '4h'
    h6 = '6h'
    h12 = '12h'
    d1 = '1d'
    #获取周期数，秒为单位
    def get_interval_seconds(self) -> int:
        interval = 0
        if self == kline_interval.m3:
            interval = 60 * 3
        elif self == kline_interval.h1:
            interval = 3600 * 1
        elif self == kline_interval.h4:
            interval = 3600 * 4
        elif self == kline_interval.h6:
            interval = 3600 * 6
        elif self == kline_interval.h12:
            interval = 3600 * 12
        elif self == kline_interval.d1:
            interval = 3600 * 24
        return interval
    #获取周期内时间差，即同周期的结束时间-开始时间
    def get_delta(self) -> timedelta:
        interval = int(self.value[:-1])
        unit = self.value[-1]
        if unit == 'm':
            delta = timedelta(minutes=interval)
        elif unit == 'h':
            delta = timedelta(hours=interval)
        elif unit == 'd':
            delta = timedelta(days=interval)
        else :
            delta = timedelta()
        return delta
    #判断两个时间是否同一周期
    #begin: 周期的开始时间
    def is_same(self, begin : datetime, other : datetime) -> bool:
        delta = self.get_delta()
        diff = other - begin
        return diff.total_seconds() <= delta.total_seconds()
    #判断某条币安K线是否已封闭
    #begin: 开始时间戳，毫秒级
    #end: 结束时间戳，毫秒级
    #返回=0，未封闭。返回>0，封闭的秒数。返回<0，异常。
    def is_closed(self, begin : int, end : int) -> int:
        if end <= begin :
            return -1
        delta = self.get_delta()
        if delta.total_seconds() == 0 :
            return -2
        diff = (end + 1 - begin) - (delta.total_seconds()*1000)
        if diff == 0 :
            return delta.total_seconds()
        elif diff < 0 :     #未封闭
            return 0
        else :              #终止和起始时间差超出阈值，异常
            return -3
    def get_unit(self) -> str:
        return self.value[-1]

#保存单元
class save_unit() : 
    def __init__(self, interval : kline_interval, multiple : int = 0) :
        self.__inter = interval
        self.__multi = multiple
        return
    @property
    def interval(self) -> kline_interval:
        return self.__inter
    @property
    def multiple(self) -> int:
        return self.__multi
    def get_unit_seconds(self, dt : datetime) -> int:
        OMS = 60        #1分钟秒数
        seconds = 0
        UNIT = self.interval.get_unit()
        delta = self.interval.get_delta()
        if self.multiple > 0 :
            seconds = self.multiple * int(delta.total_seconds())
        else :
            if UNIT == 'm':     #分钟K线
                seconds = OMS * 60      #默认保存单位为1小时
            elif UNIT == 'h':   #小时K线
                seconds = OMS * 60 * 24      #默认保存单位为1天
            elif UNIT == 'd':   #日K线
                seconds = OMS * 60 * 24 * utility.days_in_month(dt.year, dt.month)      #默认保存单位为1月
        return seconds
    #获取保存周期的（理论）开始时间戳，毫秒级
    #实际的数据不一定从这个时间开始，如第一条数据可能是2017-08-17 04:00:00
    #pos: 当前位置时间戳，毫秒级
    def get_default_begin(self, pos : int) -> int:
        begin = 0
        pos_t = utility.timestamp_to_datetime(pos)
        UNIT = self.interval.get_unit()
        if UNIT == 'm':
            begin = utility.string_to_timestamp(pos_t.strftime("%Y-%m-%d %H:00:00"))
        elif UNIT == 'h':
            begin = utility.string_to_timestamp(pos_t.strftime("%Y-%m-%d 00:00:00"))
        elif UNIT == 'd':
            begin = utility.string_to_timestamp(pos_t.strftime("%Y-%m-01 00:00:00"))
        else :
            assert(False)
            pass
        return begin
    #取得一个文件里的记录数
    def items_per_file(self, year : int = 0, month : int = 0) -> int :
        items = 0
        if self.multiple > 0 :
            items = self.multiple
        else :
            UNIT = self.interval.get_unit()
            if UNIT == 'm':
                items = 60
            elif UNIT == 'h':
                items = 24
            elif UNIT == 'd':
                assert(year > 0 and month > 0)
                items = utility.days_in_month(year, month)
        return items
    #判断是否同一保存周期（同一数据文件）
    #base: 基准时间戳，毫秒级（注：base不一定为周期的开始）
    #如self.multiple>0，则base必须为周期的开始时间戳
    #check: 待检查时间戳，毫秒级
    #HEADER: check是否为头部时间戳，即是否为周期的开始时间戳
    def is_same_unit(self, base : int, check : int, HEADER=True) -> bool:
        if self.multiple > 0 :
            begin = base
        else :
            begin = self.get_default_begin(base)
        if begin == 0 :
            assert(False)
            return False
        assert(check >= begin)
        if check < begin :
            return False
        win = self.get_unit_seconds(begin) * 1000
        diff = win - (check - begin)
        print('重要：base={}, begin={}, check={}, HEADER={}, WIN={}, diff={}'.format(base, begin, check, HEADER, win, diff))
        s_begin = utility.timestamp_to_string(begin)
        s_base = utility.timestamp_to_string(base)
        s_check = utility.timestamp_to_string(check)
        print('重要：begin时间={}, base时间={}, check时间={}'.format(s_begin, s_base, s_check))
        return diff > 0 if HEADER else diff >= 0
    #获取保存的末级目录单位
    def get_save_dir(self, begin : datetime) -> str :
        dir = ''
        UNIT = self.interval.get_unit()
        if UNIT == 'm':     #分钟K线，末级目录为天
            dir = '{}\\{:0>2}\\{:0>2}'.format(begin.year, begin.month, begin.day)
        elif UNIT == 'h':   #小时K线，末级目录为月
            dir = '{}\\{:0>2}'.format(begin.year, begin.month)
        elif UNIT == 'd':   #日K线，末级目录为年
            dir = '{}'.format(begin.year)
        return dir
    #获取保存的文件名
    def get_save_file(self, begin : datetime) -> str :
        file = ''
        UNIT = self.interval.get_unit()
        if UNIT == 'm':
            if self.multiple == 0 :
                file = '{}-{:0>2}-{:0>2}-{:0>2}-{}.json'.format(begin.year, begin.month, begin.day, begin.hour, self.interval.value)
            else :
                file = '{}-{:0>2}-{:0>2}-{:0>2}-{:0>2}-{}.json'.format(begin.year, begin.month, begin.day,
                    begin.hour, begin.minute, self.interval.value)
        elif UNIT == 'h':
            if self.multiple == 0 :
                file = '{}-{:0>2}-{:0>2}-{}.json'.format(begin.year, begin.month, begin.day, self.interval.value)
            else :
                file = '{}-{:0>2}-{:0>2}-{:0>2}-{}.json'.format(begin.year, begin.month, begin.day, begin.hour, self.interval.value)
        elif UNIT == 'd':
            if self.multiple == 0 :
                file = '{}-{:0>2}-{}.json'.format(begin.year, begin.month, self.interval.value)
            else :
                file = '{}-{:0>2}-{:0>2}-{}.json'.format(begin.year, begin.month, begin.day, self.interval.value)
        return file   
    #计算K线偏移量
    #count: K线数量
    #如begin=0则从当前时间开始计算
    #返回毫秒时间戳
    def calc_offset(self, count : int, begin=0, BACK=True) -> int:
        offset = 0
        if begin <= 0 :
            begin = int(datetime.now().timestamp()) * 1000
        if BACK :
            offset = begin - count * self.interval.get_interval_seconds() * 1000
        else :
            offset = begin + count * self.interval.get_interval_seconds() * 1000
        assert(offset > 0)
        return offset


            

class trade_symbol(str, Enum):
    BTCUSDT = 'BTCUSDT'
    ETHUSDT = 'ETHUSDT'
    def get_base(self) -> str:
        return self.value[:3]
    def get_quote(self) -> str:
        return self.value[3:]
    def get_BTC_USDT() -> trade_symbol:
        return trade_symbol.BTCUSDT
    def get_ETH_USDT() -> trade_symbol:
        return trade_symbol.ETHUSDT
    def get_BTC_name() -> str:
        return 'BTC'
    def get_USDT_name() -> str:
        return 'USDT'
    def get_symbol_with_USDT(asset : str) -> trade_symbol :
        return trade_symbol(asset + trade_symbol.get_USDT_name())

class TRADE_STATUS(Enum):
    IGNORE = 0
    BUY = 1
    SELL = 2
    HANDLED = 10        #该条K线已处理过

class MACD_CROSS(Enum):
    NONE = 0
    GOLD_ZERO_UP = 1    #0轴上金叉
    GOLD_ZERO_DOWN = 2  #0轴下金叉
    DEAD_ZERO_UP = 3    #0轴上死叉
    DEAD_ZERO_DOWN = 4  #0轴下死叉
    TOP_DIVERGENCE = 5  #顶背离
    BOTTOM_DIVERGENCE = 6  #底背离
    #判断是否金叉
    def is_golden(self) -> bool:
        return self == MACD_CROSS.GOLD_ZERO_UP or self == MACD_CROSS.GOLD_ZERO_DOWN
    #判断是否死叉
    def is_dead(self) -> bool:
        return self == MACD_CROSS.DEAD_ZERO_DOWN or self == MACD_CROSS.DEAD_ZERO_UP
    #判断两个交叉是否相反
    def is_opposite(self, other : MACD_CROSS) -> bool:
        opposite = False
        if self.is_golden() :
            opposite = other.is_dead()
        else :
            assert(self.is_dead())
            opposite = other.is_golden()
        return opposite
  
DEFAULT_FEE = 0.001         #默认手续费
DEF_MIN_AMOUNT = 0.0001     #最小交易数量，如<1，则每次递减1位小数

# 持仓数据类
class holding() :
    def __init__(self, symbol : trade_symbol, free : float, lock : float, cost : float) :
        self.__symbol = symbol
        self.__free = free          #可用数量
        self.__lock = lock          #锁定数量
        self.__cost = cost            #持仓成本
        self.__day = ''               #持仓日期，如几次追加则记录最早的持仓日期
        return
    def __str__(self) -> str:
        return 'symbol={}, free={}, lock={}, cost={}'.format(self.__symbol, self.__free, self.__lock, self.__cost)     
    @property
    def symbol(self) -> trade_symbol:
        return self.__symbol
    @property
    def amount(self) -> float:
        return round(self.__free, 4)
    
    #计算一次买入成本
    def calc_cost(price : float, amount : float, fee : float) -> float:
        return round(price * amount * (1 + fee), 2)
    #计算一次卖出收入
    def calc_income(price : float, amount : float, fee : float) -> float:
        return round(price * amount * (1 - fee), 2)
    #计算持仓价值
    def hold_asset(self, price : float) -> float:
        return round(self.__free * price, 2)
    #买入
    def _buy(self, amount : float, cost : float, day : str) :
        assert(amount > 0 and cost > 0)
        if self.__free == 0 :    #首次买入
            assert(self.__day == '')
            self.__day = day
        self.__free += amount
        if self.__free > 0 :
            self.__cost = (self.__cost * self.__free + cost) / self.__free
        return
    #卖出
    def _sell(self, amount : float, cost : float) :
        assert(amount > 0 and cost > 0)
        assert(self.__free >= amount)
        self.__free -= amount
        #计算股票卖出后的成本价格
        if self.__free > 0 :
            self.__cost = (self.__cost * self.__free + cost) / self.__free
        if self.__free == 0 :
            self.__day = ''
        return
    #计算持仓天数
    def hold_days(self, day : str) -> int:
        if self.__free == 0:
            return 0
        assert(self.__day != '' and day != '')
        #计算两个YYYY-MM-DD日期之间的天数
        d1 = datetime.strptime(self.__day, "%Y-%m-%d")
        d2 = datetime.strptime(day, "%Y-%m-%d")
        delta = d2 - d1
        return delta.days   

#分境维度的账户类
class part_account() :
    def __init__(self, part_id : str, part_name : str) :
        self.__part_id = part_id
        self.__part_name = part_name
        self.__cash = float(0)         #该分境的现金
        self.__holdings = dict[str, holding]()      #该分境的持仓数据
        self.__lock = Lock()
        return
 
    def __deepcopy__(self, memo):
        new_obj = type(self)(self.__part_id, self.__part_name)
        memo[id(self)] = new_obj
        #new_obj.__part_id = self.__part_id
        #new_obj.__part_name = self.__part_name
        new_obj.__cash = self.__cash
        new_obj.__holdings = copy.deepcopy(self.__holdings, memo)
        #new_obj.__lock = Lock()
        return new_obj

    @property
    def part_id(self) -> str:
        return self.__part_id
    @property
    def part_name(self) -> str:
        return self.__part_name
    @property
    def cash(self) -> float:
        return round(self.__cash, 2)
    #获取特定的持仓
    def get_holding(self, symbol : trade_symbol) -> holding:
        if symbol in self.__holdings :
            return self.__holdings[symbol]
        return None  
    def init_holding(self, symbol : trade_symbol, free : float, locked : float, cost : float, day : str) :
        hold = self.get_holding(symbol)
        if hold is None :
            hold = holding(symbol, free, locked, cost)
            self.__holdings[symbol] = hold
        else :
            assert(False)
            pass
        return
    def get_amount(self, symbol : trade_symbol) -> float:
        hold = self.get_holding(symbol)
        if hold is None :
            return 0
        return hold.amount
    #充值
    def deposit(self, cash : float) :
        self.__cash = round(self.__cash + cash, 2)
        return
    #提现
    def withdraw(self, cash : float) -> bool :
        if cash > self.__cash:
            return False
        self.__cash = round(self.__cash - cash, 2)
        return True
    #计算该分境的总资产（资金+持仓）
    def total_asset(self, current_prices : dict) -> float :
        total_value = self.__cash
        for symbol in self.__holdings :
            total_value += self.__holdings[symbol].hold_asset(current_prices[symbol])
        return round(total_value, 2)
    #买入
    #需要处理手续费和现金扣除
    def _buy(self, symbol : trade_symbol, amount : float, price : float, day : str, fee : float) :
        if day == '' :
            day = datetime.now().strftime("%Y-%m-%d")
        hold = self.get_holding(symbol)
        if hold is None :
            hold = holding(symbol, 0, 0, 0)
            self.__holdings[symbol] = hold

        cur_cost = holding.calc_cost(price, amount, fee)
        with self.__lock :
            hold._buy(amount, cur_cost, day)
            self.__cash = round(self.__cash - cur_cost, 2)
        return
    #买入
    def buy(self, symbol : trade_symbol, amount : float, price : float, day = '', fee = DEFAULT_FEE) -> bool :
        if holding.calc_cost(price, amount, fee) > self.__cash:
            return False
        self._buy(symbol, amount, price, day, fee)
        return True
    #计算最大可买数量
    def calc_max(self, price : float, min_amount = DEF_MIN_AMOUNT, fee = DEFAULT_FEE) -> float :
        amount = 0
        if min_amount >= 1 :        #最小交易数量大于1
            amount = math.floor(self.__cash / price * (1 - fee) * min_amount) / min_amount
        else :
            amount = math.floor(self.__cash / price * (1 - fee) / min_amount) * min_amount
        #验证交易数量和价格是否低于现金，包括手续费
        assert(holding.calc_cost(price, amount, fee) <= self.__cash)
        if amount > 0 :
            assert(amount >= min_amount)
            pass
        return amount    
    #满仓买入
    def buy_max(self, symbol : trade_symbol, price : float, day = '', min_amount = DEF_MIN_AMOUNT, fee = DEFAULT_FEE) -> float:
        amount = self.calc_max(price, min_amount, fee)
        if amount > 0 :
            self.buy(symbol, amount, price, day, fee)
        return amount
    #卖出
    def _sell(self, symbol : trade_symbol, amount : float, price : float, fee : float) :
        hold = self.get_holding(symbol)
        if hold is None :
            return
        cur_cost = holding.calc_income(price, amount, fee)
        with self.__lock :
            hold._sell(amount, cur_cost)
            self.__cash = round(self.__cash + cur_cost, 2)
        return
    #卖出
    def sell(self, symbol : trade_symbol, amount : float, price : float, fee = DEFAULT_FEE) -> bool :
        hold = self.get_holding(symbol)
        if hold is None :
            return False
        if amount > hold.amount or amount == 0:
            return False
        self._sell(symbol, amount, price, fee)
        return True   
    # 清仓卖出
    def sell_all(self, symbol : trade_symbol, price : float, fee = DEFAULT_FEE) -> bool :
        hold = self.get_holding(symbol)
        if hold is None :
            return False
        if hold.amount == 0:
            return False
        self._sell(symbol, hold.amount, price, fee)
        return

#全局维度的账户类
class global_account() :
    def __init__(self, account_id : str, account_name : str) :
        self.__account_id = account_id
        self.__account_name = account_name
        self.__part_accounts = dict[str, part_account]()      #分境账户列表
        return
    @property
    def id(self) -> str:
        return self.__account_id
    @property
    def name(self) -> str:
        return self.__account_name