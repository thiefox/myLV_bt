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
from processor_template import processor_T, UPDATE_KLINE_RESULT, UPDATE_TRADE_RESULT 
import grid_process
import data_loader
import mail_template

import socket

#from binance import BinanceSpotHttp
#from binance import authentication
#import binance.binance_spot as bs
import binance_spot_wrap as bsw

GRACE_EXIT = False

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
        macd_enable = 0
        macd_item = self.config.get_macd(self.symbol.value, base_item.kline_interval.d1.value)
        if macd_item is not None :
            macd_enable = macd_item.enable
        grid_enable = self.config.grid_model.enable
        logging.critical('MACD处理器的enable={}，网格处理器的enable={}。'.format(macd_enable, grid_enable))

        self.master = None
        if macd_enable == 1:
            MACD_su = base_item.save_unit(base_item.kline_interval.d1)
            #3分钟获取一次日线K线数据
            MACD_su.query_interval = 3 * 60 * 1000
            assert(MACD_su.query_interval == base_item.kline_interval.m3.get_interval_seconds() * 1000)
            self.master = MACD_process.MACD_processor(self.symbol, MACD_su, self.config)

        self.workers = list[processor_T]()
        if grid_enable == 1 :
            grid_su = base_item.save_unit(base_item.kline_interval.m3)
            grid_processor = grid_process.grid_process(self.symbol, grid_su, self.config)
            self.workers.append(grid_processor)
        if self.master is None and len(self.workers) == 0 :
            logging.error('没有可用的处理器，退出。')
            sys.exit(-1)
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
    #加载历史数据
    #END: 0表示不指定结束时间，否则表示指定的结束时间。ONLINE=False时有效。
    def _prepare(self, ONLINE : bool, END : int = 0) -> bool:
        if not self._general_prepare():
            return False
        CONTROLED = False
        if self.master is not None :
            result = self.master.prepare(ONLINE, END)
            if result == processor_T.PREPARE_CONTROLED :
                CONTROLED = True
            elif result == processor_T.PREPARE_RELEASED :
                CONTROLED = False
            elif result == processor_T.PREPARE_FAILED :
                logging.error('主处理器{}准备失败。'.format(self.master.name))
                return False
            else :
                assert(False)
        for processor in self.workers :
            result = processor.prepare(ONLINE, END)
            if result == processor_T.PREPARE_OK :
                processor.enable = not CONTROLED
                logging.info('处理器{}准备完成，enable={}。'.format(processor.name, processor.enable))
            elif result == processor_T.PREPARE_FAILED :
                logging.error('处理器{}准备失败。'.format(processor.name))
                return False
            else :
                assert(False)
        return True
    def _finish(self) :
        self.config.saves()
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
    
    def update_mail_asset(self, mail : mail_template.mail_content) -> None:
        price = self.bsw.get_price(self.symbol.get_base())
        balances = self.bsw.get_all_balances()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        mail.update_balance(now_str, balances, price)
        return

    def _daily_notify(self) :
        now = datetime.now()
        infos = list[str]()
        #if now.hour == 12 and now.day > self.last_notify.day :
        if now.hour != self.last_notify.hour :
            logging.info('定期报告，当前时间={}。'.format(now.strftime('%Y-%m-%d %H:%M:%S')))
            infos.append('定期报告，当前时间={}。'.format(now.strftime('%Y-%m-%d %H:%M:%S')))
            mail = mail_template.mail_content('thiefox@qq.com')
            if self.master is not None :
                infos.extend(self.master.daily_report())
            for processor in self.workers :
                infos.extend(processor.daily_report())

            #infos.extend(self.MACD_processor.daily_report())
            price = self.bsw.get_price(self.symbol)
            infos.append('当前{}价格={}$。'.format(self.symbol.value, price))
            logging.info('开始获取账户余额信息...')
            balances = self.bsw.get_all_balances()
            logging.info('获取账户余额信息完成。')
            btc_total = float(0)
            usdt_asset = float(0)
            for balance in balances :
                if balance['asset'] == 'USDT' :
                    usdt_asset = round(float(balance['free']) + float(balance['locked']), 2)
                    if float(balance['locked']) > 0:
                        infos.append('USDT余额={}$，free={}$，lock={}$。'.format(usdt_asset, round(balance['free'], 2), round(balance['locked'], 2)))
                    else :
                        infos.append('USDT余额={}$。'.format(usdt_asset))
                elif balance['asset'] == 'BTC' :
                    btc_total = round(float(balance['free']) + float(balance['locked']), 5)
                    if float(balance['locked']) > 0 :
                        infos.append('BTC余额={}个，free={}个，lock={}个。'.format(btc_total, round(balance['free'], 5), round(balance['locked'], 5)))
                    else :
                        infos.append('BTC余额={}个。'.format(btc_total))

            btc_asset = round(btc_total * price, 2)
            total_asset = round(usdt_asset + btc_asset, 2)
            infos.append('当前USDT余额={}$，BTC数量={}，价值={}$，总资产={}$。'.format(usdt_asset, btc_total, btc_asset, total_asset))
            msg = '\n'.join(infos)
            if mail.write_mail('定期通报-{}$'.format(int(price)), msg) :
                logging.info('日报通知发送成功。')
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

    # 返回=0，表示当前时间该处理器不需要处理
    # 返回=1，表示WORKER进行了处理
    # 返回=2，表示MASTER进入了控制态->所有workers必须停止工作
    # 返回=3，表示MASTER释放控制->所有workers可以开始工作
    # 返回=-1，异常
    def _processor_run(self, processor : processor_T) -> int:
        result = 0
        ts_begin, count, inter = processor.need_query()
        if ts_begin >= 0 and count > 0 :
            result = 1
            if count > 1 :
                logging.error('异常：暂不支持的数量。处理器{}需要查询K线数据，开始时间={}，数量={}，间隔={}。'.format(processor.name,
                    utility.timestamp_to_string(ts_begin), count, inter.value))
                result = -1
                assert(False)
            if ts_begin > 0 :
                logging.info('处理器{}需要查询K线数据，开始时间={}，数量={}，间隔={}。'.format(processor.name,
                    utility.timestamp_to_string(ts_begin), count, inter.value))
            else :
                logging.info('处理器{}需要查询最新K线数据，数量={}，间隔={}。'.format(processor.name, count, inter.value))
            klines = kline_spider.get_klines(processor.symbol, inter, ts_begin, count)
            if len(klines) == 0:
                logging.error('处理器{}获取实时K线数据失败，开始={}，数量={}。'.format(processor.name, utility.timestamp_to_string(ts_begin), count))
                result = -1
            else :
                logging.info('获取到实时K线数据记录={}'.format(len(klines)))
                assert(len(klines) == 1)
                begin_time = int(klines[0][0])
                end_time = int(klines[0][6])
                s_bt = utility.timestamp_to_string(begin_time)
                s_et = utility.timestamp_to_string(end_time)
                end_price = round(float(klines[0][4]), 2)
                logging.info('处理器{}获取到最新K线数据，开始时间={}，结束时间={}，结束价格={}。'.format(processor.name, s_bt, s_et, end_price))
                kline = data_loader.get_kline_shape(klines)         #标准化处理
                ukr, infos = processor.update_kline(kline, inter)
                if processor.is_master() :
                    #worker处理器的K线数据更新
                    if ukr.is_controled() :
                        #logging.info('主处理器{}进入控制态，所有worker停止工作。'.format(processor.name))
                        result = 2
                    elif ukr.is_released() :
                        #logging.info('主处理器{}释放控制态，所有worker可以开始工作。'.format(processor.name))
                        result = 3
                    else :
                        logging.error('主处理器{}异常，未进入控制态或释放控制态。'.format(processor.name))
                        result = -1
                #timeinfo和begin_time不一定相同，比如timeinfo可能处理的是上一条固化K线
                if ukr.is_K_success():      #K线数据正常
                    if ukr.trade.happened() :   #发生了交易动作，可能成功可能失败
                        logging.info('处理器{}在({})K线={}发生交易处理，status={}，reason={}，info={}'.format(processor.name, 
                            inter.value, s_bt, ukr.trade.status, ukr.trade.reason, ukr.trade.info))
                        mail = mail_template.mail_content('thiefox@qq.com')
                        mail.processor = processor.name
                        mail.update_trade(s_bt, ukr.trade, infos)
                        self.update_mail_asset(mail)
                        if not mail.send_mail() :
                            logging.critical('处理器{}在K线={}发生了交易动作，发送邮件失败。'.format(processor.name, s_bt))
                    elif ukr.trade.handled() :
                        logging.info('处理器{}在（{}）K线={}已发生过交易动作1，忽略。'.format(processor.name, inter.value, s_bt))
                    else :
                        logging.debug('该K线不构成交易，开始时间={}，结束价格={}'.format(s_bt, end_price))
                        pass
                else :
                    logging.debug('K线开始时间={}，update_kline返回K线异常={}。'.format(s_bt, ukr.KR))
                    pass
        else :
            logging.debug('处理器{}不需要查询最新K线数据, master={}, controled={}。'.format(processor.name, processor.is_master(), processor.is_controled()))
        #logging.debug('处理器{}的处理结果={}'.format(processor.name, result))        
        return result

    def _monitor(self) :
        
        logging.debug('minotor开始...')
        self.monitor_begin = datetime.now()
        if self.master is not None :
            logging.info('主处理器{}共缓存了{}条K线数据。'.format(self.master.name, self.master.K_len))
            if self.master.K_len > 0 :
                logging.info('{}'.format(self.master.print_kline(0)))
            if self.master.K_len > 1 :
                logging.info('{}'.format(self.master.print_kline(-1)))
        for processor in self.workers :
            logging.info('处理器{}共缓存了{}条K线数据。'.format(processor.name, processor.K_len))
            if processor.K_len > 0 :
                logging.info('{}'.format(processor.print_kline(0)))
            if processor.K_len > 1 :
                logging.info('{}'.format(processor.print_kline(-1)))
        MAX_FAILED = 0
        fail_count = 0
        while True:
            if self._need_exit() :
                logging.info('_need_exit返回True，退出循环。')
                break
            worker_run = False
            if self.master is not None :
                result = self._processor_run(self.master)
                logging.info('主处理器{}的处理结果={}'.format(self.master.name, result))
                if result == 2 :
                    #主处理器处于控制态，所有worker都需要停止工作
                    worker_run = False
                elif result == 3 :
                    #主处理器释放控制态，所有worker都可以开始工作
                    worker_run = True
                elif result == 0 :
                    worker_run = not self.master.is_controled()
                elif result == -1 :
                    fail_count += 1
                    logging.error('主处理器{}返回异常={}，fail_count={}。'.format(self.master.name, result, fail_count))
                    if MAX_FAILED > 0 and fail_count >= MAX_FAILED :
                        logging.critical('达到最大错误次数，退出监控。')
                        break
                    else :
                        continue
            else :
                logging.critical('主处理器不存在，所有workers工作。')
                worker_run = True
            
            for processor in self.workers :
                #logging.critical('对处理器{}进行enable置位为{}...'.format(processor.name, worker_run))
                processor.enable = worker_run

            if worker_run :
                #logging.info('主处理器释放控制态，所有worker处理器开始工作...')
                for processor in self.workers :
                    result = self._processor_run(processor)
                    if result == 0 :
                        logging.debug('worker处理器{}不需要查询最新K线数据。'.format(processor.name))
                    elif result == 1 :
                        pass
                    else :
                        fail_count += 1
                        logging.error('worker处理器{}返回异常={}，fail_count={}。'.format(processor.name, result, fail_count))
                        if MAX_FAILED > 0 and fail_count >= MAX_FAILED :
                            logging.critical('达成最大错误次数，退出监控。')
                            break
                if MAX_FAILED > 0 and fail_count >= MAX_FAILED :
                    break
            else :
                #logging.info('主处理器进入控制态，所有worker处理器暂停工作。')
                pass

            #time.sleep(1)
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
    def _fake_monitor(self) :
        logging.debug('fake minotor开始...')
        for processor in self.workers :
            logging.info('开始打印处理器{}的头尾K线数据...'.format(processor.name))
            logging.info('{}'.format(processor.print_kline(0)))
            logging.info('{}'.format(processor.print_kline(-1))) 
            attack_su, begin, end = processor.get_attack_info()
            logging.info('处理器{}的attack_su={}，开始时间={}，结束时间={}...'.format(processor.name, attack_su.interval.value,
                utility.timestamp_to_string(begin), utility.timestamp_to_string(end)))
            if begin == 0 or end == 0 :
                logging.info('处理器{}的开始时间或结束时间无效，忽略该处理器。'.format(processor.name))
                continue
            attack_k_begin = attack_su.interval.get_K_begin()
            logging.info('处理器{}的attack_k_begin={}...'.format(processor.name, utility.timestamp_to_string(attack_k_begin)))

            klines = data_loader.load_klines_range(processor.symbol, attack_su,
                utility.timestamp_to_datetime(begin), utility.timestamp_to_datetime(end))
            if len(klines) == 0:
                logging.critical('离线获取下级单位的增量K线数据失败。')
            else :    
                logging.info('离线获取下级单位，共获取到K线数据记录={}。'.format(len(klines)))
                FIXED_BEGIN_TIMESTAMP = FIXED_END_TIMESTAMP = 0
                FIXED_BEGIN_AND_END = False
                if FIXED_BEGIN_AND_END :
                    #如果需要固定开始和结束时间，则将所有K线的开始和结束时间都设置为同一个时间点
                    FIXED_BEGIN_TIMESTAMP = int(klines[0][0])
                    #这里非attack su
                    FIXED_END_TIMESTAMP = int(processor.su.interval.get_delta().total_seconds()) * 1000 + begin_time

                for kline in klines :
                    if FIXED_BEGIN_AND_END :
                        kline[0] = FIXED_BEGIN_TIMESTAMP
                        kline[6] = FIXED_END_TIMESTAMP

                    begin_time = int(kline[0])
                    end_time = int(kline[6])
                    #kline = data_loader.get_kline_shape(kline)
                    ukr, infos = processor.update_kline(kline, processor.su.interval)
                    if ukr.is_K_success() :      #K线数据正常
                        if ukr.trade.happened() :
                            logging.info('处理器{}在({})K线={}发生交易处理，status={}，reason={}，info={}'.format(processor.name, 
                                processor.su.interval.value, utility.timestamp_to_string(begin_time),
                                ukr.trade.status, ukr.trade.reason, ukr.trade.info))
                        elif ukr.trade.handled() :
                            logging.info('处理器{}在（{}）K线={}已发生过交易动作2，忽略。'.format(processor.name, processor.su.interval.value,
                                utility.timestamp_to_string(begin_time)))
                        elif ukr.trade.ignored() :
                            logging.info('处理器{}在（{}）K线={}忽略该K线，开始时间={}，结束时间={}'.format(processor.name, processor.su.interval.value,
                                utility.timestamp_to_string(begin_time), utility.timestamp_to_string(begin_time), utility.timestamp_to_string(end_time)))
                        else :
                            assert(False)
                    else :
                        logging.error('fake K线开始时间={}，update_kline返回K线异常={}。'.format(utility.timestamp_to_string(begin_time), ukr.KR))
        logging.debug('fake minotor结束。')
        return
    def run(self) :
        if not self._prepare(True):
            return
        time.sleep(1)
        self._monitor()
        self._finish()
        return
    def fake_run(self) : 
        #HISTORY_END为最后一条K线的结束时间
        HISTORY_END = datetime(year=2025, month=1, day=15)
        end = int(HISTORY_END.timestamp()) * 1000
        if not self._prepare(False, END=end) :
            return
        time.sleep(1)
        self._fake_monitor()
        self._finish()
        return

g_monitor : active_monitor = None

def exit_gracefully(signum, frame):
    logging.info('active_monitor接收到退出信号={}'.format(signum))
    global GRACE_EXIT
    GRACE_EXIT = True
    global g_monitor
    if g_monitor is not None :
        g_monitor._finish()
        g_monitor = None
    sys.exit(0)
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
    #监控主控器为D1单位
    #子处理器可以有自己的单位，也可以选择复用主控器的单位
    su = base_item.save_unit(base_item.kline_interval.d1)
    global g_monitor
    assert(g_monitor is None)
    g_monitor = active_monitor(su)
    dns_valid = g_monitor.bsw.check_DNS()
    if not dns_valid :
        logging.error('DNS解析失败，退出。')
        return False
    logging.info('DNS解析成功。')
    server_time = g_monitor.bsw.get_server_time()
    if server_time == 0 :
        logging.error('获取服务器时间失败，退出。')
        return False
    logging.info('获取服务器时间={}'.format(utility.timestamp_to_string(server_time)))

    g_monitor.run()
    #monitor.fake_run()

    if OWNER :
        print('Active Monitor End.')
        pass
    else :
        logging.debug('Active Monitor End.')
    return True

#目前采用的币安监控处理器
monitor(OWNER=True)
