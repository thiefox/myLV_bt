import numpy as np
import talib
import copy
from pandas import DataFrame, Series

import base_item

#计算MACD交叉点, macd即为快线(DIF)，signal即为慢线(DEA)
def find_macd_crossovers(macd : list, signal : list, hist : list) -> list:
    crossovers = []
    for i in range(1, len(macd)):
        if macd[i] > signal[i] and macd[i-1] < signal[i-1]:
            if macd[i] > 0 and signal[i] > 0 :  #0轴上金叉
                crossovers.append((i, base_item.MACD_CROSS.GOLD_ZERO_UP, macd[i]-signal[i], macd[i-1]-signal[i-1]))
            elif (macd[i] < 0 and signal[i] < 0) :  #0轴下金叉
                crossovers.append((i, base_item.MACD_CROSS.GOLD_ZERO_DOWN, macd[i]-signal[i], macd[i-1]-signal[i-1]))
            else :
                print('异常：金叉时macd={}, signal={}，忽略'.format(macd[i], signal[i]))
        elif macd[i] < signal[i] and macd[i-1] > signal[i-1]:
            if macd[i] > 0 and signal[i] > 0 :  #0轴上死叉
                crossovers.append((i, base_item.MACD_CROSS.DEAD_ZERO_UP, macd[i]-signal[i], macd[i-1]-signal[i-1]))
            elif macd[i] < 0 and signal[i] < 0 :  #0轴下死叉
                crossovers.append((i, base_item.MACD_CROSS.DEAD_ZERO_DOWN, macd[i]-signal[i], macd[i-1]-signal[i-1]))
            else :
                print('异常：死叉时macd={}, signal={}，忽略'.format(macd[i], signal[i]))
    return crossovers

#基于MACD和价格计算顶背离和底背离
def calc_macd_divergence(prices : list, macd : list, signal : list) -> tuple:
    peaks = []      #顶背离, 价格走高，macd走低，看衰。
    bottoms = []    #底背离, 价格走低，macd走高，看涨。
    for i in range(1, len(prices)):
        if prices[i] > prices[i-1] and macd[i] < macd[i-1] and signal[i] < signal[i-1]:
            peaks.append(i)
        elif prices[i] < prices[i-1] and macd[i] > macd[i-1] and signal[i] > signal[i-1]:
            bottoms.append(i)
    return peaks, bottoms

#计算持仓天数, amount>0为持仓标准。返回总天数和最大连续持仓天数
def calc_hold_days(amounts : list[float]) -> tuple:
    am = Series(amounts)
    am = am[am > 0]
    all = am.count()
    max = cur = 0
    index = am.index
    for i in range(len(index)):
        if i == 0 :
            cur = 1
        elif index[i] - index[i-1] == 1 :
            cur += 1
        else :
            if cur > max :
                max = cur
            cur = 1
    if cur > max :
        max = cur
    return all, max

#计算增长或下降比例，增长为正值，下降为负值
def calc_scale(begin_price : float, end_price : float) -> float:
    if begin_price == 0:
        return 0
    else :
        return (end_price - begin_price) / begin_price

