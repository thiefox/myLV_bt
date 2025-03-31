import sys
import os
import logging
from datetime import datetime

import pandas as pd
import numpy as np

from com_utils import utility
from com_utils import log_adapter
from com_utils import config

import base_item
import data_loader
import fin_util
import draw_profit
import mail_template
import binance_spot_wrap

class CROSS_DESC():
    def __init__(self, id : int, cross : base_item.MACD_CROSS, timestamp : int, 
            status : base_item.TRADE_STATUS = base_item.TRADE_STATUS.IGNORE) -> None:
        self.__id = id                  #交叉点的索引
        self.__cross = cross            #交叉类型
        self.__status = status          #交易状态
        self.__timestamp = timestamp    #交叉点的时间戳
        return
    @property
    def id(self) -> int:
        return self.__id
    @property
    def cross(self) -> base_item.MACD_CROSS:
        return self.__cross
    @property
    def status(self) -> base_item.TRADE_STATUS:
        return self.__status
    @property
    def timestamp(self) -> int:
        return self.__timestamp
    def update_status(self, status : base_item.TRADE_STATUS):
        self.__status = status
        return

class MACD_processor():
    SLOW_PERIOD = 26
    FAST_PERIOD = 12
    SIGNAL_PERIOD = 9
    MAX_CROSS_COUNT = 200
    def _reset_klines(self):
        self.__klines = pd.DataFrame(columns=['date_b', 'open', 'high', 'low', 'close', 
            'volume', 'date_e', 'amount', 'count', 'buy_amount', 'buy_money', 'ignore'])
        return
    def __init__(self, symbol : base_item.trade_symbol, config : config.Config) -> None:
        self.__config = config
        self.__account = base_item.part_account('13', 'thiefox')
        self._reset_klines()
        self.__symbol = symbol
        self.DAILY_LOG = False
        self.dailies = pd.DataFrame(columns=['date', 'cash', 'hold', 'profit'])
        #交叉点列表，索引/交叉点/交易状态/时间戳
        #记录的是出现的交叉点，而不是处理的交叉点，后者是前者的子集
        self.crosses = list[CROSS_DESC]()    
        hc_info = self.__config.get_hc()    
        if hc_info[0] > 0 :
            logging.info('processor重新启动，最后处理交叉点时间={}，类型={}，状态={}'.format(utility.timestamp_to_string(hc_info[0]), hc_info[1], hc_info[2]))
        else :
            logging.info('processor第一次运行，没有最后处理交叉点。')
        #WINDOW_LENGTH=0表示不限制K线数量
        #114天结果和无限一样，114为最小临界窗口
        self.WINDOW_LENGTH = 120
        return
    @property
    def symbol(self) -> base_item.trade_symbol:
        return self.__symbol
    @property
    def account(self) -> base_item.part_account:
        return self.__account
    @property
    def len(self) -> int:
        return len(self.__klines)
    def set_config(self, config : config.Config):
        self.__config = config
        return
    def set_account(self, account : base_item.part_account):
        self.__account = account
        return
    def open_daily_log(self, LOG : bool):
        self.DAILY_LOG = LOG
        return
    #取得最后一个处理过的交叉点，从配置文件中读取
    def get_last_handled_cross(self) -> CROSS_DESC:
        hc_info = self.__config.get_hc()
        if hc_info[0] > 0 :
            timeinfo = hc_info[0]
            cross = base_item.MACD_CROSS(hc_info[1])
            if hc_info[2] == '' :
                status = base_item.TRADE_STATUS.IGNORE
            else :
                status = base_item.TRADE_STATUS(hc_info[2])
            return CROSS_DESC(-1, cross, timeinfo, status)
        else :
            return None
    #取得最后一个交叉点
    def get_last_cross(self) -> CROSS_DESC :
        if len(self.crosses) > 0 :
            return self.crosses[-1]
        else :
            return None
    #更新交叉点状态
    def update_cross_status(self, id : int, status : base_item.TRADE_STATUS):
        for cross in self.crosses:
            if cross.id == id :
                assert(cross.status == base_item.TRADE_STATUS.IGNORE)
                cross.update_status(status)
                return
    #初始化历史K线数据
    #返回槽中的K线数量
    def init_history(self, klines : list) -> int:
        logging.debug('初始化历史K线数据...')
        self._reset_klines()    #复位
        begin = 0
        #保留最近的WINDOW_LENGTH条K线数据
        if self.WINDOW_LENGTH > 0 and len(klines) > self.WINDOW_LENGTH :
            begin = len(klines) - self.WINDOW_LENGTH
        for kline in klines[begin:]:
            self.__klines.loc[len(self.__klines)] = data_loader.get_kline_shape(kline)
        self.print_kline(0)     #打印第一条K线
        self.print_kline(-1)    #打印最后一条K线
        logging.debug('初始化历史K线数据完成，共{}条K线.'.format(len(self.__klines)))
        self.__process_ex(HISTORY=True)
        return len(self.__klines)
    #更新一条K线数据
    def update_kline(self, kline : list) -> tuple[base_item.MACD_CROSS, base_item.TRADE_STATUS, int, dict]:
        assert(isinstance(kline, list))
        kline = data_loader.get_kline_shape(kline)
        if len(self.__klines) == 0 :    #第一条K线
            self.__klines.loc[0] = kline
            logging.debug('第一条K线，开始时间={}.'.format(utility.timestamp_to_string(kline[0])))
        else :
            last_begin = int(self.__klines.iloc[-1, 0])
            last_index = self.__klines.index[-1] 
            if last_begin == kline[0] : #开始时间戳相同->最后一条K线的更新
                self.__klines.loc[last_index] = kline
                logging.info('更新最后一条K线，开始时间={}，开盘价={}，最新价={}.'.format(utility.timestamp_to_string(kline[0]),
                    round(self.__klines.loc[last_index, 'open'], 2), round(self.__klines.loc[last_index, 'close'], 2)))
            else :      #新增一条K线
                self.__klines.loc[last_index+1] = kline
                logging.info('新增一条K线，开始时间={}.'.format(utility.timestamp_to_string(kline[0])))
                #保留最近的WINDOW_LENGTH条K线数据
                if self.WINDOW_LENGTH > 0 and len(self.__klines) > self.WINDOW_LENGTH :
                    #self.__klines = self.__klines.iloc[-self.WINDOW_LENGTH:]
                    #删除第一条K线
                    self.__klines = self.__klines.drop(self.__klines.index[0])
                    logging.info('重要：删除最早的一条K线，剩余数量={}'.format(len(self.__klines)))
        if self.WINDOW_LENGTH > 0 :
            assert(len(self.__klines) <= self.WINDOW_LENGTH)
        #取得第一条K线的日期
        #first_date = int(self.__klines.loc[self.__klines.index[0], 'date_b'])
        first_date = int(self.__klines.iloc[0, 0])
        last_date = int(self.__klines.iloc[-1, 0])
        date_first = utility.timestamp_to_string(first_date, ONLY_DATE=True)
        date_last = utility.timestamp_to_string(last_date, ONLY_DATE=True)
        logging.debug('通知：窗口={}, 第一条K线={}，最后一条K线={}.'.format(len(self.__klines), date_first, date_last))
        return self.__process_ex(HISTORY=False)
    #打印某条K线数据，index区间为[-len(klines), len(klines)-1]，即iloc坐标系
    def print_kline(self, index : int):
        if abs(index) >= len(self.__klines) :
            return
        begin = int(self.__klines.iloc[index, 0])
        s_begin = utility.timestamp_to_string(begin)
        end = int(self.__klines.iloc[index, 6])
        s_end = utility.timestamp_to_string(end)
        logging.info('第{}条K线开始={}, 结束={}，开盘价={}, 收盘价={}, 最高价={}, 最低价={}。'.format(index, s_begin, s_end,
            self.__klines.iloc[index, 1], self.__klines.iloc[index, 4],
            self.__klines.iloc[index, 2], self.__klines.iloc[index, 3]))
        return
    def get_time_begin(self, index : int) -> int:
        return int(self.__klines.iloc[index, 0])
    def get_time_end(self, index : int) -> int:
        return int(self.__klines.iloc[index, 6])
    def get_price_open(self, index : int) -> float:
        return round(self.__klines.iloc[index, 1], 2)
    def get_price_close(self, index : int) -> float:
        return round(self.__klines.iloc[index, 4], 2)
    #市价买单，如果amount=0，则满仓买入
    #返回dict有效则成功，None为买入失败
    def buy_market(self, amount : float = 0) -> dict:
        bsw = binance_spot_wrap.binance_spot_wrapper()
        if bsw.init() :
            return bsw.buy_with_market(self.symbol.get_base(), amount)
        else :
            infos = dict()
            infos['local_code'] = -1
            infos['local_msg'] = 'bsw初始化失败'
            return infos
    #市价卖单，如果amount=0，则全部卖出
    #返回dict有效则成功，None为卖出失败
    def sell_martket(self, amount : float = 0) -> dict:
        bsw = binance_spot_wrap.binance_spot_wrapper()
        if bsw.init() :
            return bsw.sell_with_market(self.symbol.get_base(), amount)
        else :
            infos = dict()
            infos['local_code'] = -1
            infos['local_msg'] = 'bsw初始化失败'
            return infos
    #处理MACD交叉
    #index: 交叉发生的K线索引
    def __process_cross(self, cross : base_item.MACD_CROSS, index : int) -> tuple[base_item.TRADE_STATUS, dict]:
        logging.debug('打印K线数据, input index={}...'.format(index))
        index = self.__klines.index[index]
        assert(self.__config is not None)
        infos = None
        logging.debug('klines总数={}, klines重置索引={}, 交叉={}'.format(self.len, index, cross))
        #print('内部索引={}, 外部索引={}, 交叉={}'.format(ni, index, cross))
        status = base_item.TRADE_STATUS.IGNORE
        #date_str = utility.timestamp_to_string(self.__klines[index, 'date_b'], ONLY_DATE=True)
        date_str = utility.timestamp_to_string(int(self.__klines.loc[index, 'date_b']), ONLY_DATE=True)
        if cross.is_golden() and not cross.is_updown() : #金叉
            buy_price = self.__klines.loc[index, 'close']
            logging.info('重要：日期={}，出现金叉，币价={}，尝试买入操作...'.format(date_str, round(buy_price, 2)))
            infos = self.buy_market()
            if infos['local_code'] == 0 :
                status = base_item.TRADE_STATUS.BUY
            else :
                if infos['local_code'] == -100 :        #余额不足导致无法买入
                    status = base_item.TRADE_STATUS.IGNORE
                else :
                    status = base_item.TRADE_STATUS.FAILED
        elif cross.is_dead() and not cross.is_updown() : #死叉
            sell_price = self.__klines.loc[index, 'close']
            logging.info('重要：日期={}，出现死叉，币价={}，尝试卖出操作...'.format(date_str, round(sell_price, 2)))
            infos = self.sell_martket()
            if infos['local_code'] == 0 :
                status = base_item.TRADE_STATUS.SELL
            else :
                if infos['local_code'] == -100 :        #余币不足导致无法卖出
                    status = base_item.TRADE_STATUS.IGNORE
                else :
                    status = base_item.TRADE_STATUS.FAILED
        else :
            status = base_item.TRADE_STATUS.IGNORE
            pass
        return status, infos

    def print_crossover(crossovers : list, closes : list, dates : list[str], asascend : bool = True):
        cur = 0
        his = 0
        gold_cnt = dead_cnt = 0
        gold_updown = dead_updown = 0
        logs = list[str]()
        for cross in crossovers:
            index : int = cross[0]
            cross_type : base_item.MACD_CROSS = cross[1]
            if cross_type.is_golden() :
                gold_cnt += 1
                if cross_type.is_updown() :
                    gold_updown += 1
            elif cross_type.is_dead() :
                dead_cnt += 1
                if cross_type.is_updown() :
                    dead_updown += 1
            if index == len(closes) - 1 :
                DATE_INFO = '当前'
                cur += 1
            else :
                DATE_INFO = '历史'
                his += 1

            if cross_type.is_golden() :
                if cross_type.is_updown() :
                    logs.append('{}K线发现跨0轴金叉（忽略），索引={}，时间={}。'.format(DATE_INFO, index, dates[index]))
                else :
                    logs.append('{}K线发现金叉，索引={}，时间={}。'.format(DATE_INFO, index, dates[index]))
            elif cross_type.is_dead() :
                if cross_type.is_updown() :
                    logs.append('{}K线发现跨0轴死叉（忽略），索引={}，时间={}。'.format(DATE_INFO, index, dates[index]))
                else :
                    logs.append('{}K线发现死叉，索引={}，时间={}。'.format(DATE_INFO, index, dates[index]))

        if not asascend :
            logs.reverse()
        for log in logs:
            logging.info(log)

        if cur > 0 :
            logging.info('共找到{}个MACD交叉点，其中当前K线={}个，历史K线={}。'.format(len(crossovers), cur, his))
        else :
            logging.info('共找到{}个MACD交叉点，全部为历史K线={}个。'.format(len(crossovers), his))
        logging.info('金叉总数量={}, 0轴金叉数量（忽略）={}, 死叉总数量={}, 0轴死叉数量（忽略）={}.'.format(gold_cnt, gold_updown, dead_cnt, dead_updown))
        return
    
    #如HISTORY=True，则检测和打印数据列表上的所有交叉点，不处理。
    #如HISTORY=False，则检测数据列表的最后一条是否有交叉点，有则处理。
    def __process_ex(self, HISTORY : bool = False) -> tuple[base_item.MACD_CROSS, base_item.TRADE_STATUS, int, dict]:
        cross = base_item.MACD_CROSS.NONE
        status = base_item.TRADE_STATUS.IGNORE
        time_i = int(0)
        infos = None
        #获取收盘价列表
        assert(len(self.__klines) > 0)
        #获取最后一条K线的收盘价
        #close = self.__klines.loc[len(self.__klines)-1, 'close']  #最后一条K线的收盘价
        opens = self.__klines['open'].tolist()
        closes = self.__klines['close'].tolist()
        dates = self.__klines['date_b'].tolist()
        dates = [int(i) for i in dates]
        dates_str = [utility.timestamp_to_string(int(i), ONLY_DATE=True) for i in dates]
        #print('closes={}'.format(closes))
        last_date_end = utility.timestamp_to_string(int(self.__klines.loc[len(self.__klines)-1, 'date_e']))
        #print('当前K线数量，方法1={}，方法2={}'.format(len(closes), len(self.__klines)))
        #print('最后一条K线，开始时间={}, 结束时间={}，开盘价={}, 收盘价={}'.format(dates_str[-1], last_date_end, opens[-1], closes[-1]))
        if len(closes) > 0 :
            assert(isinstance(closes[0], float))
        pi = fin_util.prices_info(closes)
        #计算MACD
        macd, signal, hist = pi.calculate_macd()
        crossovers = fin_util.find_macd_crossovers(macd, signal, hist, ONLY_LAST=not HISTORY)

        '''
        if len(crossovers) > 0 :
            MACD_processor.print_crossover(crossovers, closes, dates_str, asascend=True)
        '''

        if len(crossovers) > 0 :
            if len(crossovers) > 1 :
                for cross in crossovers[:-1]:
                    index : int = cross[0]
                    cross : base_item.MACD_CROSS = cross[1]
                    time_i = dates[index]
                    cd = CROSS_DESC(index, cross, time_i)
                    self.crosses.append((cd))
                    

            index : int = crossovers[-1][0]
            cross : base_item.MACD_CROSS = crossovers[-1][1]
            #timeinfo = int(self.__klines.loc[index, 'date_b'])
            time_i = dates[index]
            cd = CROSS_DESC(index, cross, time_i)
            if not HISTORY :
                assert(len(crossovers) == 1)
                assert(index == len(closes) - 1)
            if not cross.is_updown() :  #非0轴上下的交叉
                oi = self.__klines.index[index]
                if len(self.crosses) == 0 :
                    self.crosses.append((cd))
                else :
                    last_cd = self.crosses[-1]
                    if cd.id > last_cd.id :
                        if cross.is_opposite(last_cd.cross) :  #交叉点相反
                            self.crosses.append((cd))
                        else :
                            logging.critical('交叉点=({},{})和最后一个交叉点=({},{})相同类型.'.format(cd.id, cd.cross, last_cd.id, last_cd.cross))
                    elif cd.id == last_cd.id :
                        #同一个交叉点
                        pass
                    else :
                        logging.error('交叉点=({},{})不是最新位置，最后一个有效交叉=({},{})'.format(cd.id, cd.cross, last_cd.id, last_cd.cross))

                if index == len(closes) - 1 and not HISTORY :        #最新的K线上有交叉
                    lh_cross = self.get_last_handled_cross()
                    if lh_cross is None or lh_cross.timestamp < dates[index] :   #这个交叉点没有处理过
                        lh_time_str = utility.timestamp_to_string(lh_cross.timestamp) if lh_cross is not None else '无'
                        logging.info('发现交叉点={}, 日期={}, 配置的最后处理交叉点={}...'.format(cross, 
                            dates_str[index], lh_time_str))
                        status, infos = self.__process_cross(cross, index)
                        logging.info('出现新的MACD交叉点={}, 日期={}, 索引={}, 处理结果={}.'.format(cross, dates_str[index], index, status))
                        if status == base_item.TRADE_STATUS.BUY or status == base_item.TRADE_STATUS.SELL :
                            assert(infos is not None)
                            logging.info('交叉点={}完成买卖，code={}, 更新配置文件。'.format(cross, infos['local_code']))
                            self.__config.update_hc(dates[index], cross.value, status.value)
                            cd.update_status(status)
                        elif infos['local_code'] == -100 :
                            logging.info('交叉点={}因余额不足放弃买卖，更新配置文件。'.format(cross))
                            self.__config.update_hc(dates[index], cross.value, status.value)
                            cd.update_status(base_item.TRADE_STATUS.HANDLED)
                        else :
                            logging.warning('交叉点={}处理失败，交易状态={}, local_code={}, local_msg={}。'.format(cross,
                                status.value, infos['local_code'], infos['local_msg']))
                            cd.update_status(status)
                    elif lh_cross.timestamp == dates[index] :
                        logging.info('K线交叉点={}已处理，索引={}, 时间={}。'.format(cross, index, dates_str[index]))
                        status = base_item.TRADE_STATUS.HANDLED
                        cd.update_status(status)
                    else :
                        logging.error('交叉点={}，索引={}, 时间={}，小于最后处理时间={}.'.format(cross, index, dates_str[index],
                            utility.timestamp_to_string(lh_cross.timestamp)))
                        assert(False)
                else :
                    #assert(False)
                    cross = base_item.MACD_CROSS.NONE
                    pass
        #弹出多余的交叉点
        if MACD_processor.MAX_CROSS_COUNT > 0 and len(self.crosses) > MACD_processor.MAX_CROSS_COUNT :
                self.crosses = self.crosses[-self.MAX_CROSS_COUNT:]
                logging.info('交叉点数量超过{}，弹出多余的交叉点，剩余数量={}.'.format(MACD_processor.MAX_CROSS_COUNT, len(self.crosses)))

        if len(self.crosses) > 0 :
            msgs = self.print_cross(asascend=True)
            for msg in msgs:
                logging.info(msg)

        if self.DAILY_LOG :
            #如当天发现交叉，则cash和hold为处理交叉后的数据
            #prices = {base_item.trade_symbol.BTCUSDT: closes[-1], }
            profit = self.account.cash + self.account.get_amount(self.symbol) * closes[-1]
            self.dailies.loc[len(self.dailies)] = [dates[-1], self.account.cash, self.account.get_amount(self.symbol), profit]
        return cross, status, time_i, infos


    def print_cross(self, asascend : bool = True) -> list[str]:
        #获取self.crosses中的金叉列表和死叉列表
        logs = list[str]()
        all_gold = all_dead = 0
        gold_updown = dead_updown = 0
        for cd in self.crosses:
            time_str = utility.timestamp_to_string(cd.timestamp, ONLY_DATE=True)
            if cd.cross.is_golden():
                all_gold += 1
                if cd.cross.is_updown() :
                    gold_updown += 1
                    logs.append('金叉：发现跨0轴金叉（忽略），索引={}，时间={}，状态={}。'.format(cd.id, time_str, cd.status.value))
                else :
                    logs.append('金叉：发现金叉，索引={}，时间={}，状态={}。'.format(cd.id, time_str, cd.status.value))
            elif cd.cross.is_dead():
                all_dead += 1
                if cd.cross.is_updown() :
                    dead_updown += 1
                    logs.append('死叉：发现跨0轴死叉（忽略），索引={}，时间={}，状态={}。'.format(cd.id, time_str, cd.status.value))
                else :
                    logs.append('死叉：发现死叉，索引={}，时间={}，状态={}。'.format(cd.id, time_str, cd.status.value))
        if not asascend :
            logs.reverse()
        info = '交叉点总数={}，其中金叉总数={}, 0轴金叉（忽略）={}, 其中死叉总数={}, 0轴死叉（忽略）={}.'.format(
            len(self.crosses), all_gold, gold_updown, all_dead, dead_updown)
        logs.append(info)
        return logs
    
