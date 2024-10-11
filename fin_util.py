
#价格/价值列表类
class prices_info():
    def __init__(self, prices : list):
        self.prices = prices
        self.max_price = max(prices)
        self.min_price = min(prices)
        self.avg_price = sum(prices) / len(prices)
        return

    #计算价格列表上两个点之间的收益比例
    #盈利为正值，亏损为负值
    def calc_profit_scale(self, begin : int, end : int) -> float:
        assert(begin < end)
        assert(end < len(self.prices))
        begin_price = float(self.prices[begin])
        end_price = float(self.prices[end])
        return round((end_price - begin_price) / begin_price, 4)

    #查找价格列表的前一个最高点
    #返回最高点和索引
    def find_prev_high(self, index : int) -> tuple:
        assert(index < len(self.prices))
        high = 0
        high_index = -1
        for i in range(index-1, 0, -1):
            if self.prices[i] > high:
                high = self.prices[i]
                high_index = i
        return high, high_index

    #查找价格列表的前一个峰值
    #返回峰值和索引
    def find_prev_peak(self, index : int) -> tuple:
        assert(index < len(self.prices))
        peak = 0
        peak_index = -1
        for i in range(index-1, 0, -1):
            if self.prices[i] > self.prices[i-1] and self.prices[i] > self.prices[i+1]:
                peak = self.prices[i]
                peak_index = i
                break
        return peak, peak_index

    #计算价格列表上指定一段区间的最大回撤
    #返回回撤比例和起始索引
    def calc_max_drawdown(self, begin : int, end : int) -> tuple:
        assert(begin < end)
        assert(end < len(self.prices))
        max_drawdown = 0
        max_drawdown_index = -1
        for i in range(begin, end):
            for j in range(i+1, end):
                drawdown = (self.prices[j] - self.prices[i]) / self.prices[j]
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_index = i
        return max_drawdown, max_drawdown_index