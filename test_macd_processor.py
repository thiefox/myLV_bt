import logging
from datetime import datetime

import base_item
import com_utils.log_adapter as log_adapter
import com_utils.utility as utility

import fin_util
import data_loader
import draw_profit
import MACD_process
import MACD_profit

def _test() :
    print("MACD process Start...")
    log_adapter.log_to_console('MACD_process', level = logging.DEBUG)
    #log_adapter.log_to_file('MACD_process', level= logging.DEBUG)
    
    su = base_item.save_unit(base_item.kline_interval.d1)
    #calc_profit(2017, 2025, base_item.kline_interval.d1)
    draw_profit.draw_kline_and_profit(2017, 2025, su, MACD_profit.calc_profit)

    print("MACD process End.")    
    return

def processor() -> int:
    su = base_item.save_unit(base_item.kline_interval.d1)
    BEGIN_YEAR = 2017
    CUR_YEAR = datetime.now().year
    CUR_MONTH = datetime.now().month
    CUR_DAY = datetime.now().day
    all_klines = list()
    for i in range(BEGIN_YEAR, CUR_YEAR+1):
        YEAR_DAYS = utility.days_in_year(i)
        year_klines = data_loader.load_klines_1Y(base_item.trade_symbol.BTCUSDT, i, su)
        if len(year_klines) > 0:
            last_begin = utility.timestamp_to_datetime(year_klines[-1][0])
            last_end = utility.timestamp_to_datetime(year_klines[-1][6])
            print('重要：{}年K线数据共{}条，最后一条开始时间={}，结束时间={}。'.format(i, len(year_klines), 
                last_begin.strftime('%Y-%m-%d %H:%M:%S'), last_end.strftime('%Y-%m-%d %H:%M:%S')))
            dates = [kline[0] for kline in year_klines]
            if i < CUR_YEAR :
                if fin_util.check_time_continuity(dates, su.interval) and last_begin.strftime('%m%d') == '1231':
                    print('重要：历史年{}K线数据时间连续。'.format(i))
                    all_klines.extend(year_klines)
                else :
                    print('异常：历史年{}K线数据时间不连续1。'.format(i))
                    return -1
                if len(all_klines) > 0 and len(year_klines) < YEAR_DAYS:
                    print('异常：中间历史年{}K线数据不全，应有{}条，实际{}条。'.format(i, YEAR_DAYS, len(year_klines)))
                    return -1
            else :
                if fin_util.check_time_continuity(dates, su.interval):
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

#processor()
#_test()