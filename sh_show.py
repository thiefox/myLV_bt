import pandas as pd  
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
#%matplotlib inline

#正常显示画图时出现的中文和负号
from pylab import mpl
mpl.rcParams['font.sans-serif']=['SimHei']
mpl.rcParams['axes.unicode_minus']=False

#引入TA-Lib库
import talib as ta

#获取交易数据用于示例分析
import tushare as ts

#通过tushare获取2023年的上证指数数据
def get_data(code):
    df = ts.get_hist_data(code,start='2023-01-01',end='2023-12-31')
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df

STOCK_CODE = '600028.SH'

ts_pro = ts.pro_api('ce1e9b68e91e19b5b695c568155ba578dca597609a6ba5a4bd5f24a6')
df = ts_pro.daily(ts_code=STOCK_CODE, start_date='20230101', end_date='20240101')
print('type of df ={}'.format(type(df)))
print('df.index={}'.format(df.index))
cl = df.columns.tolist()
print('df.columns={}'.format(cl))
#arr = np.array(df)      #将DataFrame转换为ndarray
print(df.head())

# Data for Shanghai Composite Index in 2023
#dates = df.index.strftime('%b')  # Extract month abbreviations from index dates
dates = df['trade_date'].values
index_values = df['close'].values  # Extract closing prices from the 'close' column

dates = pd.to_datetime(dates)

#plt的横轴显示月份
#plt.figure(figsize=(10,6), dpi=1000)

ax = plt.subplot(2, 1, 1)
ax.plot(dates, index_values, color='red')

ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
#ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(ax.xaxis.get_major_locator()))
#ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(mdates.MonthLocator()))

ax.set_xlabel('日期')
ax.set_ylabel('价格')
ax.set_title(STOCK_CODE)


ma = plt.subplot(2, 1, 2)
#用ma画MACD图
#计算MACD指标
df['macd'], df['signal'], df['hist'] = ta.MACD(df['close'].values, fastperiod=12, slowperiod=26, signalperiod=9)
#画出MACD线
ma.plot(dates, df['macd'], label='MACD Line', color='red')
#画出signal线
ma.plot(dates, df['signal'], label='Signal Line', color='blue')
#画出diff线
ma.bar(dates, df['hist'], label='MACD Histogram', color='gray')


#ma.plot(dates, index_values, color='blue')

ma.xaxis.set_major_locator(mdates.MonthLocator())
ma.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
#ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(ax.xaxis.get_major_locator()))
#ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(mdates.MonthLocator()))

ma.set_xlabel('日期')
ma.set_ylabel('趋势')
ma.set_title(STOCK_CODE)

#subplot可以绘制多个子图
# Plotting the data
#plt.plot(dates, index_values, color='red')
#plt.xlabel('Day')
#plt.ylabel('价格')
#plt.title(STOCK_CODE)

# Displaying the plot
plt.show()

exit()





