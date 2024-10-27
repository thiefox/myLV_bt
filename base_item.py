from __future__ import annotations
from enum import Enum
from typing import Dict

import math
from datetime import datetime

# K线周期枚举
class kline_interval(str, Enum):
    h1 = '1h'
    h4 = '4h'
    h6 = '6h'
    h12 = '12h'
    d1 = '1d'

class trade_symbol(str, Enum):
    BTCUSDT = 'BTCUSDT'
    ETHUSDT = 'ETHUSDT'

class TRADE_STATUS(Enum):
    IGNORE = 0
    BUY = 1
    SELL = 2

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
    def __init__(self, symbol : trade_symbol, amount : float, cost : float) :
        self.__symbol = symbol
        self.__amount = amount        #持仓数量
        self.__cost = cost            #持仓成本
        self.__day = ''               #持仓日期，如几次追加则记录最早的持仓日期
        return
    def __str__(self) -> str:
        return 'symbol={}, amount={}, cost={}'.format(self.__symbol, self.__amount, self.__cost)     
    @property
    def symbol(self) -> trade_symbol:
        return self.__symbol
    @property
    def amount(self) -> float:
        return round(self.__amount, 4)
    
    #计算一次买入成本
    def calc_cost(price : float, amount : float, fee : float) -> float:
        return round(price * amount * (1 + fee), 2)
    #计算一次卖出收入
    def calc_income(price : float, amount : float, fee : float) -> float:
        return round(price * amount * (1 - fee), 2)
    #计算持仓价值
    def hold_asset(self, price : float) -> float:
        return round(self.__amount * price, 2)
    #买入
    def _buy(self, amount : float, cost : float, day : str) :
        assert(amount > 0 and cost > 0)
        if self.__amount == 0 :    #首次买入
            assert(self.__day == '')
            self.__day = day
        self.__amount += amount
        if self.__amount > 0 :
            self.__cost = (self.__cost * self.__amount + cost) / self.__amount
        return
    #卖出
    def _sell(self, amount : float, cost : float) :
        assert(amount > 0 and cost > 0)
        assert(self.__amount >= amount)
        self.__amount -= amount
        #计算股票卖出后的成本价格
        if self.__amount > 0 :
            self.__cost = (self.__cost * self.__amount + cost) / self.__amount
        if self.__amount == 0 :
            self.__day = ''
        return
    #计算持仓天数
    def hold_days(self, day : str) -> int:
        if self.__amount == 0:
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
        return
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
            hold = holding(symbol, 0, 0)
            self.__holdings[symbol] = hold

        cur_cost = holding.calc_cost(price, amount, fee)
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