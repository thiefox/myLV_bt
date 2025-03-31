import sys
import time
import platform
import signal
import logging
from datetime import datetime, timedelta

from com_utils import utility
from com_utils import log_adapter
from com_utils import config

import base_item
import kline_spider
import MACD_process
import data_loader
import mail_template

import socket

#from binance import BinanceSpotHttp
#from binance import authentication
#import binance.binance_spot as bs
import binance_spot_wrap as bsw

DEFAULT_BACK_COUNT = 200

GRACE_EXIT = False

def exit_gracefully(signum, frame):
    logging.info('active_monitor接收到退出信号={}'.format(signum))
    global GRACE_EXIT
    GRACE_EXIT = True
    sys.exit(0)
    return

class active_monitor() :
    def __init__(self, su : base_item.save_unit) :
        self.__su = su
        self.symbol = base_item.trade_symbol.BTCUSDT
        ONE_HOUR_SECONDS = 60 * 60
        EIGHT_HOURS_SECONDS = ONE_HOUR_SECONDS * 8
        ONE_DAY_SECONDS = 60 * 60 * 24
        TEN_YEARS_SECONDS = ONE_DAY_SECONDS * 365 * 10
        #self.MONITOR_SECONDS = ONE_HOUR_SECONDS * 4
        self.MONITOR_SECONDS = 0
        self.monitor_begin = datetime.min
        self.last_notify = datetime.min           #每日12点的例行通知
        self.bsw = bsw.binance_spot_wrapper()
        self.outer_exit_check_func = None
        if not self.bsw.init() :
            logging.error('初始化币安接口包装器失败。')
            raise Exception('初始化币安接口包装器失败。')
            return
        assert(self.bsw.is_valid())
        last_handled = 0
        self.config = config.Config()
        if not self.config.loads(config.Config.GET_CONFIG_FILE()):
            logging.error('加载配置文件{}失败。'.format(config.Config.GET_CONFIG_FILE()))
            raise Exception('加载配置文件={}失败。'.format(config.Config.GET_CONFIG_FILE()))
            return
        last_handled = self.config.general.handled_cross
        if last_handled > 0 :
            logging.info('从配置读取的最后处理交叉点={}。'.format(utility.timestamp_to_string(last_handled)))
 
        self.processor = MACD_process.MACD_processor(self.symbol, self.config)
        return
    
    def _general_prepare(self) -> bool:
        assert(self.bsw.is_valid())
        min_price, min_quantity = self.bsw.get_exchange_params(self.symbol)
        if min_quantity > 0 :
            self.config.update_exchange_info(self.symbol.value, min_price, min_quantity)
            logging.info('交易参数：最小交易数量={}，最小交易价格={}。'.format(min_quantity, min_price))
        else :
            logging.error('获取minQty={}和minPrice={}交易参数失败。'.format(min_quantity, min_price))
            return False
        return True
    #在线模式加载历史数据
    def _prepare_online(self) -> bool:
        if not self._general_prepare():
            return False
        begin = int(datetime.now().timestamp()) * 1000
        offset = self.__su.calc_offset(DEFAULT_BACK_COUNT, begin)
        assert(offset > 0)
        logging.info('开始在线获取{}条历史K线数据，开始时间戳={}，结束时间戳={}'.format(DEFAULT_BACK_COUNT,
            utility.timestamp_to_string(offset), utility.timestamp_to_string(begin)))
        klines = kline_spider.get_klines(base_item.trade_symbol.BTCUSDT, self.__su.interval, offset)
        if len(klines) == 0:
            logging.critical('在线获取历史K线数据失败。')
            return False
        logging.info('在线初始化共获取到K线数据记录={}，BACK_CN={}'.format(len(klines), DEFAULT_BACK_COUNT))
        if len(klines) < DEFAULT_BACK_COUNT:
            logging.critical('在线获取到的历史K线数据记录数={}，低于阈值={}。'.format(len(klines), DEFAULT_BACK_COUNT))
            return False
        info = self.processor.init_history(klines)
        logging.info('在线初始化历史数据结果={}。'.format(info))
        return info >= self.processor.WINDOW_LENGTH
    #离线模式加载历史数据
    #end: 0表示不指定结束时间，否则表示指定的结束时间
    def _prepare_offline(self, end : int = 0) -> bool:
        if not self._general_prepare():
            return False
        if end == 0 :
            end = self.__su.interval.get_K_begin()
        offset = self.__su.calc_offset(DEFAULT_BACK_COUNT, end)
        assert(offset > 0)
        logging.info('开始离线获取{}条历史K线数据，开始时间戳={}，结束时间戳={}'.format(DEFAULT_BACK_COUNT, 
            utility.timestamp_to_string(offset), utility.timestamp_to_string(end)))
        klines = data_loader.load_klines_range(base_item.trade_symbol.BTCUSDT, self.__su,
            utility.timestamp_to_datetime(offset), utility.timestamp_to_datetime(end))
        if len(klines) == 0:
            logging.critical('离线获取历史K线数据失败。')
            return False
        logging.info('离线初始化共获取到K线数据记录={}，BACK_CN={}'.format(len(klines), DEFAULT_BACK_COUNT))
        if len(klines) < DEFAULT_BACK_COUNT:
            logging.critical('离线获取到的历史K线数据记录数={}，低于阈值={}。'.format(len(klines), DEFAULT_BACK_COUNT))
            return False
        info = self.processor.init_history(klines)
        logging.info('离线初始化历史数据结果={}。'.format(info))
        return info >= self.processor.WINDOW_LENGTH
    def _finish(self) :
        return
    #是否需要退出
    def _need_exit(self) -> bool:
        global GRACE_EXIT
        if GRACE_EXIT :
            logging.info('GRACE_EXIT被置位，退出...')
            return True
        if self.outer_exit_check_func is not None :
            if self.outer_exit_check_func() :
                logging.info('外部退出检查函数返回True，退出...')
                return True
        now = datetime.now()
        delta = now - self.monitor_begin
        if self.MONITOR_SECONDS > 0 and delta.total_seconds() >= self.MONITOR_SECONDS:
            logging.info('开始时间={}，当前时间={}，达到结束时间，退出...'.format(datetime.strftime(self.monitor_begin, '%Y-%m-%d %H-%M-%S'),
                datetime.strftime(now, '%Y-%m-%d %H-%M-%S')))
            return True
        return False
    def _daily_notify(self) :
        now = datetime.now()
        #if now.hour == 12 and now.day > self.last_notify.day :
        if now.hour != self.last_notify.hour :
            logging.info('定期报告，当前时间={}。'.format(now.strftime('%Y-%m-%d %H:%M:%S')))
            msg = '每日定点通知，当前时间={}。\n'.format(now.strftime('%Y-%m-%d %H:%M:%S'))
            mail = mail_template.mail_content('thiefox@qq.com')
            last_cross = self.processor.get_last_cross()
            if last_cross is not None :
                msg += '最后出现的交叉点时间={}，类型={}，状态={}。\n'.format(utility.timestamp_to_string(last_cross.timestamp),
                    last_cross.cross.value, last_cross.status.value)
            last_handled = self.processor.get_last_handled_cross()
            price = self.bsw.get_price(self.symbol)
            if last_handled is not None :
                msg += '最后处理的交叉点时间={}，类型={}，状态={}。\n'.format(utility.timestamp_to_string(last_handled.timestamp),
                    last_handled.cross.value, last_handled.status.value)
            msg += '当前{}价格={}$。\n'.format(self.symbol.value, price)
            logging.info('开始获取账户余额信息...')
            balances = self.bsw.get_all_balances()
            logging.info('获取账户余额信息完成。')
            btc_total = float(0)
            usdt_asset = float(0)
            for balance in balances :
                if balance['asset'] == 'USDT' :
                    usdt_asset = round(float(balance['free']) + float(balance['locked']), 2)
                    if float(balance['locked']) > 0:
                        msg += 'USDT余额={}$，free={}$，lock={}$。\n'.format(usdt_asset, round(balance['free'], 2), round(balance['locked'], 2))
                    else :
                        msg += 'USDT余额={}$。\n'.format(usdt_asset)
                elif balance['asset'] == 'BTC' :
                    btc_total = round(float(balance['free']) + float(balance['locked']), 5)
                    if float(balance['locked']) > 0 :
                        msg += '币{}数量={}个，free={}个，lock={}个。\n'.format(balance['asset'], btc_total, round(balance['free'], 5), round(balance['locked'], 5))
                    else :
                        msg += '币{}数量={}个。\n'.format(balance['asset'], btc_total)
            btc_asset = round(btc_total * price, 2)
            total_asset = round(usdt_asset + btc_asset, 2)
            msg += '当前USDT剩余={}$，BTC数量={}，价值={}$，总资产={}$。\n'.format(usdt_asset, btc_total, btc_asset, total_asset)
            crosses_info = self.processor.print_cross()
            if len(crosses_info) > 0 :
                msg += '---打印交叉点信息：\n'
                for cross_info in crosses_info :
                    msg += '------' + cross_info + '\n'

            if mail.write_mail('定期通报-{}$'.format(int(price)), msg) :
                logging.info('每日12点日报通知发送成功。')
                self.last_notify = now
        return
    #获取剩余的监控时间
    def _get_remain_seconds(self) -> timedelta:
        now = datetime.now()
        delta = now - self.monitor_begin
        if self.MONITOR_SECONDS >= delta.total_seconds() :
            return timedelta(seconds=self.MONITOR_SECONDS - delta.total_seconds())
        else :
            return timedelta(seconds=0)
    def print_kline(self, index : int) :
        s_begin = utility.timestamp_to_string(self.processor.get_time_begin(index))
        s_end = utility.timestamp_to_string(self.processor.get_time_end(index))
        open_price = self.processor.get_price_open(index)
        close_price = self.processor.get_price_close(index)
        logging.info('K线总数={}，K线序号={}，开始时间={}，结束时间={}，开盘价={}，收盘价={}'.format(self.processor.len, index,
            s_begin, s_end, open_price, close_price))
    def _monitor(self) :
        logging.debug('minotor开始...')
        self.monitor_begin = datetime.now()

        self.print_kline(-1)
        begin = self.processor.get_time_begin(-1)
        end = self.processor.get_time_end(-1)
        cur = 0
        while True:
            if self._need_exit() :
                logging.info('_need_exit返回True，退出循环。')
            remains = self._get_remain_seconds()
            text = "%d天 %d小时 %d分钟" % (remains.days, remains.seconds // 3600, (remains.seconds // 60) % 60)
            logging.debug('获取实时K线数据，当前时间={}，剩余运行时间={}...'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), text))     
            now = datetime.now().timestamp() * 1000
            if now < end:
                cur = begin
            else :
                cur = end + 1
            klines = kline_spider.get_klines(self.symbol, self.__su.interval, cur, 1)
            if len(klines) == 0:
                logging.error('获取实时K线数据失败。')
                time.sleep(3)
                continue
            logging.info('获取到实时K线数据记录={}'.format(len(klines)))
            assert(len(klines) == 1)
            begin_time = int(klines[0][0])
            cross, status, timeinfo, infos = self.processor.update_kline(klines)
            if status == base_item.TRADE_STATUS.BUY or status == base_item.TRADE_STATUS.SELL:
                assert(timeinfo == begin_time)
                logging.info('发生交易处理，status={}，cross={}，时间={}({})'.format(status, cross.value,
                    timeinfo, utility.timestamp_to_string(timeinfo)))
                mail = mail_template.mail_content('thiefox@qq.com')
                if infos['local_code'] == 0:
                    mail.update_with_success(utility.timestamp_to_string(timeinfo), cross, infos)
                else :
                    mail.update_with_failed(utility.timestamp_to_string(timeinfo), cross, infos['local_msg'])
                if not mail.send_mail() :
                    if cross.is_golden() :  
                        logging.critical('金叉买入失败，发送邮件失败。')
                    else :
                        logging.critical('死叉卖出失败，发送邮件失败。')
            elif status == base_item.TRADE_STATUS.FAILED :
                logging.error('时间={}发生交叉点，但交易失败，code={}, 原因={}。'.format(utility.timestamp_to_string(timeinfo),
                    infos['local_code'], infos['local_msg']))
                mail = mail_template.mail_content('thiefox@qq.com')
                mail.update_with_failed(utility.timestamp_to_string(timeinfo), cross, infos['local_msg'])
                if not mail.send_mail() :
                    logging.critical('交易失败，发送邮件失败。')
            elif status == base_item.TRADE_STATUS.HANDLED :
                assert(timeinfo == begin_time)
                logging.info('K线开始时间={}({})，发生交叉但已被处理过，忽略。'.format(timeinfo, utility.timestamp_to_string(timeinfo)))
            else :
                assert(status == base_item.TRADE_STATUS.IGNORE)
                logging.info('忽略该K线(无交叉)，开始时间={}({})'.format(timeinfo, utility.timestamp_to_string(timeinfo)))
                pass
            time.sleep(1)
            self._daily_notify()
            if self._need_exit() :
                break            
            time.sleep(60)
        monitor_end = datetime.now()
        logging.info('minotor结束, 开始时间={}，结束时间={}。'.format(datetime.strftime(self.monitor_begin, '%Y-%m-%d %H-%M-%S'),
            datetime.strftime(monitor_end, '%Y-%m-%d %H-%M-%S')))
        delta = monitor_end - self.monitor_begin
        text = "%d天 %d小时 %d分钟" % (delta.days, delta.seconds // 3600, (delta.seconds // 60) % 60)        
        logging.info('minotor结束, 运行时长={}。'.format(text))
        self.monitor_begin = datetime.min
        #self.config.save()
        return
    #本地模拟的监控处理，用于观察发生交叉点的后续处理是否正常
    def _fake_monitor(self, attack_su : base_item.save_unit, begin : int = 0, end : int = 0) :
        logging.debug('fake minotor开始...')
        self.print_kline(-1)
        if begin == 0 :
            begin = self.processor.get_time_end(-1) + 1
            #begin = attack_su.get_unit_begin()
        assert(isinstance(begin, int))

        self_k_begin = self.__su.interval.get_K_begin()
        attack_k_begin = attack_su.interval.get_K_begin()
        logging.info('self_k_begin={}，attack_k_begin={}...'.format(utility.timestamp_to_string(self_k_begin),
            utility.timestamp_to_string(attack_k_begin)))
        if end == 0 :
            end = begin + attack_su.get_unit_seconds() * 1000
        assert(isinstance(end, int))
        logging.info('fake minotor开始时间={}，结束时间={}...'.format(utility.timestamp_to_string(begin),
            utility.timestamp_to_string(end)))

        klines = data_loader.load_klines_range(base_item.trade_symbol.BTCUSDT, attack_su,
            utility.timestamp_to_datetime(begin), utility.timestamp_to_datetime(end))
        if len(klines) == 0:
            logging.critical('离线获取下级单位的增量K线数据失败。')
            return
        logging.info('离线获取下级单位，共获取到K线数据记录={}。'.format(len(klines)))

        FIXED_BEGIN_TIMESTAMP = FIXED_END_TIMESTAMP = 0
        if len(klines) > 0 :
            begin_time = int(klines[0][0])
            FIXED_BEGIN_TIMESTAMP = begin_time
            FIXED_END_TIMESTAMP = int(self.__su.interval.get_delta().total_seconds()) * 1000 + begin_time
            end_time = int(klines[0][6])
            logging.info('第一条K线的开始时间={}，结束时间={}。'.format(utility.timestamp_to_string(begin_time),
                utility.timestamp_to_string(end_time)))
            begin_time = int(klines[-1][0])
            end_time = int(klines[-1][6])
            logging.info('最后一条K线的开始时间={}，结束时间={}。'.format(utility.timestamp_to_string(begin_time),
                utility.timestamp_to_string(end_time)))

        logging.info('固定开始时间={}，固定结束时间={}。'.format(utility.timestamp_to_string(FIXED_BEGIN_TIMESTAMP),
            utility.timestamp_to_string(FIXED_END_TIMESTAMP)))

        for kline in klines :
            kline[0] = FIXED_BEGIN_TIMESTAMP
            kline[6] = FIXED_END_TIMESTAMP

            begin_time = int(kline[0])
            end_time = int(kline[6])

            cross, status, timeinfo, infos = self.processor.update_kline(list(kline))
            if status == base_item.TRADE_STATUS.BUY or status == base_item.TRADE_STATUS.SELL:
                assert(timeinfo == begin_time)
                logging.info('发生交易处理，status={}，cross={}，开始时间={}({})，结束时间={}'.format(status, cross,
                    timeinfo, utility.timestamp_to_string(timeinfo), utility.timestamp_to_string(end_time)))
            elif status == base_item.TRADE_STATUS.HANDLED :
                assert(timeinfo == begin_time)
                logging.info('K线开始时间={}({})，发生交叉但已被处理过，忽略。'.format(timeinfo, 
                    utility.timestamp_to_string(timeinfo)))
            else :
                assert(status == base_item.TRADE_STATUS.IGNORE)
                logging.info('通知：忽略该K线(无交叉)，开始时间={}，结束时间={}'.format(utility.timestamp_to_string(begin_time),
                    utility.timestamp_to_string(end_time)))
                pass
        logging.debug('fake minotor结束。')
        return
    def run(self) :
        if not self._prepare_online():
            return
        time.sleep(1)
        self._monitor()
        self._finish()
        return
    def fake_run(self) : 
        #HISTORY_END为最后一条K线的结束时间
        HISTORY_END = datetime(year=2025, month=1, day=15)
        end = int(HISTORY_END.timestamp()) * 1000
        if not self._prepare_offline(end) :
            return
        time.sleep(1)
        ATTACK_HOURS = 24
        begin = self.processor.get_time_end(-1) + 1
        #end = begin + attack_su.get_unit_seconds() * 1000
        end = begin + ATTACK_HOURS * 60 * 60 * 1000
        self._fake_monitor(base_item.save_unit(base_item.kline_interval.h1), begin, end)
        self._finish()
        return

def monitor(OWNER : bool = False) -> bool :
    if OWNER :
        print('Active Monitor Start, OWNER={}...'.format(OWNER))
        if platform.system().upper() == 'WINDOWS':
            signal.signal(signal.SIGINT, exit_gracefully)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        elif platform.system().upper() == 'LINUX':
            signal.signal(signal.SIGINT, exit_gracefully)
            signal.signal(signal.SIGTERM, exit_gracefully)
        log_adapter.log_to_console(level=logging.INFO)
        log_adapter.log_to_file('Active_Monitor', level=logging.DEBUG)
    else :
        logging.debug('Active Monitor Start, OWNER={}...'.format(OWNER))

    su = base_item.save_unit(base_item.kline_interval.d1)
    monitor = active_monitor(su)
    dns_valid = monitor.bsw.check_DNS()
    if not dns_valid :
        logging.error('DNS解析失败，退出。')
        return False
    logging.info('DNS解析成功。')
    server_time = monitor.bsw.get_server_time()
    if server_time == 0 :
        logging.error('获取服务器时间失败，退出。')
        return False
    logging.info('获取服务器时间={}'.format(utility.timestamp_to_string(server_time)))

    monitor.run()
    #monitor.fake_run()

    if OWNER :
        print('Active Monitor End.')
        pass
    else :
        logging.debug('Active Monitor End.')
    return True

#目前采用的币安监控处理器
monitor(OWNER=True)
