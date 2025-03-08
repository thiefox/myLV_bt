import sys
import time
import platform
import signal
import logging
from datetime import datetime, timedelta

from utils import utility
from utils import log_adapter
from utils import config

import base_item
import kline_spider
import MACD_process
import data_loader
import mail_template

#from binance import BinanceSpotHttp
#from binance import authentication
#import binance.binance_spot as bs
import binance_spot_wrap as bsw

DEFAULT_BACK_COUNT = 200

def exit_gracefully(signum, frame):
    print('received signal %d' % signum)
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
        if not self.bsw.init() :
            log_adapter.color_print('异常：初始化币安接口包装器失败。', log_adapter.COLOR.RED)
            return
        assert(self.bsw.is_valid())
        last_handled = 0
        self.config = config.Config()
        if not self.config.loads(config.Config.GET_CONFIG_FILE()):
            log_adapter.color_print('异常：加载配置文件{}失败。'.format(config.Config.GET_CONFIG_FILE()), log_adapter.COLOR.RED)
            return
        last_handled = self.config.general.handled_cross
        if last_handled > 0 :
            log_adapter.color_print('重要：最后的处理交叉点={}'.format(utility.timestamp_to_string(last_handled), log_adapter.COLOR.GREEN))
 
        item = self.config.get_macd(self.symbol, self.__su.interval)
        if item is not None and item.last_handled_cross != '':
            print('重要：最后的处理交叉点1={}'.format(item.last_handled_cross))
            info = datetime.strptime(item.last_handled_cross, '%Y-%m-%d %H:%M:%S') 
            print('重要：最后的处理交叉点2={}'.format(info.strftime('%Y-%m-%d %H:%M:%S')))
            last_handled = info.timestamp() * 1000

        self.processor = MACD_process.MACD_processor(self.symbol, self.config)
        #self.config.update_macd(self.symbol, self.__su.interval, datetime.now().strftime('%Y-%m-%d 00:00:00'))
        return
    
    def _general_prepare(self) -> bool:
        assert(self.bsw.is_valid())
        min_price, min_quantity = self.bsw.get_exchange_params(self.symbol)
        if min_quantity > 0 :
            self.config.update_exchange_info(self.symbol.value, min_price, min_quantity)
            log_adapter.color_print('重要：最小交易数量={}。'.format(self.config.general.min_qty), log_adapter.COLOR.GREEN)
            log_adapter.color_print('重要：最小交易价格={}。'.format(self.config.general.min_price), log_adapter.COLOR.GREEN)
        else :
            log_adapter.color_print('异常：获取minQty={}和minPrice={}交易参数失败。'.format(min_quantity, min_price), log_adapter.COLOR.RED)
            return False
        return True
    #在线模式加载历史数据
    def _prepare_online(self) -> bool:
        if not self._general_prepare():
            return False
        begin = int(datetime.now().timestamp()) * 1000
        offset = self.__su.calc_offset(DEFAULT_BACK_COUNT, begin)
        assert(offset > 0)
        log_adapter.color_print('重要：开始在线获取{}条历史K线数据，开始时间戳={}，结束时间戳={}'.format(DEFAULT_BACK_COUNT,
            utility.timestamp_to_string(offset), utility.timestamp_to_string(begin)), log_adapter.COLOR.GREEN)
        klines = kline_spider.get_klines(base_item.trade_symbol.BTCUSDT, self.__su.interval, offset)
        if len(klines) == 0:
            log_adapter.color_print('异常：在线获取历史K线数据失败', log_adapter.COLOR.RED)
            return False
        log_adapter.color_print('重要：在线初始化共获取到K线数据记录={}，BACK_CN={}'.format(len(klines), DEFAULT_BACK_COUNT), log_adapter.COLOR.GREEN)
        if len(klines) < DEFAULT_BACK_COUNT:
            log_adapter.color_print('异常：在线获取到的历史K线数据记录数少于{}'.format(DEFAULT_BACK_COUNT), log_adapter.COLOR.RED)
            return False
        info = self.processor.init_history(klines)
        log_adapter.color_print('重要：在线初始化历史数据结果={}'.format(info), log_adapter.COLOR.GREEN)
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
        log_adapter.color_print('重要：开始离线获取{}条历史K线数据，开始时间戳={}，结束时间戳={}'.format(DEFAULT_BACK_COUNT, 
            utility.timestamp_to_string(offset), utility.timestamp_to_string(end)), log_adapter.COLOR.GREEN)
        
        klines = data_loader.load_klines_range(base_item.trade_symbol.BTCUSDT, self.__su,
            utility.timestamp_to_datetime(offset), utility.timestamp_to_datetime(end))
        if len(klines) == 0:
            log_adapter.color_print('异常：离线获取历史K线数据失败', log_adapter.COLOR.RED)
            return False
        log_adapter.color_print('重要：离线初始化共获取到K线数据记录={}，BACK_CN={}'.format(len(klines), DEFAULT_BACK_COUNT), log_adapter.COLOR.GREEN)
        if len(klines) < DEFAULT_BACK_COUNT:
            log_adapter.color_print('异常：离线获取到的历史K线数据记录数少于{}'.format(DEFAULT_BACK_COUNT), log_adapter.COLOR.RED)
            return False
        info = self.processor.init_history(klines)
        log_adapter.color_print('重要：离线初始化历史数据结果={}'.format(info), log_adapter.COLOR.GREEN)
        return info >= self.processor.WINDOW_LENGTH
    def _finish(self) :
        return
    #是否需要退出
    def _need_exit(self) -> bool:
        now = datetime.now()
        delta = now - self.monitor_begin
        if self.MONITOR_SECONDS > 0 and delta.total_seconds() >= self.MONITOR_SECONDS:
            print('重要：开始时间={}，当前时间={}，达到结束时间，退出。'.format(datetime.strftime(self.monitor_begin, '%Y-%m-%d %H-%M-%S'), 
                datetime.strftime(now, '%Y-%m-%d %H-%M-%S')))
            return True
        return False
    def _daily_notify(self) :
        now = datetime.now()
        #if now.hour == 12 and now.day > self.last_notify.day :
        if now.hour != self.last_notify.hour :
            print('重要：每日12点日报通知，当前时间={}。'.format(now.strftime('%Y-%m-%d %H:%M:%S')))
            msg = '每日定点通知，当前时间={}。\n'.format(now.strftime('%Y-%m-%d %H:%M:%S'))
            mail = mail_template.mail_content('thiefox@qq.com')
            last_cross = self.processor.get_last_cross()
            last_handled = self.processor.get_last_handled_cross()
            price = self.bsw.get_price(self.symbol)
            if last_handled[0] != base_item.MACD_CROSS.NONE :
                msg += '最后处理的交叉点时间={}，类型={}。\n'.format(utility.timestamp_to_string(last_handled[1]), last_handled[0].value)
            else :
                msg += '最后的历史交叉点时间={}，类型={}。\n'.format(utility.timestamp_to_string(last_cross[1]), last_cross[0].value)
            msg += '当前{}价格={}$。\n'.format(self.symbol.value, price)
            balances = self.bsw.get_all_balances()
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

            if mail.write_mail('定期通报', msg) :
                print('重要：每日12点日报通知发送成功。')
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
        log_adapter.color_print('K线总数={}，K线序号={}，开始时间={}，结束时间={}，开盘价={}，收盘价={}'.format(self.processor.len, index, 
            s_begin, s_end, open_price, close_price), log_adapter.COLOR.GREEN)
    def _monitor(self) :
        print('minotor开始...')
        self.monitor_begin = datetime.now()

        self.print_kline(-1)
        begin = self.processor.get_time_begin(-1)
        end = self.processor.get_time_end(-1)
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
            cross, status, timeinfo, infos = self.processor.update_kline(klines)
            if status == base_item.TRADE_STATUS.BUY or status == base_item.TRADE_STATUS.SELL:
                assert(timeinfo == begin_time)
                print('重要：发生交易处理，status={}，cross={}，时间={}({})'.format(status, cross.value,
                    timeinfo, utility.timestamp_to_string(timeinfo)))
                self.config.update_macd(self.symbol, self.__su.interval, utility.timestamp_to_string(timeinfo))
                mail = mail_template.mail_content('thiefox@qq.com')
                if infos['local_code'] == 0:
                    mail.update_with_success(utility.timestamp_to_string(timeinfo), cross, infos)
                else :
                    mail.update_with_failed(utility.timestamp_to_string(timeinfo), cross, infos['local_msg'])
                if not mail.send_mail() :
                    if cross.is_golden() :  
                        print('异常：金叉买入失败，发送邮件失败。')
                    else :
                        print('异常：死叉卖出失败，发送邮件失败。')
            elif status == base_item.TRADE_STATUS.FAILED :
                assert(infos['local_code'] == -1)
                print('异常：时间={}发生交叉点，但交易失败，原因={}。'.format(utility.timestamp_to_string(timeinfo), infos['local_msg']))
                mail = mail_template.mail_content('thiefox@qq.com')
                mail.update_with_failed(utility.timestamp_to_string(timeinfo), cross, infos['local_msg'])
                if not mail.send_mail() :
                    print('异常：交易失败，发送邮件失败。')
            elif status == base_item.TRADE_STATUS.HANDLED :
                assert(timeinfo == begin_time)
                print('重要：K线开始时间={}({})，发生交叉但已被处理过，忽略。'.format(timeinfo, utility.timestamp_to_string(timeinfo)))
            else :
                assert(status == base_item.TRADE_STATUS.IGNORE)
                print('通知：忽略该K线(无交叉)，开始时间={}'.format(utility.timestamp_to_string(begin_time)))
                pass
            time.sleep(1)
            self._daily_notify()
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
    #本地模拟的监控处理，用于观察发生交叉点的后续处理是否正常
    def _fake_monitor(self, attack_su : base_item.save_unit, begin : int = 0, end : int = 0) :
        log_adapter.color_print('fake minotor开始...', log_adapter.COLOR.GREEN)
        self.print_kline(-1)
        if begin == 0 :
            begin = self.processor.get_time_end(-1) + 1
            #begin = attack_su.get_unit_begin()
        assert(isinstance(begin, int))

        self_k_begin = self.__su.interval.get_K_begin()
        attack_k_begin = attack_su.interval.get_K_begin()
        log_adapter.color_print('self_k_begin={}，attack_k_begin={}...'.format(utility.timestamp_to_string(self_k_begin),
            utility.timestamp_to_string(attack_k_begin)), log_adapter.COLOR.GREEN)
        if end == 0 :
            end = begin + attack_su.get_unit_seconds() * 1000
        assert(isinstance(end, int))
        log_adapter.color_print('攻击开始时间={}，结束时间={}...'.format(utility.timestamp_to_string(begin),
            utility.timestamp_to_string(end)), log_adapter.COLOR.GREEN)

        klines = data_loader.load_klines_range(base_item.trade_symbol.BTCUSDT, attack_su,
            utility.timestamp_to_datetime(begin), utility.timestamp_to_datetime(end))
        if len(klines) == 0:
            log_adapter.color_print('异常：离线获取下级单位的增量K线数据失败。', log_adapter.COLOR.RED)
            return
        log_adapter.color_print('重要：离线获取下级单位，共获取到K线数据记录={}'.format(len(klines)), log_adapter.COLOR.GREEN)

        FIXED_BEGIN_TIMESTAMP = FIXED_END_TIMESTAMP = 0
        if len(klines) > 0 :
            begin_time = int(klines[0][0])
            FIXED_BEGIN_TIMESTAMP = begin_time
            FIXED_END_TIMESTAMP = int(self.__su.interval.get_delta().total_seconds()) * 1000 + begin_time
            end_time = int(klines[0][6])
            log_adapter.color_print('重要：第一条K线的开始时间={}，结束时间={}。'.format(utility.timestamp_to_string(begin_time),
                utility.timestamp_to_string(end_time)), log_adapter.COLOR.GREEN)
            begin_time = int(klines[-1][0])
            end_time = int(klines[-1][6])
            log_adapter.color_print('重要：最后一条K线的开始时间={}，结束时间={}。'.format(utility.timestamp_to_string(begin_time),
                utility.timestamp_to_string(end_time)), log_adapter.COLOR.GREEN)

        log_adapter.color_print('重要：固定开始时间={}，固定结束时间={}。'.format(utility.timestamp_to_string(FIXED_BEGIN_TIMESTAMP),
            utility.timestamp_to_string(FIXED_END_TIMESTAMP)), log_adapter.COLOR.RED)

        for kline in klines :
            kline[0] = FIXED_BEGIN_TIMESTAMP
            kline[6] = FIXED_END_TIMESTAMP

            begin_time = int(kline[0])
            end_time = int(kline[6])

            cross, status, timeinfo, infos = self.processor.update_kline(list(kline))
            if status == base_item.TRADE_STATUS.BUY or status == base_item.TRADE_STATUS.SELL:
                assert(timeinfo == begin_time)
                log_adapter.color_print('重要：发生交易处理，status={}，cross={}，开始时间={}({})，结束时间={}'.format(status, cross,
                    timeinfo, utility.timestamp_to_string(timeinfo), utility.timestamp_to_string(end_time)), log_adapter.COLOR.GREEN)
                self.config.update_macd(self.symbol, self.__su.interval, utility.timestamp_to_string(timeinfo))
            elif status == base_item.TRADE_STATUS.HANDLED :
                assert(timeinfo == begin_time)
                log_adapter.color_print('重要：K线开始时间={}({})，发生交叉但已被处理过，忽略。'.format(timeinfo, 
                    utility.timestamp_to_string(timeinfo)), log_adapter.COLOR.YELLOW) 
            else :
                assert(status == base_item.TRADE_STATUS.IGNORE)

                print('通知：忽略该K线(无交叉)，开始时间={}，结束时间={}'.format(utility.timestamp_to_string(begin_time),
                    utility.timestamp_to_string(end_time)))
                pass
        log_adapter.color_print('重要：fake minotor结束。', log_adapter.COLOR.GREEN)
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

def test() :
    print("Active Monitor Start...")
    if platform.system().upper() == 'WINDOWS':
        signal.signal(signal.SIGINT, exit_gracefully)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    elif platform.system().upper() == 'LINUX':
        signal.signal(signal.SIGINT, exit_gracefully)
        signal.signal(signal.SIGTERM, exit_gracefully)


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
    #monitor.fake_run()

    if LOG_FLAG == 1 :
        sys.stdout = tmp_out
        sys.stderr = tmp_err
    print("Active Monitor End.")
    return

#目前采用的币安监控处理器
test()
