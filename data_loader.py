import os
import json
from datetime import datetime

import utils.utility as utility

from base_item import trade_symbol, kline_interval, save_unit
import fin_util

#把一条K线数据的价格转换为float
def get_kline_shape(kline : list) -> list:
    '''
    assert(isinstance(kline, list))
    print('len(kline)={}'.format(len(kline)))
    print('kline={}'.format(kline))
    assert(len(kline) == 12)
    '''
    #print('len(kline)={}'.format(len(kline)))
    if len(kline) == 12:
        return [int(kline[0]), float(kline[1]), float(kline[2]), float(kline[3]), float(kline[4]), 
            float(kline[5]), int(kline[6]), float(kline[7]), int(kline[8]), float(kline[9]), float(kline[10]), float(kline[11])]
    elif len(kline) == 1:
        kline = kline[0]
        return [int(kline[0]), float(kline[1]), float(kline[2]), float(kline[3]), float(kline[4]), 
            float(kline[5]), int(kline[6]), float(kline[7]), int(kline[8]), float(kline[9]), float(kline[10]), float(kline[11])]
    else :
        assert(False)


#载入K线数据
#count为从当前时间往前的N条K线数据。如count=0表示获取所有的本地K线数据
def load_klines(symbol : trade_symbol, su : save_unit, count : int) -> list:
    klines = list()
    now = datetime.now()
    while True:
        file_name = fin_util.get_kline_file_name(symbol, su, utility.datetime_to_timestamp(now))
        if not os.path.exists(file_name):
            print('K线数据文件{}不存在'.format(file_name))
            now = now - su.interval
            continue
        try :
            with open(file_name, 'r') as f:
                klines = json.load(f)
        except Exception as e:
            print('读取K线数据文件{}失败={}'.format(file_name, e))
        break

    return klines

#载入K线数据文件
def load_klines_1M(symbol : trade_symbol, year : int, month : int, su : save_unit) -> list:
    #begin = utility.string_to_timestamp('{}-{}-01 00:00:00'.format(year, str(month).zfill(2)))
    begin = datetime.strptime('{}-{}-01 00:00:00'.format(year, str(month).zfill(2)), '%Y-%m-%d %H:%M:%S')
    file_name = fin_util.get_kline_file_name(symbol, su, begin)
    print('数据文件名={}'.format(file_name))
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
def load_klines_1Y(symbol : trade_symbol, year : int, su : save_unit) -> list:
    klines = list()
    for i in range(1, 13):
        month_klines = load_klines_1M(symbol, year, i, su)
        if len(month_klines) > 0:
            klines.extend(month_klines)
        else :
            print('异常：未获取到{}年-{}月的K线数据'.format(year, i))
    return klines

#载入多个年份的K线数据
def load_klines_years(symbol : trade_symbol, begin_year : int, end_year : int, su : save_unit) -> list:
    assert(begin_year < end_year)
    klines = list()
    for i in range(begin_year, end_year):
        print('处理年份={}'.format(i))
        klines.extend(load_klines_1Y(symbol, i, su))
    return klines

def test() : 
    su = save_unit(kline_interval.d1)
    klines = load_klines_years(trade_symbol.BTCUSDT, 2020, 2021, su)
    print('获取到K线数据记录={}'.format(len(klines)))
    dates = [kline[0] for kline in klines]
    continues = fin_util.check_time_continuity(dates, su.interval)
    print('K线数据时间连续性={}'.format(continues))
    return

#test()