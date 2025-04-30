import logging
import sys
import pandas as pd
import numpy as np
from enum import Enum
from datetime import datetime, timedelta
from com_utils import config
from com_utils import utility

import base_item
import kline_spider
import data_loader
import binance_spot_wrap

DEFAULT_MAX_KLINES = 1000

class UPDATE_TRADE_RESULT(object):
    NETWORK_ERROR = '网络异常'
    INSUFFICIENT_BALANCE = '余额不足'
    INSUFFICIENT_CURRENCY = '余币不足'
    SUCCESS = '交易成功'
    def __init__(self) -> None:
        self.__trade_status = base_item.TRADE_STATUS.NONE     #交易状态, 具体原因参见trade_reason
        self.__trade_reason = ''        #触发交易的原因
        #self.__local_code = 0         # 0：交易成功。-100：余额/余币不足导致交易失败。-1：交易失败，具体原因参见local_msg。
        self.__trade_info = ''                # 如本地异常或取消交易，则记录失败原因。在trade_status为FAILED的前提下。
        return
    def __str__(self) -> str:
        return "status={}, reason={}, info={}".format(self.status, self.reason, self.info)
    @property
    def status(self) -> base_item.TRADE_STATUS:
        return self.__trade_status
    @property
    def reason(self) -> str:
        return self.__trade_reason
    @property
    def info(self) -> str:
        return self.__trade_info
    def success(self) -> bool:
        return self.status.success()
    def failed(self) -> bool:
        return self.status.failed()    
    def handled(self) -> bool:
        return self.status.handled()
    def ignored(self) -> bool:
        return self.status.ignored()    
    def happened(self) -> bool:
        return self.success() or self.failed()

    def begin_trade(self, status : base_item.TRADE_STATUS, reason : str) -> None:
        self.__trade_status = status
        self.__trade_reason = reason
    def end_trade(self, status : base_item.TRADE_STATUS, info : str) -> None:
        self.__trade_status = status
        self.__trade_info = info
    def get_trade(self) -> tuple[base_item.TRADE_STATUS, str, str]:
        return self.__trade_status, self.__trade_reason, self.__trade_info

class UPDATE_KLINE_RESULT(object):
    def __init__(self) -> None:
        self.__kline_result = 0       # 0表示已有K线的更新，1表示新增K线，-1表示K线不连续异常
        self.__control_mode = 0       # 0表示worker的返回，1表示master进入控制模式，2表示master放弃控制模式
        self.__trade_result = UPDATE_TRADE_RESULT()  # 交易结果
        return
    def __str__(self) -> str:
        return "KR={}, TR={}".format(self.KR, self.trade)
    @property
    def KR(self) -> int:
        return self.__kline_result
    @property
    def trade(self) -> UPDATE_TRADE_RESULT:
        return self.__trade_result
    @trade.setter
    def trade(self, result : UPDATE_TRADE_RESULT) -> None:
        self.__trade_result = result
    def controled(self):
        self.__control_mode = 1
    def released(self):
        self.__control_mode = 2
    def is_controled(self) -> bool:
        return self.__control_mode == 1
    def is_released(self) -> bool:
        return self.__control_mode == 2
    def is_worker(self) -> bool:
        return self.__control_mode == 0
    def is_master(self) -> bool:
        return self.__control_mode == 1 or self.__control_mode == 2
    def is_K_added(self) -> bool:
        return self.__kline_result == 1
    def is_K_updated(self) -> bool:
        return self.__kline_result == 0
    def is_K_error(self) -> bool:
        return self.__kline_result == -1
    def is_K_success(self) -> bool:
        return self.is_K_added() or self.is_K_updated()        
    def K_added(self) :
        self.__kline_result = 1
    def K_updated(self) :
        self.__kline_result = 0
    def K_errored(self) :
        self.__kline_result = -1


