import sys
import logging
from datetime import datetime

import pandas as pd
import numpy as np

from utils import utility
from utils import log_adapter

import base_item
import data_loader
import fin_util

class MACD_processor():
    WINDOW_LENGTH = 30
    SLOW_PERIOD = 26
    FAST_PERIOD = 12
    SIGNAL_PERIOD = 9
    CN_HOLD = 'hold'
    CN_PROFIT = 'profit'
    def __init__(self, symbol : base_item.trade_symbol) -> None:
        self.__account = None
        self.__klines = pd.DataFrame(columns=['date_b', 'open', 'high', 'low', 'close', 
            'volume', 'date_e', 'amount', 'count', 'buy_amount', 'buy_money', 'ignore'])
        self.__symbol = symbol
        self.DAILY_LOG = False
        self.dailies = None
        return
    @property
    def symbol(self) -> base_item.trade_symbol:
        return self.__symbol
    @property
    def account(self) -> base_item.part_account:
        return self.__account
    def set_account(self, account : base_item.part_account):
        self.__account = account
    def open_daily_log(self, LOG : bool):
        self.DAILY_LOG = LOG
        if self.DAILY_LOG :
            self.dailies = pd.DataFrame(columns=[MACD_processor.CN_HOLD, MACD_processor.CN_PROFIT])
        else :
            self.dailies = None
        return
    #更新一条K线数据
    def update_kline(self, kline : list) -> int:
        begin_len = len(self.__klines)
        if begin_len > 0 :
            print('添加前K线, first index={}, last index={}...'.format(self.__klines.index[0], self.__klines.index[-1]))
        print('{}'.format(self.__klines))
        if begin_len == 0 :
            index = 0
        else :
            index = self.__klines.index[-1] + 1
        #self.__klines.loc[len(self.__klines)] = data_loader.get_kline_shape(kline)
        self.__klines.loc[index] = data_loader.get_kline_shape(kline)
        print('添加后K线...')
        print('{}'.format(self.__klines))
        print('添加前K线数量={}，添加后K线数量={}'.format(begin_len, len(self.__klines)))

        #保留最近的WINDOW_LENGTH条K线数据
        if len(self.__klines) > self.WINDOW_LENGTH :
            #self.__klines = self.__klines.iloc[-self.WINDOW_LENGTH:]
            #删除第一条K线
            self.__klines = self.__klines.drop(self.__klines.index[0])
            print('重要：弹出失效K线，剩余数量={}'.format(len(self.__klines)))
        #取得第一条K线的日期
        #first_date = int(self.__klines.loc[self.__klines.index[0], 'date_b'])
        first_date = int(self.__klines.iloc[0, 0])
        last_date = int(self.__klines.iloc[-1, 0])
        date_first = utility.timestamp_to_string(first_date, ONLY_DATE=True)
        date_last = utility.timestamp_to_string(last_date, ONLY_DATE=True)
        print('重要：窗口={}, 第一条K线={}，最后一条K线={}.'.format(len(self.__klines), date_first, date_last))
        return self.__process()    
    #挂出买单，返回挂单ID
    def __post_buying(self, amount : float, price : float) -> str:
        order_id = ''
        self.__buyed_action(order_id, amount, price)
        return order_id
    #挂出卖单，返回挂单ID
    def __post_selling(self, amount : float, price : float) -> str:
        order_id = ''
        self.__selled_action(order_id, amount, price)
        return order_id
    #收到服务端的买入成功通知
    #order_id: 挂单ID. 可能为成功部分
    def __buyed_action(self, order_id : str, amount : float, price : float):
        self.__account.buy(self.symbol, amount, price)
        return
    #收到服务端的卖出成功通知
    def __selled_action(self, order_id : str, amount : float, price : float):
        self.__account.sell(self.symbol, amount, price)
        return
    def sell_all(self, price : float) -> str:
        order_id = ''
        amount = self.account.get_amount(self.symbol)
        if amount > 0:
            order_id = self.__post_selling(amount, price)
        return order_id
    #处理MACD交叉
    #index: 交叉发生的K线索引
    def __process_cross(self, cross : base_item.MACD_CROSS, index : int) -> int:
        result = 0
        if cross == base_item.MACD_CROSS.GOLD_ZERO_UP or cross == base_item.MACD_CROSS.GOLD_ZERO_DOWN : #金叉
            if self.account.get_amount(self.symbol) == 0:
                buy_price = self.__klines['close', index]
                amount = self.account.calc_max(buy_price)
                date_str = datetime.strptime(self.__klines['date', index], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
                print('重要：日期={}，出现金叉，可用资金={}, 币价={}, 可买数量={}'.format(date_str, self.account.cash, 
                    buy_price, amount))
                if amount > 0 :
                    self.__post_buying(amount, buy_price)
                    print('重要：日期={}, 金叉买入操作完成，当前资金={}, 当前币数={}。'.format(date_str, self.account.cash, 
                        self.__account.get_amount(self.symbol)))
                    result = 1
            else :
                print('异常：日期={}, 金叉买入信号，已为持仓状态(资金={}，持币={})，放弃该金叉。'.format(date_str, 
                    self.account.cash, self.account.get_amount(self.symbol)))
                result = -1
        elif cross == base_item.MACD_CROSS.DEAD_ZERO_UP or cross == base_item.MACD_CROSS.DEAD_ZERO_DOWN : #死叉
            amount = self.account.get_amount(self.symbol)
            if amount > 0:
                sell_price = self.__klines['close', index]
                print('重要：日期={}，出现死叉，卖出操作，价格={}, 数量={}...'.format(date_str, sell_price, self.account.get_amount(self.symbol)))
                self.__post_selling(amount, sell_price)
                print('重要：日期={}, 死叉卖出操作完成，当前资金={}, 当前币数={}。'.format(date_str, self.account.cash, 
                    self.account.get_amount(self.symbol)))
                result = 2
            else :
                print('异常：日期={}, 死叉卖出信号，无持仓状态(资金={}，持币={})，放弃该死叉。'.format(date_str, self.account.cash, 
                    amount))
                result = -2
        return result

    def __process(self) -> int:
        result = 0
        #获取收盘价列表
        assert(len(self.__klines) > 0)
        #获取最后一条K线的收盘价
        #close = self.__klines.loc[len(self.__klines)-1, 'close']  #最后一条K线的收盘价
        closes = self.__klines['close'].tolist()
        #print('closes={}'.format(closes))
        pi = fin_util.prices_info(closes)
        #计算MACD
        macd, signal, hist = pi.calculate_macd()
        crossovers = fin_util.find_macd_crossovers(macd, signal, hist)
        if len(crossovers) > 0 :
            index = crossovers[-1][0]
            cross = crossovers[-1][1]
            if index == len(closes) - 1 :        #最新的K线上有交叉
                result = self.__process_cross(cross, cross[0])
        if self.DAILY_LOG :
            assert(self.dailies is not None)
            prices = {base_item.trade_symbol.BTCUSDT: closes[-1], }
            self.dailies.loc[len(self.dailies)] = [self.account.get_amount(self.symbol), self.account.total_asset(prices)]
        return result
    
def calc_profit(year_begin : int, year_end : int) :
    INIT_CASH = 10000
    account = base_item.part_account('13', 'thiefox')
    account.deposit(INIT_CASH)
    symbol = base_item.trade_symbol('BTCUSDT')
    processor = MACD_processor(symbol)
    processor.set_account(account)
    processor.open_daily_log(True)
    interval = base_item.kline_interval.d1
    klines = data_loader.load_klines_years(processor.symbol, year_begin, year_end, interval)
    print('共载入的K线数据记录={}'.format(len(klines)))
    if len(klines) == 0:
        return 
    dates = [utility.timestamp_to_string(kline[0]) for kline in klines]
    #把dates转换为numpy数组
    dates = np.array(dates)
    
    gold_cross = list()
    dead_cross = list()
    for i in range(len(klines)):
        print('处理第{}条K线数据，日期={}...'.format(i, dates[i]))
        if i > 50 :
            break
        kline = klines[i]
        #print(kline)
        result = processor.update_kline(kline)
        if result == 1:
            print('重要：日期={}，第{}条K线发现金叉。'.format(dates[i], i))
            gold_cross.append(i)
        elif result == 2:
            print('重要：日期={}，第{}条K线发现死叉。'.format(dates[i], i))
            dead_cross.append(i)
        elif result == 0 :
            pass
        elif result == -1 :
            print('异常：日期={}，第{}条K线金叉信号，已为持仓状态，放弃该金叉。'.format(dates[i], i))
        elif result == -2 :
            print('异常：日期={}，第{}条K线死叉信号，无持仓状态，放弃该死叉。'.format(dates[i], i))
        else :
            assert(False)
            pass

    last_price = klines[-1][4]
    processor.sell_all(last_price)
    print('MACD模式最终总值={}, 收益率={:.2f}%'.format(account.cash, fin_util.calc_scale(INIT_CASH, account.cash)))

    print('金叉次数={}, 死叉次数={}'.format(len(gold_cross), len(dead_cross)))
    for gc in gold_cross :
        print('金叉={}， 日期={}'.format(gc, dates[gc]))
    for dc in dead_cross :
        print('死叉={}， 日期={}'.format(dc, dates[dc]))

    if processor.dailies is not None :
        profits = processor.dailies[MACD_processor.CN_PROFIT].tolist()
        pf = fin_util.prices_info(profits)
        info = pf.find_max_trend(INCREMENT=False)
        if info[0] > 0:
            begin_str = datetime.strptime(dates[info[1]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            end_str = datetime.strptime(dates[info[2]-1], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            print('MACD最大连续回撤={:.2f}%, bi={}, ei={}'.format(info[0]*100, begin_str, end_str))
            before = profits[info[1]-1]
            after = profits[info[2]]
            print('MACD模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
            if not pf.check_order(info[1], info[2], ASCENDING=False):
                print('异常：最大连续回撤区间不是降序排列！')
                #pf.print(info[1], info[2])

        holds = processor.dailies[MACD_processor.CN_HOLD].tolist()
        info = fin_util.calc_hold_days(holds)
        print('MACD模式-总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    return    

def _test() :
    print("MACD process Start...")
    LOG_FLAG = 1
    if LOG_FLAG == 1:
        str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        #logging.basicConfig(level=logging.INFO, format=format, filename='log/{}_{}_{}H-{}.txt'.format(symbol, year, interval, str_now))
        logging.basicConfig(level=logging.INFO, format=format, filename='log/MACD_process-{}.txt'.format(str_now))
        logger = logging.getLogger('binance')
        logger.setLevel(logging.INFO)
        #把print输出到日志文件
        tmp_out = sys.stdout
        tmp_err = sys.stderr

        sys.stdout = log_adapter.LoggerWriter(logger, logging.INFO)
        sys.stderr = log_adapter.LoggerWriter(logger, logging.ERROR)
    
    #calc_MACD_daily_profit(2017, 2025, kline_interval.d1)
    #draw_klines(2023, 2024, kline_interval.d1)
    calc_profit(2017, 2025)

    if LOG_FLAG == 1:
        sys.stdout = tmp_out
        sys.stderr = tmp_err
    print("MACD process End.")    
    return

_test()