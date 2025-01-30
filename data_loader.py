import os
import json
from datetime import datetime, timedelta

import utils.utility as utility
import utils.log_adapter as log_adapter

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
def _load_klines(symbol : trade_symbol, su : save_unit, begin_t : datetime) -> list:
    klines = list()
    assert(isinstance(begin_t, datetime))
    file_name = fin_util.get_kline_file_name(symbol, su, begin_t)
    if os.path.exists(file_name):
        try :
            with open(file_name, 'r') as f:
                klines = json.load(f)
        except Exception as e:
            log_adapter.color_print('异常：读取K线数据文件{}失败={}'.format(file_name, e), log_adapter.COLOR.RED)
    else :
        log_adapter.color_print('异常：K线数据文件{}不存在'.format(file_name), log_adapter.COLOR.RED)
    return klines

#载入从begin_t到end_t时间区间内的所有K线数据(>=begin_t, < end_t)
def load_klines_range(symbol: trade_symbol, su: save_unit, begin_t: datetime, end_t: datetime) -> list:
    all_klines = list()
    assert(isinstance(begin_t, datetime))
    assert(isinstance(end_t, datetime))
    begin = int(begin_t.timestamp() * 1000)
    end = int(end_t.timestamp() * 1000)
    assert(begin <= end)
    current = begin
    assert(isinstance(current, int))
    FULL_SECONDS = su.get_unit_seconds(begin_t)
    log_adapter.color_print('通知：SU间隔={}，倍数模式={}'.format(su.interval.value, su.multiple), log_adapter.COLOR.YELLOW)
    cn = 0
    while current < end:
        if not isinstance(current, int):
            log_adapter.color_print('异常：cn={}, current={}，类型={}'.format(cn, current, type(current)), log_adapter.COLOR.RED)
            assert(False)
        s_current= utility.timestamp_to_string(current)
        full = su.get_K_count(utility.timestamp_to_datetime(current))
        assert(full > 0)
        klines = _load_klines(symbol, su, utility.timestamp_to_datetime(current))
        if len(klines) > 0 :
            assert(len(klines) <= full)
            start_time = int(klines[0][0])
            end_time = int(klines[-1][6])
            DIFF_SECONDS = su.interval.get_delta().total_seconds() * len(klines)
            if len(all_klines) == 0 :   #第一次
                if len(klines) == full:
                    assert(start_time == current)
                assert(end_time == current + DIFF_SECONDS * 1000 - 1)
            else :
                assert(start_time == current)
                if len(klines) == full:
                    assert(end_time == current + DIFF_SECONDS * 1000 - 1)

            if end_time + 1 - start_time != DIFF_SECONDS * 1000:
                log_adapter.color_print('异常：开始={}，获取K线数据={}，full={}，时间连续性检查失败。'.format(s_current, 
                    len(klines), full), log_adapter.COLOR.RED)
                log_adapter.color_print('异常：开始时间={}，结束时间={}，时间差={}，理论时间差={}。'.format(utility.timestamp_to_string(start_time), 
                    utility.timestamp_to_string(end_time), end_time + 1 - start_time, DIFF_SECONDS * 1000), log_adapter.COLOR.RED)
                assert(False)
                all_klines.clear()
                break
            if len(klines) == full:
                assert(start_time == current)
                all_klines.extend(klines)
            else :
                all_klines.extend(klines)
                log_adapter.color_print('重要：开始={}，获取K线数据={}，小于full={}，提前结束。'.format(s_current, len(klines), full),
                    log_adapter.COLOR.YELLOW)
                break
        else :
            log_adapter.color_print('异常：未获取到开始={}的K线数据，已有{}条数据清零。'.format(s_current, len(all_klines)), log_adapter.COLOR.RED)
            all_klines.clear()
            break
        current += int(FULL_SECONDS * 1000)
        cn += 1

    return all_klines

#载入某月的K线数据
def load_klines_1M(symbol : trade_symbol, year : int, month : int, su : save_unit) -> list:
    begin = datetime.strptime('{}-{}-01 00:00:00'.format(year, str(month).zfill(2)), '%Y-%m-%d %H:%M:%S')
    end = begin + timedelta(days=utility.days_in_month(year, month))
    print('通知：载入月份数据，开始={}，结束={}...'.format(begin.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S')))
    #klines = _load_klines(symbol, su, begin)
    klines = load_klines_range(symbol, su, begin, end)
    return klines

#载入一年的K线数据
def load_klines_1Y(symbol : trade_symbol, year : int, su : save_unit) -> list:
    klines = list()
    now = datetime.now()
    for i in range(1, 13):
        if year == now.year and i > now.month:
            log_adapter.color_print('重要：当前时间={}，不再获取{}年-{}月的K线数据'.format(now, year, i), log_adapter.COLOR.YELLOW)
            break
        month_klines = load_klines_1M(symbol, year, i, su)
        if len(month_klines) > 0:
            klines.extend(month_klines)
        else :
            log_adapter.color_print('异常：未获取到{}年-{}月的K线数据'.format(year, i), log_adapter.COLOR.RED)
    return klines

#载入多个年份的K线数据
def load_klines_years(symbol : trade_symbol, begin_year : int, end_year : int, su : save_unit) -> list:
    assert(begin_year < end_year)
    klines = list()
    for i in range(begin_year, end_year):
        if i > datetime.now().year:
            log_adapter.color_print('重要：当前时间={}，不再获取{}年的K线数据'.format(datetime.now(), i), log_adapter.COLOR.YELLOW)
            break
        #print('通知：处理年份={}'.format(i))
        klines.extend(load_klines_1Y(symbol, i, su))
    return klines

def test() : 
    all_klines = list()
    su = save_unit(kline_interval.h1)
    log_adapter.color_print('通知：SU间隔={}，倍数模式={}'.format(su.interval.value, su.multiple), log_adapter.COLOR.YELLOW)
    YEAR = 2024
    MONTH_BEGIN = 11
    MONTH_END = 13
    for i in range(MONTH_BEGIN, MONTH_END):
        klines = load_klines_1M(trade_symbol.BTCUSDT, YEAR, i, su)
        if len(klines) > 0:
            log_adapter.color_print('通知：获取到{}年{}月K线数据记录={}'.format(YEAR, i, len(klines)), log_adapter.COLOR.GREEN)
            first_begin = int(klines[0][0])
            first_end = int(klines[0][6])
            last_begin = int(klines[-1][0])
            last_end = int(klines[-1][6])
            log_adapter.color_print('通知：第一条记录开始时间={}，结束时间={}。'.format(utility.timestamp_to_string(first_begin), 
                utility.timestamp_to_string(first_end)), log_adapter.COLOR.YELLOW)
            log_adapter.color_print('通知：最后一条记录开始时间={}，结束时间={}。'.format(utility.timestamp_to_string(last_begin), 
                utility.timestamp_to_string(last_end)), log_adapter.COLOR.YELLOW)
            all_klines.extend(klines)
        else :
            log_adapter.color_print('异常：未获取到{}年{}月K线数据'.format(YEAR, i), log_adapter.COLOR.RED)
            break

    dates = [kline[0] for kline in all_klines]
    if fin_util.check_time_continuity(dates, su.interval) :
        log_adapter.color_print('通知：K线数据时间连续性检查通过', log_adapter.COLOR.GREEN)
    else :
        log_adapter.color_print('异常：K线数据时间连续性检查失败', log_adapter.COLOR.RED)
    return

test()