import pandas
import numpy
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 画K线
def draw_kline(dates : numpy.ndarray, klines : list):
    # Create a new figure and axis
    fig, ax = plt.subplots()

    # Plot the candlestick chart
    ax.plot(dates, klines)

    # Customize the chart as needed (e.g., axis labels, title, etc.)
    plt.rcParams['font.sans-serif']='SimHei'

    ax.set_xlabel('时间')
    ax.set_ylabel('价格')
    ax.set_title('K线图')

    # Show the chart
    plt.show()
    return

# 画K线和收益曲线
def draw_kline_and_profile(dates : numpy.ndarray, klines : list, profiles : list, XUnit : str = 'M'):
    plt.rcParams['font.sans-serif']='SimHei'
    # Create a new figure and axis
    fig, ax = plt.subplots()

    if XUnit == 'Y':
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    elif XUnit == 'D':
        ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))        
    else :
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        #ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(ax.xaxis.get_major_locator()))
        #ax.xaxis.set_major_formatter(mdates.AutoDateFormatter(mdates.MonthLocator()))

    ax.set_xlabel('日期')
    ax.set_ylabel('趋势')
    ax.set_title('K线和收益曲线')

    #ma.plot(dates, index_values, color='blue')
    # 画K线
    ax.plot(dates, klines, label='K线', color='red')
    # 画收益曲线
    ax.plot(dates, profiles, label='收益', color='blue')

    # Show the chart
    plt.show()
    return

# Sample data for candlestick chart
data = [
    (1, 2, 3, 4),  # (open, high, low, close) for the first candlestick
    (2, 3, 4, 5),  # (open, high, low, close) for the second candlestick
    (3, 4, 5, 6),  # (open, high, low, close) for the third candlestick
    # Add more data as needed
]

#draw_kline(data)  # Draw the candlestick chart

