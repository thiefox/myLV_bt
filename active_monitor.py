import sys
import time
import logging
from datetime import datetime, timedelta

from utils import utility
from utils import log_adapter
from utils import config

import base_item
import kline_spider
import MACD_process

#from binance import BinanceSpotHttp
#from binance import authentication
import binance.binance_spot as bs

DEFAULT_BACK_COUNT = 200

class active_monitor() :
    def __init__(self, su : base_item.save_unit) :
        self.__su = su
        self.symbol = base_item.trade_symbol.BTCUSDT
        ONE_HOUR_SECONDS = 60 * 60
        EIGHT_HOURS_SECONDS = ONE_HOUR_SECONDS * 8
        ONE_DAY_SECONDS = 60 * 60 * 24
        TEN_YEARS_SECONDS = ONE_DAY_SECONDS * 365 * 10
        self.MONITOR_SECONDS = ONE_HOUR_SECONDS * 4
        self.monitor_begin = datetime.min
        
        last_handled = 0
        self.config = config.Config()
        if not self.config.loads(config.Config.GET_CONFIG_FILE()):
            print('异常：加载配置文件{}失败。'.format(config.Config.GET_CONFIG_FILE()))
 
        item = self.config.get_macd(self.symbol, self.__su.interval)
        if item is not None and item.last_handled_cross != '':
            print('重要：最后的处理交叉点1={}'.format(item.last_handled_cross))
            info = datetime.strptime(item.last_handled_cross, '%Y-%m-%d %H:%M:%S') 
            print('重要：最后的处理交叉点2={}'.format(info.strftime('%Y-%m-%d %H:%M:%S')))
            last_handled = info.timestamp() * 1000
        self.processor = MACD_process.MACD_processor(self.symbol, last_handled)
        #self.config.update_macd(self.symbol, self.__su.interval, datetime.now().strftime('%Y-%m-%d 00:00:00'))
        return
    
    def _get_client(self) -> bs.BinanceSpotHttp:
        return bs.BinanceSpotHttp(api_key=self.config.api_key, private_key=self.config.private_key)

    def _prepare(self) -> bool:
        http_client = bs.BinanceSpotHttp(api_key=self.config.api_key, private_key=self.config.private_key)        
        params = http_client.get_exchange_params(self.symbol.value)
        if params is None:
            print('异常：获取交易对参数失败。')
            return False
        if 'min_quantity' in params and 'min_price' in params:
            self.config.update_exchange_info(self.symbol.value, params['min_price'], params['min_quantity'])
        else:
            print('异常：获取minQty和minPrice交易参数失败。')
            return False
        offset = self.__su.calc_offset(DEFAULT_BACK_COUNT)
        print('开始获取{}条历史K线数据，开始时间戳={}'.format(DEFAULT_BACK_COUNT, offset))
        assert(offset > 0)
        klines = kline_spider.get_klines(base_item.trade_symbol.BTCUSDT, self.__su.interval, offset)
        if len(klines) == 0:
            print('获取历史K线数据失败')
            return False
        print('重要：初始化共获取到K线数据记录={}，DEF_BACK_CN={}'.format(len(klines), DEFAULT_BACK_COUNT))
        if len(klines) < DEFAULT_BACK_COUNT:
            print('异常：获取到的历史K线数据记录数少于{}'.format(DEFAULT_BACK_COUNT))
            return False
        info = self.processor.init_history(klines)
        print('重要：初始化历史数据结果={}'.format(info))
        return info >= self.processor.WINDOW_LENGTH
    def _finish(self) :
        return
    #是否需要退出
    def _need_exit(self) -> bool:
        now = datetime.now()
        delta = now - self.monitor_begin
        if delta.total_seconds() >= self.MONITOR_SECONDS:
            print('重要：开始时间={}，当前时间={}，达到结束时间，退出。'.format(datetime.strftime(self.monitor_begin, '%Y-%m-%d %H-%M-%S'), 
                datetime.strftime(now, '%Y-%m-%d %H-%M-%S')))
            return True
        return False
    #获取剩余的监控时间
    def _get_remain_seconds(self) -> timedelta:
        now = datetime.now()
        delta = now - self.monitor_begin
        if self.MONITOR_SECONDS >= delta.total_seconds() :
            return timedelta(seconds=self.MONITOR_SECONDS - delta.total_seconds())
        else :
            return timedelta(seconds=0)
    def _monitor(self) :
        print('minotor开始...')
        self.monitor_begin = datetime.now()

        begin = self.processor.get_time_begin(-1)
        end = self.processor.get_time_end(-1)
        print('最后一条K线的开始时间={}, 结束时间={}'.format(utility.timestamp_to_string(begin), utility.timestamp_to_string(end)))
        cur = 0
        while True:
            remains = self._get_remain_seconds()
            text = "%d天 %d小时 %d分钟" % (remains.days, remains.seconds // 3600, (remains.seconds // 60) % 60)     
            print('---获取实时K线数据，当前时间={}，剩余运行时间={}...'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), text))
            now = datetime.now().timestamp() * 1000
            if now < end:
                cur = begin
            else :
                cur = end + 1
            klines = kline_spider.get_klines(self.symbol, self.__su.interval, cur, 1)
            if len(klines) == 0:
                print('异常：获取实时K线数据失败。')
                continue
            print('重要：获取到实时K线数据记录={}'.format(len(klines)))
            assert(len(klines) == 1)
            begin_time = int(klines[0][0])
            cross, status, timeinfo = self.processor.update_kline(klines)
            if status == base_item.TRADE_STATUS.BUY or status == base_item.TRADE_STATUS.SELL:
                assert(timeinfo == begin_time)
                print('重要：发生交易处理，status={}，cross={}，时间={}({})'.format(status, cross,
                    timeinfo, utility.timestamp_to_string(timeinfo)))
                self.config.update_macd(self.symbol, self.__su.interval, utility.timestamp_to_string(timeinfo))
            elif status == base_item.TRADE_STATUS.HANDLED :
                assert(timeinfo == begin_time)
                print('重要：K线开始时间={}({})，发生交叉但已被处理过，忽略。'.format(timeinfo, utility.timestamp_to_string(timeinfo)))
            else :
                assert(status == base_item.TRADE_STATUS.IGNORE)
                print('忽略该K线(无交叉)，开始时间={}({})'.format(begin_time, utility.timestamp_to_string(begin_time)))
                pass
            if self._need_exit() :
                break            
            time.sleep(60)
        monitor_end = datetime.now()

        print('重要：minotor结束, 开始时间={}，结束时间={}。'.format(datetime.strftime(self.monitor_begin, '%Y-%m-%d %H-%M-%S'), 
            datetime.strftime(monitor_end, '%Y-%m-%d %H-%M-%S')))
        delta = monitor_end - self.monitor_begin
        text = "%d天 %d小时 %d分钟" % (delta.days, delta.seconds // 3600, (delta.seconds // 60) % 60)        
        print('重要：minotor结束, 运行时长={}。'.format(text))
        self.monitor_begin = datetime.min
        #self.config.save()
        return
    def run(self) :
        if not self._prepare():
            return
        time.sleep(1)
        self._monitor()
        self._finish()
        return


def test() :
    print("Active Monitor Start...")

    LOG_FLAG = 0
    if LOG_FLAG == 1 :
        str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        #logging.basicConfig(level=logging.INFO, format=format, filename='log/{}_{}_{}H-{}.txt'.format(symbol, year, interval, str_now))
        logging.basicConfig(level=logging.INFO, format=format, filename='log/active_monitor-{}.txt'.format(str_now))
        logger = logging.getLogger('binance')
        logger.setLevel(logging.INFO)
        #把print输出到日志文件
        tmp_out = sys.stdout
        tmp_err = sys.stderr

        sys.stdout = log_adapter.LoggerWriter(logger, logging.INFO)
        sys.stderr = log_adapter.LoggerWriter(logger, logging.ERROR)

    su = base_item.save_unit(base_item.kline_interval.d1)
    monitor = active_monitor(su)
    monitor.run()

    if LOG_FLAG == 1 :
        sys.stdout = tmp_out
        sys.stderr = tmp_err
    print("Active Monitor End.")
    return

#目前采用的币安监控处理器
test()