# K线处理状态
class KLINE_PROCESS(str, Enum):
    NONE = 'NONE'               # 未处理
    PROCESS = 'PROCESS'   # 处理中
    HALF = 'HALF'           # 半处理
    ERROR = 'ERROR'             # 处理错误
    FINISH = 'FINISH'       # 处理完成
    def final(self) -> bool:
        return self == KLINE_PROCESS.FINISH or self == KLINE_PROCESS.ERROR
    def processing(self) -> bool:
        return self == KLINE_PROCESS.PROCESS or self == KLINE_PROCESS.HALF
    def blank(self) -> bool:
        return self is None or self == KLINE_PROCESS.NONE

class kline_status(object):
    def __init__(self, status : KLINE_PROCESS = KLINE_PROCESS.NONE, extends = None) -> None:
        self._status = status
        self._extends = extends
    @property
    def status(self) -> KLINE_PROCESS:
        return self._status
    @status.setter
    def status(self, status : KLINE_PROCESS) -> None:
        self._status = status
    @property
    def extends(self) -> any:
        return self._extends

class kline_status_manager(object):
    MAX_COUNT = 1000
    def __init__(self) -> None:
        self._klines = dict[int, kline_status]()
    def found(self, timestamp : int) -> bool:
        return timestamp in self._klines
    def get_status(self, timestamp : int) -> KLINE_PROCESS:
        if self.found(timestamp) :
            return self._klines[timestamp].status
        else :
            logging.error('K线{}不存在，无法获取状态。'.format(utility.timestamp_to_string(timestamp)))
            return None
    def add(self, timestamp : int, status : KLINE_PROCESS, extends = None) -> kline_status:
        if self.found(timestamp) :
            logging.error('K线{}已存在，无法重复添加。'.format(utility.timestamp_to_string(timestamp)))
            return None
        else :
            ks = kline_status(status, extends)
            self._klines[timestamp] = ks
            self.__reduce()
            return ks
    def process(self, timestamp : int) -> kline_status:
        if self.found(timestamp) :
            ks = self._klines[timestamp]
            if ks.status.final() :
                logging.error('K线{}已完成处理，无法再次更新状态。'.format(utility.timestamp_to_string(timestamp)))
            else :
                ks.status = KLINE_PROCESS.PROCESS
            return ks
        else :
            logging.error('K线{}不存在，无法更新状态。'.format(utility.timestamp_to_string(timestamp)))
            return None
    def finish(self, timestamp : int) -> kline_status:
        if self.found(timestamp) :
            ks = self._klines[timestamp]
            if ks.status.final() :
                logging.error('K线{}已完成处理，无法再次更新状态。'.format(utility.timestamp_to_string(timestamp)))
            else :
                ks.status = KLINE_PROCESS.FINISH
            return ks
        else :
            logging.error('K线{}不存在，无法更新状态。'.format(utility.timestamp_to_string(timestamp)))
            return None

    def __reduce(self) -> None:
        if len(self._klines) <= self.MAX_COUNT :
            return
        logging.warning('K线状态数量{}超过最大限制{}，删除最早的K线状态。'.format(len(self._klines), self.MAX_COUNT))
        keys = list(self._klines.keys())
        keys.sort()
        logging.warning('缩身前第一条K线时间戳={}，最后一条K线时间戳={}。'.format(utility.timestamp_to_string(keys[0]), utility.timestamp_to_string(keys[-1])))
        for i in range(len(keys) - int(self.MAX_COUNT / 2)) :
            del self._klines[keys[i]]
        logging.warning('缩身后剩余K线状态数量={}。'.format(len(self._klines)))
        keys = list(self._klines.keys())
        keys.sort()
        logging.warning('缩身后第一条K线时间戳={}，最后一条K线时间戳={}。'.format(utility.timestamp_to_string(keys[0]), utility.timestamp_to_string(keys[-1])))
        return
            
