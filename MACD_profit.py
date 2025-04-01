import logging
import numpy as np
import sys

from com_utils import utility

import base_item
import data_loader
from MACD_process import MACD_processor
import fin_util

def calc_profit(year_begin : int, year_end : int, interval : base_item.kline_interval) -> list:
    INIT_CASH = 10000
    account = base_item.part_account('13', 'thiefox')
    account.deposit(INIT_CASH)
    symbol = base_item.trade_symbol.BTCUSDT
    processor = MACD_processor(symbol)
    processor.set_account(account)
    processor.open_daily_log(True)
    klines = data_loader.load_klines_years(processor.symbol, year_begin, year_end, interval)
    logging.info('共载入的K线数据记录={}'.format(len(klines)))
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
        logging.debug('处理第{}条K线数据，日期={}...'.format(i, dates[i]))
        kline = klines[i]
        result = processor.update_kline(kline)
        if result[0].is_golden() :
            logging.info('日期={}，第{}条K线发现金叉。'.format(dates[i], i))
            gold_cross.append(i)
            operations.append((i, result[0], result[1], result[2]))
        elif result[0].is_dead():
            logging.info('日期={}，第{}条K线发现死叉。'.format(dates[i], i))
            dead_cross.append(i)
            operations.append((i, result[0], result[1], result[2]))
        else :
            pass

    last_price = float(klines[-1][4])
    amount = processor.account.get_amount(symbol)
    if amount > 0 :
        logging.info('最后一天卖出操作，日期={}, 价格={}, 数量={:.4f}...'.format(dates[-1], last_price, amount))
        processor.sell_all(last_price)
        operations.append((len(klines)-1), base_item.MACD_CROSS.NONE, base_item.TRADE_STATUS.SELL)

    logging.info('起始资金={}, 起始币数量={}, 起始币价格={:.2f}, 结束币价格={:.2f}'.format(INIT_CASH, 0, INIT_PRICE, last_price))
    logging.info('MACD最终资金={}, 盈亏={}, 收益率={:.2f}%'.format(account.cash, account.cash - INIT_CASH,
        fin_util.calc_scale(INIT_CASH, account.cash)*100))
    logging.info('---processor处理器打印金叉死叉---...')
    processor.print_cross()
    logging.info('---外部环境打印金叉死叉---...')
    logging.info('金叉出现次数={}, 金叉列表={}.'.format(len(gold_cross), ', '.join([str(x) for x in gold_cross])))
    logging.info('死叉出现次数={}, 死叉列表={}.'.format(len(dead_cross), ', '.join([str(x) for x in dead_cross])))
    logging.info('---打印买卖操作---')
    for op in operations:
        #date_str = datetime.strptime(dates[op[0]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        date_str = dates[op[0]]
        daily = processor.dailies.loc[op[0]]
        price = float(klines[op[0]][4])
        if op[1].is_golden():
            if op[2] == base_item.TRADE_STATUS.BUY:
                logging.info('金叉买入，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            elif op[2] == base_item.TRADE_STATUS.IGNORE or op[2] == base_item.TRADE_STATUS.HANDLED:
                logging.info('金叉忽略，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                logging.error('金叉操作错误，i={}，日期={}, 操作={}'.format(op[0], date_str, op[2]))
                #assert(False)
                pass
        elif op[1].is_dead() :
            if op[2] == base_item.TRADE_STATUS.SELL:
                logging.info('死叉卖出，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            elif op[2] == base_item.TRADE_STATUS.IGNORE or op[2] == base_item.TRADE_STATUS.HANDLED:
                logging.info('死叉忽略，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                logging.error('死叉操作错误，i={}，日期={}, 操作={}'.format(op[0], date_str, op[2]))
                #assert(False)
                pass
        else :
            if op[2] == base_item.TRADE_STATUS.SELL:
                logging.info('重要：最后一天卖出，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                logging.error('最后一天卖出操作错误，i={}，日期={}, 操作码={}'.format(op[0], date_str, op[2]))
                assert(False)
    logging.info('---打印买卖操作结束---')

    profits = list()
    if len(processor.dailies) > 0 :
        profits = processor.dailies['profit'].tolist()
        pf = fin_util.prices_info(profits)
        info = pf.find_max_trend(INCREMENT=False)
        logging.info('统计最大连续回撤返回={:.2f}%, bi={}, ei={}'.format(info[0]*100, info[1], info[2]-1))
        if info[1] >= 0 and info[2] > info[1]:
            begin_str = dates[info[1]]
            end_str = dates[info[2]-1]
            logging.info('MACD最大连续回撤={:.2f}%, bi={}, ei={}'.format(info[0]*100, begin_str, end_str))
            before = round(profits[info[1]-1], 2)
            after = round(profits[info[2]], 2)
            logging.info('MACD模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
            if not pf.check_order(info[1], info[2], ASCENDING=False):
                logging.error('最大连续回撤区间不是降序排列！')
                #pf.print(info[1], info[2])
        else :
            logging.error('未取到最大回撤，统计周期={}。'.format(len(profits)))

        holds = processor.dailies['hold'].tolist()
        info = fin_util.calc_hold_days(holds)
        logging.info('MACD模式-总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    return profits