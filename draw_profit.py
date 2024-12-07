import numpy as np

from utils import utility

from base_item import trade_symbol, save_unit
import data_loader
import draw

def draw_klines(b_year : int, e_year : int, su : save_unit):
    if e_year - b_year == 1:
        UNIT = 'M'
    else :
        UNIT = 'Y'    
    klines = data_loader.load_klines_years(trade_symbol.BTCUSDT, b_year, e_year, su)
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

def draw_kline_and_profit(b_year : int, e_year : int, su : save_unit, func : callable):
    if func is None :
        return draw_klines(b_year, e_year, su)
    if e_year - b_year == 1:
        UNIT = 'M'
    else :
        UNIT = 'Y'
    klines = data_loader.load_klines_years(trade_symbol.BTCUSDT, b_year, e_year, su)
    if klines:
        print('共获取到K线数据记录={}'.format(len(klines)))
        dates = [utility.timestamp_to_datetime(kline[0]) for kline in klines]
        #把dates转换为numpy数组
        dates = np.array(dates)
        closed_prices = [float(kline[4]) for kline in klines]
        profits = func(b_year, e_year, su)
        if profits is None or len(profits) != len(closed_prices):
            print("Failed to get profit data.")
        else :
            draw.draw_kline_and_profile(dates, closed_prices, profits, XUnit=UNIT)
    else :
        print("Failed to fetch kline data.")
    return