class processor_T(object):
    PREPARE_FAILED = -1
    PREPARE_OK = 0
    PREPARE_CONTROLED = 1
    PREPARE_RELEASED = 2
    def __init__(self, symbol : base_item.trade_symbol, su : base_item.save_unit, cfg : config.Config, KLINE_WINDOW : int) -> None:
        self.__symbol = symbol
        self.__su = su
        self._config = cfg
        self._klines = pd.DataFrame(columns=['date_b', 'open', 'high', 'low', 'close', 
            'volume', 'date_e', 'amount', 'count', 'buy_amount', 'buy_money', 'ignore'])
        self._ksm = kline_status_manager()
        self._KLINE_WINDOW = KLINE_WINDOW     # 允许的最大K线数量，超出则弹出最早的K线。=0则不保存K线
        if self._KLINE_WINDOW < 0 :
            logging.error('最大K线数量{}无效，复位为0。'.format(self._KLINE_WINDOW))
            self._KLINE_WINDOW = 0
        elif self._KLINE_WINDOW > DEFAULT_MAX_KLINES :
            logging.error('最大K线数量{}超出阈值，使用默认最大值={}。'.format(self._KLINE_WINDOW, DEFAULT_MAX_KLINES))
            self._KLINE_WINDOW = DEFAULT_MAX_KLINES
        self._name = 'processor_T'
        self._enable = True   #是否允许交易
        self._master = False            #是否为主控器
        self._controled = False         #主控器是否运行在控制模式（只有主控器工作/worker不工作）

    def is_master(self) -> bool:
        return self._master
    def is_controled(self) -> bool:
        return self._controled  
    @property
    def enable(self) -> bool:
        return self._enable
    @enable.setter
    def enable(self, ebl : bool) -> None:
        if self._enable != ebl :
            self._enable = ebl
            if self._enable :
                self._enable_action()
            else :
                self._disable_action()
        return
    @property
    def symbol(self) -> base_item.trade_symbol:
        return self.__symbol
    @property
    def K_MAX(self) -> int:
        return self._KLINE_WINDOW    
    @property
    def K_len(self) -> int:
        return len(self._klines)
    @property
    def su(self) -> base_item.save_unit:
        return self.__su
    @property
    def interval(self) -> base_item.kline_interval:
        return self.su.interval
    @property
    def name(self) -> str :
        return self._name
    @property
    def config(self) -> config.Config:
        return self._config
    def _enable_action(self) :
        return
    def _disable_action(self) :
        return
    #离线测试参数
    #to do : 如实际使用，可能需要把su调整为下一档，如日线则为小时线，小时线则为分钟线。以满足攻击测试需要。
    def get_attack_info(self) -> tuple[base_item.save_unit, int, int] :
        attack_su = self.__su
        begin_ts = self.get_time_end(-1) + 1
        ATTACK_HOURS = 24
        #end_ts = begin_ts + attack_su.get_unit_seconds() * 1000
        end_ts = begin_ts + ATTACK_HOURS * 60 * 60 * 1000
        return attack_su, begin_ts, end_ts
    def _set_name(self, name : str) :
        self._name = name
        return
    def get_kline_status(self, timestamp : int) -> KLINE_PROCESS:
        if self._ksm.found(timestamp) :
            return self._ksm.get_status(timestamp)
        else :
            return KLINE_PROCESS.NONE
    def kline_status_finish(self, timestamp : int, status : KLINE_PROCESS, extends = None) -> kline_status:
        if self._ksm.found(timestamp) :
            return self._ksm.finish(timestamp)
        else :
            return self._ksm.add(timestamp, status, extends)
    #删除所有K线数据
    def reset_klines(self) -> None:
        self._klines.drop(index=self._klines.index, inplace=True)
        assert(self.K_len == 0)
        return
    # 添加一条新的K线数据    
    def add_kline(self, kline : list, inteval : base_item.kline_interval) -> bool:
        kline = data_loader.get_kline_shape(kline)
        logging.debug('添加一条K线数据，inter={}, 开始时间={}...'.format(inteval.value, utility.timestamp_to_string(kline[0])))
        if self.K_MAX <= 0 :
            logging.info('处理器{}不存储K线，忽略。'.format(self._name))
            return False
        # 如果当前K线数量超过最大限制，则删除最早的K线
        if self.K_len + 1 > self.K_MAX :
            logging.info('已有K线数量{}达到或超过最大限制{}，删除最早的K线...'.format(self.K_len, self.K_MAX))
            #self._klines.drop(index=self._klines.index[0], inplace=True)
            self._klines.drop(index=self._klines.head(1).index, inplace=True)
        # 添加新的K线数据
        #self._klines.loc[len(self._klines)] = data_loader.get_kline_shape(kline)
        # 在df尾部添加新行
        index = self._klines.index[-1] + 1
        self._klines.loc[index] = data_loader.get_kline_shape(kline)
        
        assert(self.K_len <= self.K_MAX)
        logging.debug('添加K线数据完成，当前K线数量={}'.format(self.K_len))
        return True
    def add_klines(self, klines : list) -> int:
        logging.debug('添加{}条K线数据...'.format(len(klines)))
        if self.K_MAX <= 0 :
            logging.info('处理器{}不存储K线，忽略。'.format(self._name))
            return 0
        if len(klines) <= 0 :
            logging.info('没有新的K线数据，忽略。')
            return 0
        begin = 0
        if self.K_len + len(klines) > self.K_MAX :
            if len(klines) > self.K_MAX :
                self._klines.drop(index=self._klines.index, inplace=True)   #删除所有K线数据
                begin = len(klines) - self.K_MAX
            else :
                drops = self.K_len + len(klines) - self.K_MAX
                # 删除最早的drops条K线数据
                #self._klines.drop(index=self._klines.index[:drops], inplace=True)
                self._klines.drop(index=self._klines.head(drops).index, inplace=True)
        # 添加新的K线数据
        for kline in klines[begin:] :
            self._klines.loc[len(self._klines)] = data_loader.get_kline_shape(kline)
        logging.debug('添加{}条K线数据完成，当前K线数量={}'.format(len(klines), self.K_len))
        assert(self.K_len <= self.K_MAX)
        return self.K_len
    def init_klines(self, klines : list) -> int :
        logging.debug('初始化K线数据...')
        if self.K_MAX <= 0 :
            logging.info('处理器{}不存储K线，忽略。'.format(self._name))
            return 0
        self.reset_klines()  #删除所有K线数据
        return self.add_klines(klines)
    # 是否需要查询K线数据
    # tuple[0]：-1表示不需要查询。=0表示基于当前时间。>0表示需要查询的开始时间戳。
    # tuple[1]：请求的K线数量。
    def need_query(self) -> tuple[int, int, base_item.kline_interval]:
        now = int(datetime.now().timestamp() * 1000)
        if self.su.need_query(now) :
            logging.info('PT需要查询K线数据，最后查询时间={}。'.format(utility.timestamp_to_string(self.su.query_ts)))
            return 0, 1, self.su.interval
        else :
            logging.info('PT不需要查询K线数据，最后查询时间={}。'.format(utility.timestamp_to_string(self.su.query_ts)))
            return -1, 0, self.su.interval
    # 更新K线数据
    # 如子类重载触发了交易，服务器返回的交易详情在dict中
    def update_kline(self, kline : list, interval : base_item.kline_interval) -> tuple[UPDATE_KLINE_RESULT, dict]:
        ukr = UPDATE_KLINE_RESULT()
        assert(isinstance(kline, list))
        self.su.query_ts = int(datetime.now().timestamp() * 1000)       #更新最后查询时间戳
        logging.info('PT最后查询时间更新为={}。'.format(utility.timestamp_to_string(self.su.query_ts)))
        if self.K_len == 0 :    #第一条K线
            self.add_kline(list, interval)
            ukr.K_added()
        else :
            last_begin = self.get_time_begin(-1)
            last_end = self.get_time_end(-1)
            last_index = self._klines.index[-1] 
            if last_begin == kline[0] : #开始时间戳相同->最后一条K线的更新
                self._klines.loc[last_index] = kline
                logging.info('更新最后一条K线，开始时间={}，开盘价={}，最新价={}.'.format(utility.timestamp_to_string(kline[0]),
                    round(self._klines.loc[last_index, 'open'], 2), round(self._klines.loc[last_index, 'close'], 2)))
                ukr.K_updated()
            else :      #新增一条K线
                # 判断K线是否连续
                last_end = self.get_time_end(-1)
                if last_end + 1 != kline[0] :
                    logging.error('K线不连续，最后一条K线结束时间={}，当前K线开始时间={}。'.format(utility.timestamp_to_string(last_end), 
                        utility.timestamp_to_string(kline[0])))
                    ukr.K_errored()
                else :
                    if last_begin + interval.get_interval_seconds() * 1000 != kline[0] :
                        logging.error('K线不连续，最后一条K线开始时间={}，当前K线开始时间={}。'.format(utility.timestamp_to_string(last_begin), 
                            utility.timestamp_to_string(kline[0])))
                        ukr.K_errored()
                    elif last_end + 1 != kline[0] :
                        logging.error('K线不连续，最后一条K线结束时间={}，当前K线开始时间={}。'.format(utility.timestamp_to_string(last_end), 
                            utility.timestamp_to_string(kline[0])))
                        ukr.K_errored()
                    else :
                        assert(last_begin + interval.get_interval_seconds() * 1000 == kline[0])
                        assert(last_end + 1 == kline[0])
                        self.add_kline(kline, interval)
                        ukr.K_added()

        #取得第一条K线的日期
        #first_date = int(self._klines.loc[self._klines.index[0], 'date_b'])
        first_s = utility.timestamp_to_string(self.get_time_begin(0))
        last_s = utility.timestamp_to_string(self.get_time_begin(-1))
        logging.debug('通知：窗口={}, 第一条K线={}，最后一条K线={}.'.format(self.K_len, first_s, last_s))
        assert(self.K_len <= self.K_MAX)
        return ukr, None
    #实时获取最后一条固化的K线
    def query_last_fixed_kline(self, interval : base_item.kline_interval) -> list:
        cur = int(datetime.now().timestamp()) * 1000
        begin = interval.get_K_begin(cur)
        last = begin - interval.get_interval_seconds() * 1000
        offset = interval.calc_offset(1, begin = cur, BACK=True)
        logging.info('cur={}, begin={}, last={}, offset={}'.format(utility.timestamp_to_string(cur), utility.timestamp_to_string(begin), 
            utility.timestamp_to_string(last), utility.timestamp_to_string(offset)))
        assert(last == offset)
        klines = kline_spider.get_klines(self.symbol, interval, offset, 1)
        if len(klines) == 0:
            logging.error('获取实时K线数据失败。')
            return None
        assert(len(klines) == 1)
        kline = data_loader.get_kline_shape(klines)
        logging.info('获取实时K线数据成功，开始时间={}，结束时间={}。'.format(utility.timestamp_to_string(kline[0]), utility.timestamp_to_string(kline[6])))
        return kline

    def daily_report(self) -> list[str] :
        report = list()
        report.append('处理器({})日报：'.format(self._name))
        report.append('enable={}，当前K线数量={}'.format(self.enable, len(self._klines)))
        if len(self._klines) > 0 :
            first = self.print_kline(0)
            report.append('{}'.format(first))
            if len(self._klines) > 1 :
                last = self.print_kline(-1)
                report.append('{}'.format(last))
        return report

    #打印某条K线数据，index区间为[-len(klines), len(klines)-1]，即iloc坐标系
    def print_kline(self, index : int) -> str:
        if abs(index) >= len(self._klines) :
            logging.error('index={}超出范围，当前K线数量={}'.format(index, len(self._klines)))
            return ''
        begin = int(self._klines.iloc[index, 0])
        s_begin = utility.timestamp_to_string(begin)
        end = int(self._klines.iloc[index, 6])
        s_end = utility.timestamp_to_string(end)
        info = '第{}条K线开始={}, 结束={}，开盘价={}, 收盘价={}, 最高价={}, 最低价={}。'.format(index, s_begin, s_end,
            self._klines.iloc[index, 1], self._klines.iloc[index, 4],
            self._klines.iloc[index, 2], self._klines.iloc[index, 3])
        return info
    def print_klines(self) -> list[str]:
        lines = list()
        for i in range(len(self._klines)) :
            lines.append(self.print_kline(i))
        return lines
    def get_time_begin(self, index : int) -> int:
        if abs(index) >= len(self._klines) :
            return 0
        return int(self._klines.iloc[index, 0])
    def get_time_end(self, index : int) -> int:
        if abs(index) >= len(self._klines) :
            return 0
        return int(self._klines.iloc[index, 6])
    def get_price_open(self, index : int) -> float:
        if abs(index) >= len(self._klines) :
            return 0
        return round(self._klines.iloc[index, 1], 2)
    def get_price_close(self, index : int) -> float:
        if abs(index) >= len(self._klines) :
            return 0
        return round(self._klines.iloc[index, 4], 2)
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

    def _prepare_offline(self, END : int) -> int:
        return processor_T.PREPARE_OK
    def _prepare_online(self) -> int:
        return processor_T.PREPARE_OK
    #预处理
    #当ONLINE=TRUE时，END无意义。
    #当ONLINE=FALSE时，END为指定历史K线的结束时间戳。如END=0，则为当前时间戳。
    def prepare(self, ONLINE : bool, END : int = 0) -> int:
        if ONLINE :
            return self._prepare_online()
        else :
            return self._prepare_offline(END)

