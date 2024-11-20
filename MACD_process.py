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
import draw_profit
import kline_spider
class MACD_processor():
    #WINDOW_LENGTH=0表示不限制K线数量
    #114天结果和无限一样，114为最小临界窗口
    WINDOW_LENGTH = 120
    SLOW_PERIOD = 26
    FAST_PERIOD = 12
    SIGNAL_PERIOD = 9
    def __init__(self, symbol : base_item.trade_symbol) -> None:
        self.__account = None
        self.__klines = pd.DataFrame(columns=['date_b', 'open', 'high', 'low', 'close', 
            'volume', 'date_e', 'amount', 'count', 'buy_amount', 'buy_money', 'ignore'])
        self.__symbol = symbol
        self.DAILY_LOG = False
        self.dailies = pd.DataFrame(columns=['date', 'cash', 'hold', 'profit'])
        self.crosses = list()
        return
    @property
    def symbol(self) -> base_item.trade_symbol:
        return self.__symbol
    @property
    def account(self) -> base_item.part_account:
        return self.__account
    def set_account(self, account : base_item.part_account):
        self.__account = account
        return
    def open_daily_log(self, LOG : bool):
        self.DAILY_LOG = LOG
        return
    #更新一条K线数据
    def update_kline(self, kline : list) -> tuple[base_item.MACD_CROSS, base_item.TRADE_STATUS]:
        begin_len = len(self.__klines)
        '''
        if begin_len > 0 :
            print('添加前K线, first index={}, last index={}...'.format(self.__klines.index[0], self.__klines.index[-1]))
        print('{}'.format(self.__klines))
        '''
        if begin_len == 0 :
            index = 0
        else :
            index = self.__klines.index[-1] + 1
        #self.__klines.loc[len(self.__klines)] = data_loader.get_kline_shape(kline)
        self.__klines.loc[index] = data_loader.get_kline_shape(kline)
        
        #保留最近的WINDOW_LENGTH条K线数据
        if self.WINDOW_LENGTH > 0 and len(self.__klines) > self.WINDOW_LENGTH :
            #self.__klines = self.__klines.iloc[-self.WINDOW_LENGTH:]
            #删除第一条K线
            self.__klines = self.__klines.drop(self.__klines.index[0])
            #print('重要：弹出失效K线，剩余数量={}'.format(len(self.__klines)))
        #取得第一条K线的日期
        #first_date = int(self.__klines.loc[self.__klines.index[0], 'date_b'])
        first_date = int(self.__klines.iloc[0, 0])
        last_date = int(self.__klines.iloc[-1, 0])
        date_first = utility.timestamp_to_string(first_date, ONLY_DATE=True)
        date_last = utility.timestamp_to_string(last_date, ONLY_DATE=True)
        #print('重要：窗口={}, 第一条K线={}，最后一条K线={}.'.format(len(self.__klines), date_first, date_last))
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
    def __process_cross(self, cross : base_item.MACD_CROSS, index : int) -> base_item.TRADE_STATUS:
        #print('打印K线数据...{}'.format(self.__klines))
        index = self.__klines.index[index]
        #print('内部索引={}, 外部索引={}, 交叉={}'.format(ni, index, cross))
        status = base_item.TRADE_STATUS.IGNORE
        #date_str = utility.timestamp_to_string(self.__klines[index, 'date_b'], ONLY_DATE=True)
        date_str = utility.timestamp_to_string(int(self.__klines.loc[index, 'date_b']), ONLY_DATE=True)
        if cross == base_item.MACD_CROSS.GOLD_ZERO_UP or cross == base_item.MACD_CROSS.GOLD_ZERO_DOWN : #金叉
            if self.account.get_amount(self.symbol) == 0:
                buy_price = self.__klines.loc[index, 'close']
                amount = self.account.calc_max(buy_price)

                print('重要：日期={}，出现金叉，可用资金={}, 币价={}, 可买数量={}'.format(date_str, self.account.cash, 
                    buy_price, amount))
                if amount > 0 :
                    self.__post_buying(amount, buy_price)
                    print('重要：日期={}, 金叉买入操作完成，当前资金={}, 当前币数={}。'.format(date_str, self.account.cash, 
                        self.__account.get_amount(self.symbol)))
                    status = base_item.TRADE_STATUS.BUY
            else :
                print('异常：日期={}, 金叉买入信号，已为持仓状态(资金={}，持币={})，放弃该金叉。'.format(date_str, 
                    self.account.cash, self.account.get_amount(self.symbol)))
        elif cross == base_item.MACD_CROSS.DEAD_ZERO_UP or cross == base_item.MACD_CROSS.DEAD_ZERO_DOWN : #死叉
            amount = self.account.get_amount(self.symbol)
            if amount > 0:
                sell_price = self.__klines.loc[index, 'close']
                print('重要：日期={}，出现死叉，卖出操作，价格={}, 数量={}...'.format(date_str, sell_price, self.account.get_amount(self.symbol)))
                self.__post_selling(amount, sell_price)
                print('重要：日期={}, 死叉卖出操作完成，当前资金={}, 当前币数={}。'.format(date_str, self.account.cash, 
                    self.account.get_amount(self.symbol)))
                status = base_item.TRADE_STATUS.SELL
            else :
                print('异常：日期={}, 死叉卖出信号，无持仓状态(资金={}，持币={})，放弃该死叉。'.format(date_str, self.account.cash, 
                    amount))
        return status

    def __process(self) -> tuple[base_item.MACD_CROSS, base_item.TRADE_STATUS]:
        cross = base_item.MACD_CROSS.NONE
        status = base_item.TRADE_STATUS.IGNORE
        #获取收盘价列表
        assert(len(self.__klines) > 0)
        #获取最后一条K线的收盘价
        #close = self.__klines.loc[len(self.__klines)-1, 'close']  #最后一条K线的收盘价
        closes = self.__klines['close'].tolist()
        dates = self.__klines['date_b'].tolist()
        dates = [utility.timestamp_to_string(int(i), ONLY_DATE=True) for i in dates]
        #print('closes={}'.format(closes))
        if len(closes) > 0 :
            assert(isinstance(closes[0], float))
        pi = fin_util.prices_info(closes)
        #计算MACD
        macd, signal, hist = pi.calculate_macd()
        crossovers = fin_util.find_macd_crossovers(macd, signal, hist)
        #print('共找到{}个MACD交叉点...'.format(len(crossovers)))
        if len(crossovers) > 0 :
            index = crossovers[-1][0]
            cross = crossovers[-1][1]
            oi = self.__klines.index[index]
            if len(self.crosses) == 0 :
                self.crosses.append((oi, cross))
            else :
                last_oi = self.crosses[-1][0]
                last_cross = self.crosses[-1][1]
                if oi > last_oi :
                    if cross.is_opposite(last_cross) :  #交叉点相反
                        self.crosses.append((oi, cross))
                    else :
                        print('异常：交叉点=({},{})和最后一个交叉点=({},{})相同类型.'.format(oi, cross, last_oi, last_cross))
                elif oi == last_oi :
                    pass
                else :
                    print('异常：交叉点=({},{})不是最新位置，最后一个有效交叉=({},{}).'.format(oi, cross, last_oi, last_cross))
            if index == len(closes) - 1 :        #最新的K线上有交叉
                status = self.__process_cross(cross, index)
                print('重要：出现新的MACD交叉点={}, 日期={}, index={}, 处理={}.'.format(cross, dates[index], index, status))
            else :
                #assert(False)
                cross = base_item.MACD_CROSS.NONE
                pass
        if self.DAILY_LOG :
            #如当天发现交叉，则cash和hold为处理交叉后的数据
            #prices = {base_item.trade_symbol.BTCUSDT: closes[-1], }
            profit = self.account.cash + self.account.get_amount(self.symbol) * closes[-1]
            self.dailies.loc[len(self.dailies)] = [dates[-1], self.account.cash, self.account.get_amount(self.symbol), profit]
        return cross, status
    
    def print_cross(self):
        #获取self.crosses中的金叉列表和死叉列表
        gold_cross = dict()
        dead_cross = dict()
        for cross in self.crosses:
            index = cross[0]
            cross_type = cross[1]
            if cross_type.is_golden():
                gold_cross[index] = cross_type
            elif cross_type.is_dead():
                dead_cross[index] = cross_type

        print('所有金叉数量={}'.format(len(gold_cross)))
        if len(gold_cross) > 0 :
            print('金叉点列表={}'.format(', '.join([str(x) for x in gold_cross.keys()])))
        print('所有死叉数量={}'.format(len(dead_cross)))
        if len(dead_cross) > 0 :
            print('死叉点列表={}'.format(', '.join([str(x) for x in dead_cross.keys()])))
        return
    