def calc_profit(year_begin : int, year_end : int, interval : base_item.kline_interval) -> list:
    INIT_CASH = 10000
    account = base_item.part_account('13', 'thiefox')
    account.deposit(INIT_CASH)
    symbol = base_item.trade_symbol.BTCUSDT
    processor = MACD_processor(symbol)
    processor.set_account(account)
    processor.open_daily_log(True)
    klines = data_loader.load_klines_years(processor.symbol, year_begin, year_end, interval)
    logging.info('共载入的K线数据记录={}'.format(len(klines)))
    if len(klines) == 0:
        return list()
    dates = [utility.timestamp_to_string(kline[0], ONLY_DATE=True) for kline in klines]
    #把dates转换为numpy数组
    dates = np.array(dates)
    
    gold_cross = list()
    dead_cross = list()
    operations = list()     #操作记录
    INIT_PRICE = round(float(klines[0][1]), 2)  #以开盘价作为初始价格
    for i in range(len(klines)):
        logging.debug('处理第{}条K线数据，日期={}...'.format(i, dates[i]))
        kline = klines[i]
        result = processor.update_kline(kline)
        if result[0].is_golden() :
            logging.info('日期={}，第{}条K线发现金叉。'.format(dates[i], i))
            gold_cross.append(i)
            operations.append((i, result[0], result[1], result[2]))
        elif result[0].is_dead():
            logging.info('日期={}，第{}条K线发现死叉。'.format(dates[i], i))
            dead_cross.append(i)
            operations.append((i, result[0], result[1], result[2]))
        else :
            pass

    last_price = float(klines[-1][4])
    amount = processor.account.get_amount(symbol)
    if amount > 0 :
        logging.info('最后一天卖出操作，日期={}, 价格={}, 数量={:.4f}...'.format(dates[-1], last_price, amount))
        processor.sell_all(last_price)
        operations.append((len(klines)-1), base_item.MACD_CROSS.NONE, base_item.TRADE_STATUS.SELL)

    logging.info('起始资金={}, 起始币数量={}, 起始币价格={:.2f}, 结束币价格={:.2f}'.format(INIT_CASH, 0, INIT_PRICE, last_price))
    logging.info('MACD最终资金={}, 盈亏={}, 收益率={:.2f}%'.format(account.cash, account.cash - INIT_CASH,
        fin_util.calc_scale(INIT_CASH, account.cash)*100))
    logging.info('---processor处理器打印金叉死叉---...')
    processor.print_cross()
    logging.info('---外部环境打印金叉死叉---...')
    logging.info('金叉出现次数={}, 金叉列表={}.'.format(len(gold_cross), ', '.join([str(x) for x in gold_cross])))
    logging.info('死叉出现次数={}, 死叉列表={}.'.format(len(dead_cross), ', '.join([str(x) for x in dead_cross])))
    logging.info('---打印买卖操作---')
    for op in operations:
        #date_str = datetime.strptime(dates[op[0]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        date_str = dates[op[0]]
        daily = processor.dailies.loc[op[0]]
        price = float(klines[op[0]][4])
        if op[1].is_golden():
            if op[2] == base_item.TRADE_STATUS.BUY:
                logging.info('金叉买入，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            elif op[2] == base_item.TRADE_STATUS.IGNORE or op[2] == base_item.TRADE_STATUS.HANDLED:
                logging.info('金叉忽略，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                logging.error('金叉操作错误，i={}，日期={}, 操作={}'.format(op[0], date_str, op[2]))
                #assert(False)
                pass
        elif op[1].is_dead() :
            if op[2] == base_item.TRADE_STATUS.SELL:
                logging.info('死叉卖出，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            elif op[2] == base_item.TRADE_STATUS.IGNORE or op[2] == base_item.TRADE_STATUS.HANDLED:
                logging.info('死叉忽略，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                logging.error('死叉操作错误，i={}，日期={}, 操作={}'.format(op[0], date_str, op[2]))
                #assert(False)
                pass
        else :
            if op[2] == base_item.TRADE_STATUS.SELL:
                logging.info('重要：最后一天卖出，i={}，日期={}，价格={:.2f}，数量={}，资金={}，总值={:.2f}'.format(op[0], date_str, price,
                    daily['hold'], daily['cash'], daily['profit']))
            else :
                logging.error('最后一天卖出操作错误，i={}，日期={}, 操作码={}'.format(op[0], date_str, op[2]))
                assert(False)
    logging.info('---打印买卖操作结束---')

    profits = list()
    if len(processor.dailies) > 0 :
        profits = processor.dailies['profit'].tolist()
        pf = fin_util.prices_info(profits)
        info = pf.find_max_trend(INCREMENT=False)
        logging.info('统计最大连续回撤返回={:.2f}%, bi={}, ei={}'.format(info[0]*100, info[1], info[2]-1))
        if info[1] >= 0 and info[2] > info[1]:
            begin_str = dates[info[1]]
            end_str = dates[info[2]-1]
            logging.info('MACD最大连续回撤={:.2f}%, bi={}, ei={}'.format(info[0]*100, begin_str, end_str))
            before = round(profits[info[1]-1], 2)
            after = round(profits[info[2]], 2)
            logging.info('MACD模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
            if not pf.check_order(info[1], info[2], ASCENDING=False):
                logging.error('最大连续回撤区间不是降序排列！')
                #pf.print(info[1], info[2])
        else :
            logging.error('未取到最大回撤，统计周期={}。'.format(len(profits)))

        holds = processor.dailies['hold'].tolist()
        info = fin_util.calc_hold_days(holds)
        logging.info('MACD模式-总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    return profits

def _test() :
    print("MACD process Start...")
    log_adapter.log_to_console('MACD_process', level = logging.DEBUG)
    #log_adapter.log_to_file('MACD_process', level= logging.DEBUG)
    
    su = base_item.save_unit(base_item.kline_interval.d1)
    #calc_profit(2017, 2025, base_item.kline_interval.d1)
    draw_profit.draw_kline_and_profit(2017, 2025, su, calc_profit)

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