def test():
    logger = logging.getLogger()
    
    stdout_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(process)d-%(threadName)s - '
                              '%(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s')
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    d1 = base_item.kline_interval.d1
    begin = utility.string_to_timestamp('2025-04-20 08:00:00')
    step = d1.calc_step(begin, 0)
    print('step={}'.format(step))
    return


    df = pd.DataFrame({'A': ['A1', 'A2', 'A3'],
                        'B': ['B1', 'B2', 'B3'],
                         'C': ['C1', 'C2', 'C3']})
    print('打印原始数据...')
    print(df)
    print('删除第一条K线数据...')
    df.drop(index = df.head(1).index, inplace=True)
    print(df)
    # 添加新的K线数据
    print('添加新的K线数据...')
    print('len(df)={}'.format(len(df)))
    print('len(df.index)={}'.format(len(df.index)))
    index = df.index[-1] + 1
    print('index={}'.format(index))
    new_row = pd.Series({'A': 'A4', 'B': 'B4', 'C': 'C4'})
    #new_row = ['A4', 'B4', 'C4']
    #在df尾部添加新行
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    #df.loc[index] = new_row
    print('第一次添加后，len(df)={}, row shape={}'.format(len(df), df.shape[0]))
    print('第一次添加后，len(df.index)={}'.format(len(df.index)))
    index = df.index[-1] + 1
    print('index={}'.format(index))
    print(df)

    

    print('\n\n\n开始第二次弹出...')
    df.drop(index = df.head(1).index, inplace=True)
    index = df.index[-1] + 1        #最后的行数据索引+1（解决冲掉最后一行问题）
    print('index={}'.format(index))
    new_row = ['A5', 'B5', 'C5']
    nd_row = np.array(new_row)      #如不指定列名，则采用np.array模式
    new_row = pd.Series({'A': 'A5', 'B': 'B5', 'C': 'C5'})      #指定列名模式
    df.loc[index] = nd_row
    print('行号重置前的数据...')
    print(df)
    df.reset_index(drop=True, inplace=True)     #重置行索引，即行的第一条数据索引为0，后面连续
    #df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    print('第二次添加后，len(df)={}, row shape={}'.format(len(df), df.shape[0]))
    print('第二次添加后，len(df.index)={}'.format(len(df.index)))
    print('行号重置后的数据...')
    print(df)

    return

    #print('test processor_template...')
    su = base_item.save_unit(base_item.kline_interval.d1)
    pt = processor_T(base_item.trade_symbol.BTCUSDT, su, None, 0)
    info = pt.query_last_fixed_kline(base_item.kline_interval.d1)
    print(info)
    info = pt.query_last_fixed_kline(base_item.kline_interval.m3)
    print(info)
    return


    ksm = kline_status_manager()
    print('self.max={}'.format(ksm.MAX_COUNT))
    ksm.MAX_COUNT = 10
    print('updated self.max={} '.format(ksm.MAX_COUNT))
    print('updated class.max={} '.format(kline_status_manager.MAX_COUNT))

    for i in range(1, 20) :
        dt = datetime(year=2015, month=2, day=i)
        ts = int(dt.timestamp() * 1000)
        print('添加K线时间戳={}'.format(utility.timestamp_to_string(ts)))
        ksm.add(ts, KLINE_PROCESS.NONE, None)
    print('当前K线状态数量={}'.format(len(ksm._klines)))
    return

#test()