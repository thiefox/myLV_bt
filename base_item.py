from enum import Enum

# K线周期枚举
class kline_interval(str, Enum):
    h1 = '1h'
    h4 = '4h'
    h6 = '6h'
    h12 = '12h'
    d1 = '1d'

class trade_symbol(Enum):
    BTCUSDT = 'BTCUSDT'
    ETHUSDT = 'ETHUSDT'

# 持仓数据类
class holding() :
    def __init__(self, symbol : trade_symbol, amount : float, cost : float) :
        self.symbol = symbol
        self.amount = amount        #持仓数量
        self.cost = cost            #持仓成本
        return
    def current_value(self, current_price: float) -> float:
        return self.amount * current_price
    
#分境维度的账户类
class part_account() :
    def __init__(self, part_id : str, part_name : str) :
        self.part_id = part_id
        self.part_name = part_name
        self.cash = float(0)         #该分境的现金
        self.holdings = dict()      #该分境的持仓数据
        return
    #计算该分境的总资产
    def total_value(self, current_prices : dict) -> float :
        total_value = self.cash
        for symbol in self.holdings.keys() :
            total_value += self.holdings[symbol].current_value(current_prices[symbol])
        return total_value
    #买入
    #需要处理手续费和现金扣除
    def _buy(self, symbol : trade_symbol, amount : float, cost : float) :
        if symbol in self.holdings.keys() :
            self.holdings[symbol].amount += amount
            self.holdings[symbol].cost = (self.holdings[symbol].cost * self.holdings[symbol].amount + cost) / self.holdings[symbol].amount
        else :
            self.holdings[symbol] = holding(symbol, amount, cost)
        return


#全局维度的账户类
class global_account() :
    def __init__(self, account_id : str, account_name : str) :
        self.account_id = account_id
        self.account_name = account_name
        self.part_accounts = dict()      #分境账户列表