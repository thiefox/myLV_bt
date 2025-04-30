from __future__ import annotations

import sys
import os
import logging
from datetime import datetime
import time

import pandas as pd
import numpy as np

from com_utils import utility
from com_utils import log_adapter
from com_utils import config

import base_item
import kline_spider
import data_loader
import fin_util
import draw_profit
import mail_template
import binance_spot_wrap
from processor_template import processor_T, KLINE_PROCESS, UPDATE_KLINE_RESULT, UPDATE_TRADE_RESULT

DEFAULT_BACK_COUNT = 200

class CROSS_DESC():
    MAX_FAILED = 3
    def __init__(self, id : int, cross : base_item.MACD_CROSS, timestamp : int, 
            status : base_item.TRADE_STATUS = base_item.TRADE_STATUS.NONE) -> None:
        self.__id = id                  #交叉点的索引
        self.__cross = cross            #交叉类型
        self.__status = status          #交易状态
        self.__timestamp = timestamp    #交叉点所在K线的开始时间戳
        self.__fails = 0                #交叉点处理失败次数
        return
    @property
    def id(self) -> int:
        return self.__id
    @property
    def cross(self) -> base_item.MACD_CROSS:
        return self.__cross
    @cross.setter
    def cross(self, cross : base_item.MACD_CROSS) -> None:
        self.__cross = cross
        return
    @property
    def status(self) -> base_item.TRADE_STATUS:
        return self.__status
    @status.setter
    def status(self, ts : base_item.TRADE_STATUS) -> None:
        if ts == base_item.TRADE_STATUS.FAILED :
            self.__status = ts
            self.__add_fails()
        elif ts == base_item.TRADE_STATUS.BUY or ts == base_item.TRADE_STATUS.SELL :
            self.__status = ts
            self.__fails = 0
        elif ts == base_item.TRADE_STATUS.HANDLED :
            self.__status = ts
            pass
        elif ts == base_item.TRADE_STATUS.IGNORE :
            if self.status == base_item.TRADE_STATUS.NONE :
                self.__status = ts
            else :
                logging.error('交叉点={}，状态={}，不能设置为IGNORE。'.format(self.cross, self.status))
                assert(False)
            pass
        elif ts == base_item.TRADE_STATUS.NONE :
            pass
        return
    @property
    def timestamp(self) -> int:
        return self.__timestamp
    @property
    def valid(self) -> bool:
        return self.__timestamp > 0 and self.cross.valid()
    def update_from(self, other : CROSS_DESC):
        assert(other.timestamp > 0 and self.timestamp == other.timestamp)
        assert(other.cross.valid())        
        logging.info('更新CD，时间戳={}，cross={}，status={}。更新为cross={}，status={}。'.format(utility.timestamp_to_string(self.timestamp),
            self.cross.value, self.status.value, other.cross.value, other.status.value))
        self.cross = other.cross
        self.status = other.status
        return
    @property
    def key(self) -> str:
        #return '{}+{}'.format(self.__timestamp, self.__cross.value)
        return '{}'.format(self.timestamp)
    def reach_max_fails(self) -> bool :
        return self.__fails >= CROSS_DESC.MAX_FAILED
    def __add_fails(self) -> None:
        self.__fails += 1
        return

MAX_CROSS_COUNT = 100
#WINDOW_LENGTH=0表示不限制K线数量
#114天结果和无限一样，114为最小临界窗口
MIN_WINDOW_LEN = 114
DEF_WINDOW_LEN = 120

