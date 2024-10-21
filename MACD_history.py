import copy
import sys
from datetime import datetime
import logging
import numpy as np

from utils import utility
from utils import log_adapter

from base_item import kline_interval, trade_symbol, MACD_CROSS
import base_item
import data_loader
import fin_util
import draw

#生成MACD模式每日收益曲线
def calc_MACD_daily_profit(year_begin : int, year_end : int, interval : kline_interval) -> list:
    BTCUSDT = trade_symbol.BTCUSDT
    INIT_CASH = 10000
    cash = float(INIT_CASH)     #初始资金
    amount = float(0)       #持有的币数量
    FEE = base_item.DEFAULT_FEE
    MIN_AMOUNT = base_item.DEF_MIN_AMOUNT
    buy_price = 0
    klines = data_loader.load_klines_years(trade_symbol.BTCUSDT, year_begin, year_end, interval)
    print('共载入的K线数据记录={}'.format(len(klines)))
    if len(klines) == 0:
        return list()
    INIT_PRICE = round(float(klines[0][1]), 4)
    print('开始计算MACD模式的每日收益...')
    dates = [utility.timestamp_to_string(kline[0], ONLY_DATE=True) for kline in klines]
    #把dates转换为numpy数组
    dates = np.array(dates)
    closed_prices = [float(kline[4]) for kline in klines]
    pi = fin_util.prices_info(closed_prices)
    macd, signal, hist = pi.calculate_macd()
    assert(isinstance(macd, np.ndarray))
    assert(len(macd) == len(klines))
    crossovers = fin_util.find_macd_crossovers(macd, signal, hist)
    print('共找到{}个MACD交叉点'.format(len(crossovers)))
    accounts = [base_item.part_account('13', 'thiefox')] * len(klines)       #每日的账户信息
    accounts[0].deposit(INIT_CASH)                  #初始资金

    gold_ops = list()       #金叉操作
    dead_ops = list()       #死叉操作
    operations = list()     #操作记录
    for i in range(1, len(klines)):
        accounts[i] = copy.deepcopy(accounts[i-1])  #复制前一天的账户信息
        cur_account = accounts[i]
        #date_str = datetime.strptime(dates[i], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        date_str = dates[i]
        print('处理第{}天={}...'.format(i, date_str))
        if cur_account.get_amount(BTCUSDT) > 0:  #当前为持仓状态
            # 只保留年月日
            hold_days = cur_account.get_holding(BTCUSDT).hold_days(date_str)
            assert(i > hold_days)
            prefit = pi.calc_profit_scale(i-hold_days, i)
            print('持仓天数={}，日期={}，币价={}，持仓收益={:.2f}%'.format(hold_days, date_str, closed_prices[i], prefit*100))
            info = pi.find_prev_peak(i)
            assert(info[1] >= 0)
            print('前一个峰值币价={}，索引={}'.format(info[0], info[1]))
            prefit = pi.calc_profit_scale(info[1], i)
            print('前一个峰值到当前日期的收益={:.2f}%'.format(prefit*100))

        if i in [c[0] for c in crossovers]:
            index = [c[0] for c in crossovers].index(i)
            if crossovers[index][1] == MACD_CROSS.GOLD_ZERO_UP or crossovers[index][1] == MACD_CROSS.GOLD_ZERO_DOWN:  #金叉
                if cur_account.get_amount(BTCUSDT) == 0:
                    buy_price = closed_prices[i]
                    print('重要：日期={}，出现金叉，可用资金={}, 币价={}, 可买数量={}'.format(date_str, cur_account.cash, 
                        buy_price, cur_account.calc_max(buy_price, MIN_AMOUNT, FEE)))
                    amount = cur_account.buy_max(BTCUSDT, buy_price, date_str, MIN_AMOUNT, FEE)
                    assert(amount > 0)
                    print('重要：日期={}, 金叉买入操作完成，当前资金={}, 当前币数={}。'.format(date_str, cur_account.cash, 
                        cur_account.get_amount(BTCUSDT)))
                    gold_ops.append(i)
                    operations.append(i)
                else :
                    print('异常：日期={}, 金叉买入信号，已为持仓状态(资金={}，持币={})，放弃该金叉。'.format(date_str, 
                        cur_account.cash, cur_account.get_amount(BTCUSDT)))
            elif crossovers[index][1] == MACD_CROSS.DEAD_ZERO_UP or crossovers[index][1] == MACD_CROSS.DEAD_ZERO_DOWN:  #死叉
                if cur_account.get_amount(BTCUSDT) > 0:
                    sell_price = closed_prices[i]
                    print('重要：日期={}，出现死叉，卖出操作，价格={}, 数量={}...'.format(date_str, sell_price, cur_account.get_amount(BTCUSDT)))
                    cur_account.sell_all(BTCUSDT, sell_price, FEE)
                    print('重要：日期={}, 死叉卖出操作完成，当前资金={}, 当前币数={}。'.format(date_str, cur_account.cash, 
                        cur_account.get_amount(BTCUSDT)))
                    dead_ops.append(i)
                    operations.append(i)
                else :
                    print('异常：日期={}, 死叉卖出信号，无持仓状态(资金={}，持币={})，放弃该死叉。'.format(date_str, cur_account.cash, 
                        cur_account.get_amount(BTCUSDT)))
        else :
            pass
            
    #最后一天卖出
    if accounts[-1].get_amount(BTCUSDT) > 0:
        sell_price = closed_prices[-1]
        #date_str = datetime.strptime(dates[-1], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        print('重要：最后一天卖出操作，日期={}, 价格={}, 数量={}...'.format(dates[-1], sell_price, accounts[-1].get_amount(BTCUSDT)))
        accounts[-1].sell_all(BTCUSDT, sell_price, FEE)
        operations.append(len(accounts)-1)
        
    print('------------------------------------------------------------')
    assert(accounts[-1].get_amount(BTCUSDT) == 0)
    print('重要：MACD模式最终资金=={}, 最终币数={}。'.format(accounts[-1].cash, accounts[-1].get_amount(BTCUSDT)))

    profits = [0] * len(accounts)
    for i in range(len(accounts)):
        price_dict = {BTCUSDT: closed_prices[i], }
        profits[i] = accounts[i].total_asset(price_dict)

    print('起始资金={}, 起始币数量={}, 起始币价格={}, 结束币价格={}'.format(INIT_CASH, 0, INIT_PRICE, closed_prices[-1]))
    print('MACD模式最终资金={}, 最终收益={}.'.format(accounts[-1].cash, accounts[-1].cash-INIT_CASH))
    
    print('金叉买入次数={}, 金叉买入列表={}.'.format(len(gold_ops), ', '.join([str(x) for x in gold_ops])))
    print('死叉卖出次数={}, 死叉卖出列表={}.'.format(len(dead_ops), ', '.join([str(x) for x in dead_ops])))
    print('开始打印买卖操作...')
    BUY_OP = True
    for index in range(0, len(operations)):
        i = operations[index]
        cur_account = accounts[i]
        #date_str = datetime.strptime(dates[i], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        if BUY_OP:
            print('金叉买入：i={}，日期={}，价格={}，数量={}，剩余资金={}. 总值={}.'.format(i, dates[i], closed_prices[i],
                cur_account.get_amount(BTCUSDT), cur_account.cash, profits[i]))
            BUY_OP = False
        else :
            buy_i = operations[index-1]
            profit = pi.calc_profit_scale(buy_i, i)
            print('死叉卖出：i={}，日期={}，价格={}，数量={}，操作收益={:.2f}%. 剩余资金={}. 总值={}.'.format(i,
                dates[i], closed_prices[i], accounts[i-1].get_amount(BTCUSDT), profit*100, accounts[i].cash, profits[i]))
            BUY_OP = True
    print('打印买卖操作结束.')
    pf = fin_util.prices_info(profits)
    info = pf.find_max_trend(INCREMENT=False)
    if info[0] > 0:
        #begin_str = datetime.strptime(dates[info[1]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        #end_str = datetime.strptime(dates[info[2]-1], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        print('MACD最大连续回撤={:.2f}%, bi={}, ei={}'.format(info[0]*100, dates[info[1]], dates[info[2]-1]))
        before = profits[info[1]-1]
        after = profits[info[2]]
        print('MACD模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
        if not pf.check_order(info[1], info[2], ASCENDING=False):
            print('异常：最大连续回撤区间不是降序排列！')
            #pf.print(info[1], info[2])

    info = fin_util.calc_hold_days([a.get_amount(BTCUSDT) for a in accounts]) 
    print('MACD模式ACCOUNTS计算，总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    print('------------------------------------------------------------')

    #开始计算起始买币，最终卖币收益
    amount = INIT_CASH/INIT_PRICE
    cash = round(amount * closed_prices[-1] * (1 - FEE), 2)
    print('持仓模式最终资金={}, 最终收益={}'.format(cash, cash-INIT_CASH))        
    info = pi.find_max_trend(INCREMENT=False)
    if info[0] > 0:
        #begin_str = datetime.strptime(dates[info[1]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        #end_str = datetime.strptime(dates[info[2]-1], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        print('持仓模式最大连续回撤={:.2f}%, bi={}, ei={}'.format(info[0]*100, dates[info[1]], dates[info[2]-1]))
        before = pi.get(info[1]-1)
        after = pi.get(info[2])
        print('持仓模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
        if not pi.check_order(info[1], info[2], ASCENDING=False):
            print('异常：最大连续回撤区间不是降序排列！')
            #pi.print(info[1], info[2])

    '''
    print('开始打印每日收益...')
    pf.print(DATES=dates)
    print('打印每日收益结束.')
    '''    
    return profits

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
        dates = np.array(dates)
        closed_prices = [float(kline[4]) for kline in klines]
        draw.draw_kline(dates, closed_prices, XUnit=UNIT)
    else:
        print("Failed to fetch kline data.")
    return

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
        dates = np.array(dates)
        closed_prices = [float(kline[4]) for kline in klines]
        profits = calc_MACD_daily_profit(b_year, e_year, interval)
        draw.draw_kline_and_profile(dates, closed_prices, profits, XUnit=UNIT)
    return

def _test() :
    print("MACD history Start...")
    str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 
    format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    #logging.basicConfig(level=logging.INFO, format=format, filename='log/{}_{}_{}H-{}.txt'.format(symbol, year, interval, str_now))
    logging.basicConfig(level=logging.INFO, format=format, filename='log/MACD_history-{}.txt'.format(str_now))
    logger = logging.getLogger('binance')
    logger.setLevel(logging.INFO)
    #把print输出到日志文件
    tmp_out = sys.stdout
    tmp_err = sys.stderr

    #sys.stdout = log_adapter.LoggerWriter(logger, logging.INFO)
    #sys.stderr = log_adapter.LoggerWriter(logger, logging.ERROR)

    #calc_MACD_daily_profit(2017, 2025, kline_interval.d1)
    #draw_klines(2023, 2024, kline_interval.d1)
    draw_kline_and_profit(2017, 2025, kline_interval.d1)

    sys.stdout = tmp_out
    sys.stderr = tmp_err
    print("MACD history End.")    
    return

_test()