#价格/价值列表类
class prices_info():
    def __init__(self, prices : list[float]):
        self.__prices = Series(prices)
        return
    def get(self, index : int) -> float:
        return self.__prices[index]
    #检查一个区间内价格有序性, 默认为升序
    def check_order(self, BEGIN : int = 0, END : int = -1, ASCENDING = True) -> bool:
        ordered = False
        if END == -1:
            END = len(self.__prices)
        if ASCENDING :
            ordered = self.__prices[BEGIN:END].is_monotonic_increasing
        else :
            ordered = self.__prices[BEGIN:END].is_monotonic_decreasing
        return ordered
    #打印一个区间内的价格
    def print(self, BEGIN : int = 0, END : int = -1, DATES : list = None):
        if END == -1:
            END = len(self.__prices)
        for i in range(BEGIN, END):
            if DATES is not None:
                print('index={}, date={}, price={}'.format(i, DATES[i], self.__prices[i]))
            else :
                print('index={}, price={}'.format(i, self.__prices[i]))
        return

    #计算价格列表上两个点之间的收益比例
    #盈利为正值，亏损为负值
    def calc_profit_scale(self, begin : int, end : int) -> float:
        if begin >= end :
            print('异常：begin={}, end={}'.format(begin, end))
        assert(begin < end)
        assert(end < len(self.__prices))
        begin_price = float(self.__prices[begin])
        end_price = float(self.__prices[end])
        return calc_scale(begin_price, end_price)

    #查找价格列表index往前的价格最高点
    #返回最高点和索引
    def find_prev_high(self, index : int) -> tuple:
        assert(index < len(self.__prices))
        found = self.__prices[:index].idxmax()
        high = self.__prices[found]
        return high, found

    #查找价格列表index往前的第一个峰值
    #返回峰值和索引
    def find_prev_peak(self, index : int) -> tuple:
        assert(index < len(self.__prices))
        diff = self.__prices[:index].diff()
        found = diff[diff > 0].index[-1]
        peak = self.__prices[found]
        return peak, found
    
    #查找最大的一段连续上升或下降趋势（最大回撤/最大涨幅）
    #返回趋势涨跌幅（涨为正值跌为负值），开始索引和结束索引+1
    def find_max_trend(self, INCREMENT = True) -> tuple:
        diff = self.__prices.diff()
        if INCREMENT :
            info = diff[diff > 0]
        else :
            info = diff[diff < 0]
        index = info.index
        max = [0, -1, -1]
        cur = [0, -1, -1]
        before = -1
        for i in range(len(index)):
            if before == -1 :   #第一个下降
                cur[0] = info[index[i]]
                cur[1] = cur[2] = index[i]
            elif index[i] - before == 1 :   #连续下降
                cur[0] += info[index[i]]
                cur[2] = index[i]
            else :  #断开
                if abs(cur[0]) > abs(max[0]) :
                    max = copy.deepcopy(cur)
                cur[0] = info[index[i]]
                cur[1] = cur[2] = index[i]
            before = index[i]
        if abs(cur[0]) > abs(max[0]) :  #最后一个趋势
            max = copy.deepcopy(cur)
        max[1] -= 1     #趋势从diff的前一个元素开始
        if max[1] >= 0 and max[2] > max[1] :
            max[0] = self.calc_profit_scale(max[1], max[2])   #计算涨跌幅
            max[2] += 1     #后开区间
        else :
            max = [0, -1, -1]
        return max[0], max[1], max[2]

    
    #计算MACD, 返回macd(快线/DIF), signal(慢线/DEA)和hist(MACD柱值)
    def calculate_macd(self) -> tuple:
        #DIF(macd)=差离值=快线
        #DEA(signal)=差离值平均数=慢线
        #第三个值macd_hist对应于macd的差值，即macd_hist=macd-signal。也即是所谓的红绿能量柱值。
        # /MACD
        # 金叉的意思就是快线（股票行情指标的短期线）向上穿越慢线（长期线）的交叉；死叉反之。通常情况下，金叉是买进信号，死叉为卖出信号。
        macd, signal, hist = getattr(talib, 'MACD')(np.array(self.__prices),  fastperiod=12, slowperiod=26, signalperiod=9)
        print('共计算出MACD记录数={}'.format(len(macd)))
        '''
        print('开始打印MACD原始值...')
        for i in range(len(macd)):
            if i >= 33 :    #macd和signal的前33个值为0(nan)
                print('index={}, macd={}, signal={}, hits={}'.format(i, macd[i], signal[i], hist[i]))
            pass
        print('打印MACD原始值结束.')
        '''
        return macd, signal, hist
    
