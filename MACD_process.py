import pandas as pd
import numpy as np

def calculate_macd(df, short_window=12, long_window=26, signal_window=9):
    df['EMA_short'] = df['Close'].ewm(span=short_window, adjust=False).mean()
    df['EMA_long'] = df['Close'].ewm(span=long_window, adjust=False).mean()
    df['MACD'] = df['EMA_short'] - df['EMA_long']
    df['Signal'] = df['MACD'].ewm(span=signal_window, adjust=False).mean()
    return df

def generate_signals(df, max_drawdown=0.1):
    buy_signals = []
    sell_signals = []
    position = None
    peak = df['Close'][0]
    
    for i in range(1, len(df)):
        if df['MACD'][i] > df['Signal'][i] and df['MACD'][i-1] <= df['Signal'][i-1]:
            if position is None:
                buy_signals.append(i)
                position = i
                peak = df['Close'][i]
        elif df['MACD'][i] < df['Signal'][i] and df['MACD'][i-1] >= df['Signal'][i-1]:
            if position is not None:
                sell_signals.append(i)
                position = None
        if position is not None:
            peak = max(peak, df['Close'][i])
            drawdown = (peak - df['Close'][i]) / peak
            if drawdown > max_drawdown:
                sell_signals.append(i)
                position = None

    return buy_signals, sell_signals


'''
# 示例数据
data = {
    'Close': [100, 102, 101, 105, 107, 106, 108, 110, 109, 111, 113, 112, 115, 114, 116]
}
df = pd.DataFrame(data)

# 计算MACD
df = calculate_macd(df)

# 生成买点和卖点
buy_signals, sell_signals = generate_signals(df)

print("买点:", buy_signals)
print("卖点:", sell_signals)
'''