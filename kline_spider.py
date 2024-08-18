import requests
import json

import time

#int时间戳转换为字符串时间
def timestamp_to_string(time_stamp : int) -> str:
    #print('input={}'.format(time_stamp/1000))
    
    time_array = time.localtime(float(time_stamp/1000))
    str_date = time.strftime("%Y-%m-%d %H:%M:%S", time_array)
    return str_date

#字符串时间转换为int时间戳
def string_to_timestamp(str_date : str) -> int:
    #print('input={}'.format(str_date))
    time_array = time.strptime(str_date, "%Y-%m-%d %H:%M:%S")
    time_stamp = int(time.mktime(time_array) * 1000)
    return time_stamp

def get_kline_data(symbol, interval, limit):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    print('response={}'.format(response))
    if response.status_code == 200:
        return response.json()
    else:
        return None

# Example usage
symbol = "BTCUSDT"  # Replace with the desired symbol
interval = "1h"    # Replace with the desired interval (e.g., 1m, 5m, 1h, 1d)

kline_data = get_kline_data(symbol, interval, 1)
last = 0
if kline_data:
    assert(isinstance(kline_data, list))
    print('count={}'.format(len(kline_data)))
    
    for i in range(len(kline_data)):
        data = kline_data[i]
        #print('type of data[0]={}'.format(type(data[0])))
        begin = timestamp_to_string(data[0])
        end = timestamp_to_string(data[6])
        #end1 = timestamp_to_string(data[6]+1)
        last = data[6]
        print('开始时间={}，结束时间={}，'.format(begin, end))
        print('data={}'.format(data))
    print('当前结束时间={}'.format(timestamp_to_string(last)))
    last = last + 1

    #print('开始打印返回数据...')
    #print(kline_data)
    #print('结束打印返回数据.')
else:
    print("Failed to fetch K-line data from Binance API.")