class MACD_processor(processor_T):
    SLOW_PERIOD = 26
    FAST_PERIOD = 12
    SIGNAL_PERIOD = 9
    TRADE_BUY_REASON_GOLDEN = '金叉买入'
    TRADE_SELL_REASON_DEAD = '死叉卖出'
    def __init__(self, symbol : base_item.trade_symbol, su : base_item.save_unit, cfg : config.Config) -> None:
        super().__init__(symbol, su, cfg, DEF_WINDOW_LEN)
        super()._set_name('MACD_processor')
        self._master = True
        #交叉点列表，索引/交叉点/交易状态/时间戳
        #记录的是出现的交叉点，而不是处理的交叉点，后者是前者的子集
        #重要：调整为已固定K线的交叉点列表，当前活动中K线产生的交叉点不放入        
        #self.crosses = list[CROSS_DESC]()
        self.__crosses = dict[str, CROSS_DESC]()
        return    
    def _update_cross_desc(self, cd : CROSS_DESC) -> None:
        if cd.key not in self.__crosses :
            logging.info('添加交叉点，时间={}，类型={}，状态={}。'.format(utility.timestamp_to_string(cd.timestamp), cd.cross.value, cd.status.value))
            self.__crosses[cd.key] = cd
            if len(self.__crosses) > MAX_CROSS_COUNT :
                lst = list(self.__crosses.values())
                lst.sort(key=lambda x: x.timestamp, reverse=True)
                self.__crosses = dict()
                for i in range(MAX_CROSS_COUNT / 2) :       #保留一半的交叉点
                    self.__crosses[lst[i].key] = lst[i]
                logging.info('交叉点数量超过{}，弹出多余的交叉点，剩余数量={}.'.format(MAX_CROSS_COUNT, len(self.__crosses)))
        else :
            logging.info('更新交叉点，时间={}，类型={}，状态={}。'.format(utility.timestamp_to_string(cd.timestamp), cd.cross.value, cd.status.value))
            self.__crosses[cd.key].update_from(cd)
        return
    def _reach_max_fail(self, cd : CROSS_DESC) -> bool:
        if cd.key in self.__crosses :
            return self.__crosses[cd.key].reach_max_fails()
        else :
            return False
            
    def _prepare_online(self) -> int:
        begin = int(datetime.now().timestamp()) * 1000
        offset = super().interval.calc_offset(DEFAULT_BACK_COUNT, begin)
        assert(offset > 0)
        logging.info('开始在线获取{}条历史K线数据，开始时间戳={}'.format(DEFAULT_BACK_COUNT, utility.timestamp_to_string(offset)))
        klines = kline_spider.get_klines(super().symbol, super().interval, offset, DEFAULT_BACK_COUNT)
        if len(klines) == 0:
            logging.critical('在线获取历史K线数据失败。')
            return processor_T.PREPARE_FAILED
        logging.info('在线初始化共获取到K线数据记录={}，BACK_CN={}'.format(len(klines), DEFAULT_BACK_COUNT))
        if len(klines) < DEFAULT_BACK_COUNT:
            logging.critical('在线获取到的历史K线数据记录数={}，低于阈值={}。'.format(len(klines), DEFAULT_BACK_COUNT))
            return processor_T.PREPARE_FAILED
        elif len(klines) > DEFAULT_BACK_COUNT :
            logging.critical('在线获取到的历史K线数据记录数={}，超过BACK_CN={}。'.format(len(klines), DEFAULT_BACK_COUNT))
            return processor_T.PREPARE_FAILED
        first_begin = int(klines[0][0])
        last_begin = int(klines[-1][0])
        logging.info('获取K线数据完成，第一条K线的开始时间={}，最后一条K线的开始时间={}。'.format(
            utility.timestamp_to_string(first_begin), utility.timestamp_to_string(last_begin)))
        count = self.init_history(klines)
        logging.info('在线初始化历史数据结果={}。'.format(count))
        assert(count <= super().K_MAX)
        utr, infos = self.__process_ex(HISTORY=True)  #处理所有交叉点
        logging.info('交叉点处理结果={}，infos={}'.format(utr, infos))
        cd = self.get_last_handled_cross()
        if cd is not None :
            self._update_cross_desc(cd)
            if not cd.status.success() :
                logging.critical('异常：最后处理的交叉点={}，状态={}，初始化失败。'.format(utility.timestamp_to_string(cd.timestamp), cd.status.value))
                self._controled = False
                return processor_T.PREPARE_FAILED
            assert(cd.status.success())
            self._controled = True
            return processor_T.PREPARE_CONTROLED
        else :
            self._controled = False
            return processor_T.PREPARE_RELEASED
    def _prepare_offline(self, END : int) -> bool:
        if END == 0 :
            END = super().interval.get_K_begin()
        offset = super().interval.calc_offset(DEFAULT_BACK_COUNT, END)
        assert(offset > 0)
        logging.info('开始离线获取{}条历史K线数据，开始时间戳={}，结束时间戳={}'.format(DEFAULT_BACK_COUNT, 
            utility.timestamp_to_string(offset), utility.timestamp_to_string(END)))
        klines = data_loader.load_klines_range(super().symbol, super().su,
            utility.timestamp_to_datetime(offset), utility.timestamp_to_datetime(END))
        if len(klines) == 0:
            logging.critical('离线获取历史K线数据失败。')
            return processor_T.PREPARE_FAILED
        logging.info('离线初始化共获取到K线数据记录={}，BACK_CN={}'.format(len(klines), DEFAULT_BACK_COUNT))
        if len(klines) < DEFAULT_BACK_COUNT:
            logging.critical('离线获取到的历史K线数据记录数={}，低于阈值={}。'.format(len(klines), DEFAULT_BACK_COUNT))
            return processor_T.PREPARE_FAILED
        count = self.init_history(klines)
        logging.info('离线初始化历史数据结果={}。'.format(count))
        assert(count <= super().K_MAX)
        utr, infos = self.__process_ex(HISTORY=True)  #处理所有交叉点
        logging.info('交叉点处理结果={}，infos={}'.format(utr, infos))
        cd = self.get_last_handled_cross()
        if cd is not None :
            self._update_cross_desc(cd)
            if not cd.status.success() :
                logging.critical('异常：最后处理的交叉点={}，状态={}，初始化失败。'.format(utility.timestamp_to_string(cd.timestamp), cd.status.value))
                self._controled = False
                return processor_T.PREPARE_FAILED
            assert(cd.status.success())
            self._controled = True
            return processor_T.PREPARE_CONTROLED
        else :
            self._controled = False
            return processor_T.PREPARE_RELEASED

    #取得最后一个处理过的交叉点，从配置文件中读取
    def get_last_handled_cross(self) -> CROSS_DESC:
        hc_info = super().config.get_hc()
        if hc_info[0] > 0 :
            timeinfo = hc_info[0]
            cross = base_item.MACD_CROSS(hc_info[1])
            if hc_info[2] == '' :
                status = base_item.TRADE_STATUS.IGNORE
            else :
                status = base_item.TRADE_STATUS(hc_info[2])
            logging.critical('配置文件中发现最后处理交叉点={}，交叉点类型={}，处理状态={}。'.format(utility.timestamp_to_string(timeinfo),
                cross.value, status.value))
            return CROSS_DESC(-1, cross, timeinfo, status)
        else :
            logging.critical('配置文件中没有发现交叉点信息。')
            return None

    #取得最后一个交叉点
    def get_last_cross(self) -> CROSS_DESC :
        ts = 0
        key = None
        for _key in self.__crosses.keys() :
            cd = self.__crosses[_key]
            if cd.timestamp > ts :
                ts = cd.timestamp
                key = _key
        if key is not None :
            return self.__crosses[key]
        else :
            return None

    #初始化历史K线数据
    #返回槽中的K线数量
    def init_history(self, klines : list) -> int:
        return super().init_klines(klines)

    #(实时)更新一条K线数据
    def update_kline(self, kline : list, interval : base_item.kline_interval) -> tuple[UPDATE_KLINE_RESULT, dict]:
        before_last = self.get_time_begin(-1)
        begin_time = int(kline[0])
        ukr, infos = super().update_kline(kline, interval)
        if self._controled :
            ukr.controled()
        else :
            ukr.released()
        logging.info('更新K线处理结果={}，infos={}'.format(ukr, infos))
        after_last = self.get_time_begin(-1)
        if ukr.is_K_added() :
            logging.info('新增K线={}，前一条K线已固化，before_last={}, after_last={}, 开始处理前一条K线的交叉点...'.format(
                utility.timestamp_to_string(begin_time), utility.timestamp_to_string(before_last), utility.timestamp_to_string(after_last)))
            assert(before_last + interval.get_interval_seconds() * 1000 == after_last)
            ukr.trade, infos = self.__process_ex(HISTORY=False)  #处理交叉点
            if ukr.trade.success() :
                if ukr.trade.status == base_item.TRADE_STATUS.BUY : 
                    ukr.controled()
                elif ukr.trade.status == base_item.TRADE_STATUS.SELL :
                    ukr.released()
                else :
                    assert(False)
            elif ukr.trade.failed() :
                ukr.controled() 
                
            logging.info('交叉点处理结果={}，infos={}'.format(ukr, infos))
        elif ukr.is_K_updated() :
            assert(before_last == after_last)
            logging.info('当前活跃K线-{}更新，不处理。'.format(utility.timestamp_to_string(begin_time)))
        elif ukr.is_K_error() :
            logging.error('异常：时间戳不连续，更新K线数据失败。')
        else :
            assert(False)
        return ukr, infos
    def daily_report(self) -> list[str] :
        report = list()
        report.extend(super().daily_report())
        last_cross = self.get_last_cross()
        if last_cross is not None :
            report.append('最后出现的交叉点时间={}，类型={}，状态={}。\n'.format(utility.timestamp_to_string(last_cross.timestamp),
                last_cross.cross.value, last_cross.status.value))
        last_handled = self.get_last_handled_cross()
        if last_handled is not None :
            report.append('最后处理的交叉点时间={}，类型={}，状态={}。\n'.format(utility.timestamp_to_string(last_handled.timestamp),
                last_handled.cross.value, last_handled.status.value))
        crosses_info = self.print_cross()
        if len(crosses_info) > 0 :
            report.append('---交叉点列表---')
            for cross_info in crosses_info :
                report.append('------{}'.format(cross_info))
        return report

    #处理MACD交叉
    #index: 交叉发生的K线索引
    def __process_cross(self, cross : base_item.MACD_CROSS, index : int) -> tuple[UPDATE_TRADE_RESULT, dict]:
        utr = UPDATE_TRADE_RESULT()
        infos = None
        logging.debug('打印K线数据, input index={}...'.format(index))
        index = self._klines.index[index]
        
        logging.debug('klines总数={}, klines重置索引={}, 交叉={}'.format(super().K_len, index, cross))
        #print('内部索引={}, 外部索引={}, 交叉={}'.format(ni, index, cross))
        #date_str = utility.timestamp_to_string(self.__klines[index, 'date_b'], ONLY_DATE=True)
        date_str = utility.timestamp_to_string(int(self._klines.loc[index, 'date_b']), ONLY_DATE=True)
        if cross.is_golden() and not cross.is_updown() : #金叉
            buy_price = self._klines.loc[index, 'close']
            logging.info('重要：日期={}，出现金叉，币价={}，尝试买入操作...'.format(date_str, round(buy_price, 2)))
            utr.begin_trade(base_item.TRADE_STATUS.BUY, self.TRADE_BUY_REASON_GOLDEN)
            infos = super().buy_market()
            if infos['local_code'] == 0 :
                utr.end_trade(base_item.TRADE_STATUS.BUY, UPDATE_TRADE_RESULT.SUCCESS)
            else :
                if infos['local_code'] == -100 :        #余额不足导致无法买入
                    utr.end_trade(base_item.TRADE_STATUS.FAILED, '买入失败，原因：'.format(UPDATE_TRADE_RESULT.INSUFFICIENT_BALANCE))
                    logging.info('买入失败，原因：余额不足。')
                else :
                    utr.end_trade(base_item.TRADE_STATUS.FAILED, '买入失败，local_code={}'.format(infos['local_code']))

        elif cross.is_dead() and not cross.is_updown() : #死叉
            sell_price = self._klines.loc[index, 'close']
            logging.info('重要：日期={}，出现死叉，币价={}，尝试卖出操作...'.format(date_str, round(sell_price, 2)))
            utr.begin_trade(base_item.TRADE_STATUS.SELL, self.TRADE_SELL_REASON_DEAD)
            infos = super().sell_martket()
            if infos['local_code'] == 0 :
                utr.end_trade(base_item.TRADE_STATUS.SELL, UPDATE_TRADE_RESULT.SUCCESS)
            else :
                if infos['local_code'] == -100 :        #余币不足导致无法卖出
                    utr.end_trade(base_item.TRADE_STATUS.FAILED, '卖出失败，原因：'.format(UPDATE_TRADE_RESULT.INSUFFICIENT_CURRENCY))
                    logging.info('卖出失败，原因：余币不足。')
                else :
                    utr.end_trade(base_item.TRADE_STATUS.FAILED, '卖出失败，local_code={}'.format(infos['local_code']))
        else :
            pass
        return utr, infos
    
    #如HISTORY=True，则检测和打印数据列表上的所有交叉点，不处理。如HISTORY=False，则检测数据列表的倒数第二条是否有交叉点，有则处理。
    def __process_ex(self, HISTORY : bool = False) -> tuple[UPDATE_TRADE_RESULT, dict]:
        utr = UPDATE_TRADE_RESULT()
        infos = None
        #cross = base_item.MACD_CROSS.NONE
        #status = base_item.TRADE_STATUS.IGNORE
        #time_i = int(0)

        ONE_DAY_MILLSECONDS = 24 * 60 * 60 * 1000
        #获取收盘价列表
        assert(super().K_len > 0)
        #获取最后一条K线的收盘价
        #close = self.__klines.loc[len(self.__klines)-1, 'close']  #最后一条K线的收盘价
        '''
        if HISTORY :
            closes = self._klines['close'].tolist()
            dates = self._klines['date_b'].tolist()
        else :
        '''
        last_begin = self.get_time_begin(-1)  #最后一条K线的开始时间戳
        LAST_2_BEGIN = self.get_time_begin(-2)  #倒数第二条K线的开始时间戳
        time_i = LAST_2_BEGIN
        now = int(datetime.now().timestamp()) * 1000
        #last_2_fixed = False
        #检测当前时间是否已过格林威治时间的23:59:59
        logging.info('当前时间={}，倒数第二条K线的开始时间={}。最后的K线开始时间={}。'.format(utility.timestamp_to_string(now),
            utility.timestamp_to_string(LAST_2_BEGIN), utility.timestamp_to_string(last_begin)))
        #if now  >= LAST_2_BEGIN + ONE_DAY_MILLSECONDS and now < LAST_2_BEGIN + ONE_DAY_MILLSECONDS * 2 :
        if now  >= LAST_2_BEGIN + ONE_DAY_MILLSECONDS :
            logging.critical('倒数第二条K线({})已固化。HISTORY={}'.format(utility.timestamp_to_string(LAST_2_BEGIN), HISTORY))
            #last_2_fixed = True
        else :
            logging.info('倒数第二条K线({})未固化，忽略，直接返回。HISTORY={}'.format(utility.timestamp_to_string(LAST_2_BEGIN), HISTORY))
            logging.critical('当前时间={}({})，倒数第二条K线的开始时间={}({})。'.format(utility.timestamp_to_string(now), now, 
                utility.timestamp_to_string(LAST_2_BEGIN), LAST_2_BEGIN))
            return utr, infos

        ks = self.get_kline_status(LAST_2_BEGIN)
        if ks.blank():
            pass
        elif ks.processing() :
            logging.error('K线={}的处理状态为processing，当前不支持。'.format(utility.timestamp_to_string(LAST_2_BEGIN)))
            assert(False)
            pass
        elif ks.final() :
            logging.critical('K线={}的处理状态={}已固化，不处理，直接返回。'.format(utility.timestamp_to_string(LAST_2_BEGIN), ks.value))
            return utr, infos

        #选取self._klines中的从头部到尾部第二条K线的收盘价，最后一条K线是活跃K线，不能参与计算
        closes = self._klines.loc[0:len(self._klines)-2, 'close'].tolist()
        dates = self._klines.loc[0:len(self._klines)-2, 'date_b'].tolist()
        logging.info('process_ex处理，HISTORY={}，当前K线数量={}，收盘价列表长度={}。'.format(HISTORY, super().K_len, len(closes)))

        dates = [int(i) for i in dates]
        dates_str = [utility.timestamp_to_string(int(i), ONLY_DATE=True) for i in dates]
        logging.info('进入处理的倒数二条K线的开盘时间={}，收盘价={}。'.format(dates_str[-1], closes[-1]))
        #print('closes={}'.format(closes))
        #last_date_end = utility.timestamp_to_string(int(self._klines.loc[super().K_len-1, 'date_e']))
        #print('当前K线数量，方法1={}，方法2={}'.format(len(closes), len(self.__klines)))
        #print('最后一条K线，开始时间={}, 结束时间={}，开盘价={}, 收盘价={}'.format(dates_str[-1], last_date_end, opens[-1], closes[-1]))
        if len(closes) > 0 :
            assert(isinstance(closes[0], float))
        pi = fin_util.prices_info(closes)
        #计算MACD
        macd, signal, hist = pi.calculate_macd()
        crossovers = fin_util.find_macd_crossovers(macd, signal, hist, ONLY_LAST=not HISTORY)

        logging.info('当前K线找到{}个MACD交叉点, self.crosses中已有数量={}。'.format(len(crossovers), len(self.__crosses)))

        if len(crossovers) > 0 :
            logging.info('共找到{}个交叉点，HISTORY={}'.format(len(crossovers), HISTORY))
            if len(crossovers) > 1 :
                for cross in crossovers[:-1]:
                    index : int = cross[0]
                    cross : base_item.MACD_CROSS = cross[1]
                    time_i = dates[index]
                    cd = CROSS_DESC(index, cross, time_i)
                    self._update_cross_desc(cd)

            index : int = crossovers[-1][0]
            cross : base_item.MACD_CROSS = crossovers[-1][1]
            timeinfo = int(self._klines.loc[index, 'date_b'])
            time_i = dates[index]
            if timeinfo != time_i :
                logging.error('时间戳不一致，K线时间={}({})，交叉点时间={}({})。'.format(utility.timestamp_to_string(timeinfo), timeinfo, 
                    utility.timestamp_to_string(time_i), time_i))
            assert(timeinfo == time_i)
            logging.critical('找到的最后一个交叉点信息：索引={}，时间={}，交叉类型={}。'.format(index, dates_str[index], cross))
            cd = CROSS_DESC(index, cross, time_i)
            if not HISTORY :
                assert(len(crossovers) == 1)
                assert(index == len(closes) - 1)
            if not cross.is_updown() :  #非0轴上下的交叉
                oi = self._klines.index[index]
                if len(self.__crosses) == 0 :
                    self._update_cross_desc(cd)
                    logging.info('列表为空，直接加入。索引={}，时间={}，交叉类型={}。'.format(index, dates_str[index], cross))
                else :
                    last_cd = self.get_last_cross()
                    if cd.id > last_cd.id :
                        if cross.is_opposite(last_cd.cross) :  #交叉点相反
                            self._update_cross_desc(cd)
                            logging.info('添加交叉点，索引={}，时间={}，交叉类型={}。总数={}'.format(index, dates_str[index], cross, len(self.__crosses)))
                        else :
                            logging.critical('当前交叉点=({},{})和最后一个交叉点=({},{})相同类型.'.format(cd.id, cd.cross, last_cd.id, last_cd.cross))
                    elif cd.id == last_cd.id :
                        #同一个交叉点
                        logging.info('当前交叉点=({},{})和最后一个交叉点=({},{})相同.'.format(cd.id, cd.cross, last_cd.id, last_cd.cross))
                        pass
                    else :
                        logging.error('当前交叉点=({},{})不是最新位置，最后一个有效交叉=({},{})'.format(cd.id, cd.cross, last_cd.id, last_cd.cross))

                if index == len(closes) - 1 and not HISTORY :        #最后一条K线（可能为实时的最后一条，也可能为固化的倒数第二条，看前面处理）上有交叉
                    lh_cross = self.get_last_handled_cross()
                    if lh_cross is None or lh_cross.timestamp < dates[index] :   #这个交叉点没有处理过
                        lh_time_str = utility.timestamp_to_string(lh_cross.timestamp) if lh_cross is not None else '无'
                        logging.info('发现交叉点={}, 日期={}, 配置的最后处理交叉点={}...'.format(cross, 
                            dates_str[index], lh_time_str))
                        if not self._reach_max_fail(cd) :
                            utr, infos = self.__process_cross(cross, index)
                            logging.info('出现新的MACD交叉点={}, 日期={}, 索引={}, 处理结果={}.'.format(cross, dates_str[index], index, status))
                            if utr.status.success() :
                                assert(infos is not None)
                                logging.info('交叉点={}完成买卖，code={}, 更新配置文件。'.format(cross, infos['local_code']))
                                self._config.update_hc(dates[index], cross.value, utr.status.value)
                                cd.status = utr.status
                            elif utr.status.failed() :
                                logging.warning('交叉点={}处理失败，交易状态={}, local_code={}, local_msg={}。'.format(cross,
                                    utr.status.value, infos['local_code'], infos['local_msg']))
                                self._config.update_hc(dates[index], cross.value, utr.status.value)
                                #cd.status = base_item.TRADE_STATUS.HANDLED
                                cd.status = utr.status
                                self._update_cross_desc(cd)
                            elif utr.status.ignored() :
                                logging.warning('交叉点={}处理失败，交易状态={}, local_code={}, local_msg={}。'.format(cross,
                                    utr.status.value, infos['local_code'], infos['local_msg']))
                                cd.status = utr.status
                                self._update_cross_desc(cd)
                            else :
                                logging.error('交叉点={}处理异常，交易状态={}。'.format(cross, utr.status.value))
                                assert(False)
                        else :
                            logging.info('交叉点={}超过最大失败次数，不再处理。'.format(cross))
                            #cd.update_status(base_item.TRADE_STATUS.IGNORE)
                    elif lh_cross.timestamp == dates[index] :
                        logging.info('K线交叉点={}已处理过，索引={}, 时间={}。'.format(cross, index, dates_str[index]))
                        utr.end_trade(base_item.TRADE_STATUS.HANDLED, '该交叉点已处理过')
                        #cd.update_status(status)
                    else :
                        logging.error('交叉点={}，索引={}, 时间={}，小于最后处理时间={}.'.format(cross, index, dates_str[index],
                            utility.timestamp_to_string(lh_cross.timestamp)))
                        assert(False)
                else :
                    #assert(False)
                    #cross = base_item.MACD_CROSS.NONE
                    pass
            else :
                logging.info('当前交叉点={}，索引={}，时间={}，该交叉点为0轴上下交叉，忽略处理。'.format(cross, index, dates_str[index]))


        if len(self.__crosses) > 0 :
            msgs = self.print_cross(asascend=True)
            for msg in msgs:
                logging.info(msg)
        if not HISTORY :
            self.kline_status_finish(LAST_2_BEGIN, KLINE_PROCESS.FINISH, extends=None)
            logging.critical('K线={}的处理状态固化完成。'.format(utility.timestamp_to_string(LAST_2_BEGIN)))            
        #return cross, status, time_i, infos
        return utr, infos

    def print_cross(self, asascend : bool = True) -> list[str]:
        #获取self.crosses中的金叉列表和死叉列表
        logs = list[str]()
        all_gold = all_dead = 0
        gold_updown = dead_updown = 0
        for cd in self.__crosses.values():
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
            len(self.__crosses), all_gold, gold_updown, all_dead, dead_updown)
        logs.append(info)
        return logs
    