def test() :
    data = [1, 5, 100, 85, 78, 84, 56, 27, 63, 14]
    data = [0, 0, 100, 100, 120, 0, 150, 150, 0, 200]
    sr = Series(data)
    new_sr = sr[sr > 0]
    index = new_sr.index
    max_consecutive = 0
    cur_consecutive = 0
    for i in range(len(index)):
        print('index={}, value={}'.format(index[i], new_sr[index[i]]))
        if i == 0 :
            cur_consecutive = 1
        elif index[i] - index[i-1] == 1 :
            cur_consecutive += 1
        else :
            if cur_consecutive > max_consecutive :
                max_consecutive = cur_consecutive
            cur_consecutive = 1
    if cur_consecutive > max_consecutive :
        max_consecutive = cur_consecutive
    hold_days = sr[sr > 0].count()
    print('持仓天数={}'.format(hold_days))
    print('最大连续持仓天数={}'.format(max_consecutive))
    return
    groups = sr.groupby(sr > 0)
    print('groups={}'.format(groups))
    count = groups.sum()
    print('count={}'.format(count))
    for g in groups:
        print('g={}'.format(g))
    print('cumsum={}'.format(groups.cumsum()))
    max = groups.count().max()
    print('max={}'.format(max))
    return

    diff = sr.diff()
    diff.fillna(0, inplace=True)
    print('diff={}'.format(diff))
    
    g = sr.diff().ne(0).cumsum()
    print('g={}'.format(g))
    max_consecutive = sr.groupby(g).count().max()
    return 


    diff = sr.diff()
    #print('diff={}'.format(diff))
    info = diff[diff < 0]
    print('info={}'.format(info))
    index = info.index
    max = [0, -1, -1]
    cur = [0, -1, -1]
    before = -1
    for i in range(len(index)):
        print('i={}, cur diff={}'.format(index[i], info[index[i]]))
        if before == -1 :   #第一个下降
            cur[0] = info[index[i]]
            cur[1] = cur[2] = index[i]
        elif index[i] - before == 1 :   #连续下降
            cur[0] += info[index[i]]
            cur[2] = index[i]
        else :  #断开
            print('断开，当前cur={}, max={}'.format(cur[0], max[0]))
            if abs(cur[0]) > abs(max[0]) :
                max = copy.deepcopy(cur)
            cur[0] = info[index[i]]
            cur[1] = cur[2] = index[i]
        before = index[i]
    if abs(cur[0]) > abs(max[0]) :
        max = copy.deepcopy(cur)
    max[1] -= 1
    max[2] += 1 
    #print('cur={}, cur_b={}, cur_e={}'.format(cur, cur_b, cur_e))
    print('max={}, begin={}, end={}'.format(max[0], max[1], max[2]))
    begin = max[1]
    end = max[2] - 1
    print('开始数值={}, 结束数值={}, 涨/跌幅={:.2f}%'.format(sr[begin], sr[end], calc_scale(sr[begin], sr[end])*100))


    '''
    print('index={}'.format(index))
    for i in range(len(index)):
        print('index={}, value={}'.format(index[i], sr[index[i]]))  
    '''
    #result = info.index.tolist()
    #print('result={}'.format(result))

    return

    POS = 5
    index = sr[:POS].idxmax()
    print('index={}, value={}'.format(index, sr[index]))
    #统计大于50的个数
    count = sr[sr > 50].count()
    print('count={}'.format(count))
    return 0

    df = DataFrame()
    df['close'] = data

    #计算价格的顶底均值（5日）
    df['mean'] = df['close'].rolling(window=5).mean()
    print('打印均值...')
    print(df['mean'])
    print('打印均值结束.')
    print('type of mean={}, len={}'.format(type(df['mean']), len(df['mean'])))
    print('type of close={}, len={}'.format(type(df['close']), len(df['close'])))
    #na = np.array(df['close'])
    #df['top_divergence'] 
    df['top_divergence'] = np.where(df['close'] > df['mean'], 1, 0)
    print('打印顶背离...')
    print('df[top_divergence]={}'.format(df['top_divergence']))
    print('打印顶背离结束.')
    
    

    #df['top_divergence'] = np.where((df['close'] > df['peak']) & (df['macd'] < df['macdsignal']))
    #df['bottom_divergence'] = np.where((df['close'] < df['valley']) & (df['macd'] > df['macdsignal']))


    print('test end')
    return 0

#test()