def calc_profit(year_begin : int, year_end : int, interval : base_item.kline_interval) -> list:
    INIT_CASH = 10000
    account = base_item.part_account('13', 'thiefox')
    account.deposit(INIT_CASH)
    symbol = base_item.trade_symbol.BTCUSDT
    processor = MACD_processor(symbol)
    processor.set_account(account)
    processor.open_daily_log(True)
    klines = data_loader.load_klines_years(processor.symbol, year_begin, year_end, interval)
    print('共载入的K线数据记录={}'.format(len(klines)))
    if len(klines) == 0:
        return list()
    dates = [utility.timestamp_to_string(kline[0], ONLY_DATE=True) for kline in klines]
    #把dates转换为numpy数组
    dates = np.array(dates)
    
    gold_cross = list()
    dead_cross = list()
    operations = list()     #操作记录
    INIT_PRICE = round(float(klines[0][1]), 2)  #以开盘价作为初始价格
    for i in range(len(klines)):
        #print('处理第{}条K线数据，日期={}...'.format(i, dates[i]))
        kline = klines[i]
        result = processor.update_kline(kline)
        if result[0].is_golden() :
            #print('重要：日期={}，第{}条K线发现金叉。'.format(dates[i], i))
            gold_cross.append(i)
            operations.append((i, result[0], result[1]))
        elif result[0].is_dead():
            #print('重要：日期={}，第{}条K线发现死叉。'.format(dates[i], i))
            dead_cross.append(i)
            operations.append((i, result[0], result[1]))
        else :
            pass

    last_price = float(klines[-1][4])
    amount = processor.account.get_amount(symbol)
    if amount > 0 :
        print('重要：最后一天卖出操作，日期={}, 价格={}, 数量={:.4f}...'.format(dates[-1], last_price, amount))
        processor.sell_all(last_price)
        operations.append((len(klines)-1), base_item.MACD_CROSS.NONE, base_item.TRADE_STATUS.SELL)

    print('起始资金={}, 起始币数量={}, 起始币价格={:.2f}, 结束币价格={:.2f}'.format(INIT_CASH, 0, INIT_PRICE, last_price))
    print('重要：MACD模式最终资金={}, 盈亏={}，收益率={:.2f}%'.format(account.cash, account.cash - INIT_CASH,
        fin_util.calc_scale(INIT_CASH, account.cash)*100))
    print('---processor处理器打印金叉死叉---...')
    processor.print_cross()
    print('---外部环境打印金叉死叉---...')
    print('金叉出现次数={}, 金叉列表={}.'.format(len(gold_cross), ', '.join([str(x) for x in gold_cross])))
    print('死叉出现次数={}, 死叉列表={}.'.format(len(dead_cross), ', '.join([str(x) for x in dead_cross])))
    print('开始打印买卖操作...')
    for op in operations:
        #date_str = datetime.strptime(dates[op[0]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        date_str = dates[op[0]]
        daily = processor.dailies.loc[op[0]]
        price = float(klines[op[0]][4])
        if op[1].is_golden():
            if op[2] == base_item.TRADE_STATUS.BUY:
                print('重要：金叉买入，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            elif op[2] == base_item.TRADE_STATUS.IGNORE:
                print('异常：金叉忽略，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                print('异常：金叉操作错误，i={}，日期={}, 操作={}'.format(op[0], date_str, op[2]))
                #assert(False)
                pass
        elif op[1].is_dead() :
            if op[2] == base_item.TRADE_STATUS.SELL:
                print('重要：死叉卖出，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            elif op[2] == base_item.TRADE_STATUS.IGNORE:
                print('异常：死叉忽略，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                print('异常：死叉操作错误，i={}，日期={}, 操作={}'.format(op[0], date_str, op[2]))
                #assert(False)
                pass
        else :
            if op[2] == base_item.TRADE_STATUS.SELL:
                print('重要：最后一天卖出，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                assert(False)
    print('打印买卖操作结束.')

    profits = list()
    if len(processor.dailies) > 0 :
        profits = processor.dailies['profit'].tolist()
        pf = fin_util.prices_info(profits)
        info = pf.find_max_trend(INCREMENT=False)
        print('统计最大连续回撤返回={:.2f}%, bi={}, ei={}'.format(info[0]*100, info[1], info[2]-1))
        if info[1] >= 0 and info[2] > info[1]:
            begin_str = dates[info[1]]
            end_str = dates[info[2]-1]
            print('MACD最大连续回撤={:.2f}%, bi={}, ei={}'.format(info[0]*100, begin_str, end_str))
            before = round(profits[info[1]-1], 2)
            after = round(profits[info[2]], 2)
            print('MACD模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
            if not pf.check_order(info[1], info[2], ASCENDING=False):
                print('异常：最大连续回撤区间不是降序排列！')
                #pf.print(info[1], info[2])
        else :
            print('异常：未取到最大回撤，统计周期={}。'.format(len(profits)))

        holds = processor.dailies['hold'].tolist()
        info = fin_util.calc_hold_days(holds)
        print('MACD模式-总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    return profits

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
    
    #calc_profit(2017, 2025, base_item.kline_interval.d1)
    draw_profit.draw_kline_and_profit(2017, 2025, base_item.kline_interval.d1, calc_profit)

    if LOG_FLAG == 1:
        sys.stdout = tmp_out
        sys.stderr = tmp_err
    print("MACD process End.")    
    return

def processor() -> int:
    interval = base_item.kline_interval.h1
    BEGIN_YEAR = 2017
    CUR_YEAR = datetime.now().year
    CUR_MONTH = datetime.now().month
    CUR_DAY = datetime.now().day
    all_klines = list()
    for i in range(BEGIN_YEAR, CUR_YEAR+1):
        YEAR_DAYS = utility.days_in_year(i)
        year_klines = data_loader.load_klines_1Y(base_item.trade_symbol.BTCUSDT, i, interval)
        if len(year_klines) > 0:
            last_begin = utility.timestamp_to_datetime(year_klines[-1][0])
            last_end = utility.timestamp_to_datetime(year_klines[-1][6])
            print('重要：{}年K线数据共{}条，最后一条开始时间={}，结束时间={}。'.format(i, len(year_klines), 
                last_begin.strftime('%Y-%m-%d %H:%M:%S'), last_end.strftime('%Y-%m-%d %H:%M:%S')))
            dates = [kline[0] for kline in year_klines]
            if i < CUR_YEAR :
                if fin_util.check_time_continuity(dates, base_item.kline_interval.d1) and last_begin.strftime('%m%d') == '1231':
                    print('重要：历史年{}K线数据时间连续。'.format(i))
                    all_klines.extend(year_klines)
                else :
                    print('异常：历史年{}K线数据时间不连续1。'.format(i))
                    return -1
                if len(all_klines) > 0 and len(year_klines) < YEAR_DAYS:
                    print('异常：中间历史年{}K线数据不全，应有{}条，实际{}条。'.format(i, YEAR_DAYS, len(year_klines)))
                    return -1
            else :
                if fin_util.check_time_continuity(dates, base_item.kline_interval.d1):
                    print('重要：当前年{}K线数据时间连续。'.format(i))
                    all_klines.extend(year_klines)
                else :
                    print('异常：当前年{}K线数据时间不连续。'.format(i))
                    return -1
        else :
            print('异常：{}年K线数据为空。'.format(i))



    #current_date_int = int(datetime.now().strftime('%Y%m%d'))
    #print("当前日期的年月日整数形式: {current_date_int}")

    return 0

processor()
#_test()