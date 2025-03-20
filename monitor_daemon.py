import time
import sys
import signal
import os
import platform
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

from service import Service

#sys.path.append("/usr/local/lib/python3.13/site-packages")

#PATH_CUR_DIR = os.path.dirname(os.path.realpath(__file__))
#sys.path.append(PATH_CUR_DIR)

sys.path.append("/py_default/myLV_bt") 

import com_utils.log_adapter as log_adapter
import com_utils.utility as utility

import active_monitor
import base_item
import binance_spot_wrap

def exit_gracefully(signum, frame):
    print('daemon received signal %d' % signum)
    #global GRACE_EXIT
    #GRACE_EXIT = True
    sys.exit(0)
    return

def mount_signal() :
    if platform.system().upper() == 'WINDOWS':
        signal.signal(signal.SIGINT, exit_gracefully)
        signal.signal(signal.SIGTERM, exit_gracefully)
        #signal.signal(signal.SIGTERM, signal.SIG_IGN)
    elif platform.system().upper() == 'LINUX':
        signal.signal(signal.SIGINT, exit_gracefully)
        signal.signal(signal.SIGTERM, exit_gracefully)
        #signal.signal(signal.SIGQUIT, exit_gracefully)
        #signal.signal(signal.SIGHUP, exit_gracefully)            
    return

class TaskService(Service):
    def __init__(self, *args, **kwargs):
        assert(isinstance(kwargs, dict))
        '''
        singals = kwargs.get('signals', [])
        singals.append(signal.SIGTERM)
        singals.append(signal.SIGINT)
        kwargs['signals'] = singals
        '''
        #print('TaskService init..., *args={}, **kwargs={}'.format(args, kwargs))
        super(TaskService, self).__init__(*args, **kwargs, )
        return

    def prepare(self):
        log_adapter.log_to_file('daemon', level=logging.DEBUG)
        # 确定应用程序是脚本文件还是被冻结的exe
        if getattr(sys, 'frozen', False):
            # 获取应用程序exe的路径
            path = os.path.dirname(sys.executable)
            logging.info('frozen path={}'.format(path))
        elif __file__:
            # 获取脚本程序的路径
            path = os.path.dirname(__file__) 
            logging.info('script path={}'.format(path))

        path = os.path.dirname(os.path.realpath(sys.executable))
        logging.info('real path of sys.executalbe={}'.format(path))
        path = os.path.dirname(os.path.realpath(sys.argv[0]))
        logging.info('real path of sys.argv[0]={}'.format(path))
        logging.info('current path(getcwd)={}'.format(os.getcwd()))
        logging.info('sys.prefix={}'.format(sys.prefix))
        logging.info('sys.executable={}'.format(sys.executable))
        logging.info('sys.path[0]={}'.format(sys.path[0]))
        return

        cur_path = os.getcwd()
        #print('cur_path={}'.format(cur_path))
        log_path = os.path.join(cur_path, 'log')
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 
        log_file = os.path.join(log_path, 'daemon-{}.txt'.format(str_now))
        #print('log_file={}'.format(log_file))
        #RotatingFileHandler是按文件大小切割，TimedRotatingFileHandler是按时间切割
        file_handler = RotatingFileHandler(log_file, mode='w', encoding='utf-8', maxBytes=1024*1024, backupCount=2)
        #file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info('FIRST LOG AFTER ADDHANDLER.')
        logging.info('Write by system logger.')
        return

    def process(self) :
        logging.info('daemon process start...')
        #mount_signal()
        try :
            logging.info('begin am.monitor...')

            su = base_item.save_unit(base_item.kline_interval.d1)
            logging.info('create monitor...')
            monitor = active_monitor.active_monitor(su)
            logging.info('mount got_sigterm...')
            monitor.outer_exit_check_func = self.got_sigterm
            logging.info('检查DNS是否工作正常...')
            dns_valid = monitor.bsw.check_DNS()
            if not dns_valid :
                logging.error('DNS解析失败，退出。')
                return
            logging.info('DNS解析成功。')
            logging.info('获取服务器时间...')
            server_time = monitor.bsw.get_server_time()
            if server_time == 0 :
                logging.error('获取服务器时间失败，退出。')
                return 
            logging.info('获取服务器时间={}'.format(utility.timestamp_to_string(server_time)))
            logging.info('开始运行monitor.run...')
            monitor.run()
            logging.info('monitor.run结束。')
            #monitor.fake_run()
        except Exception as e:
            logging.error('daemon process异常，error:{}'.format(e))

        logging.info('daemon process end.')
        return

    def run(self):
        self.process()
        '''
        COUNT = 30
        while not self.got_sigterm():
            self.logger.info("I'm working...")
            logging.info("i'm working Write by system logger.")
            time.sleep(5)
            COUNT -= 1
            if COUNT <= 0:
                break
        self.logger.info("I'm done. COUNT={}".format(COUNT))
        '''
        return


if __name__ == '__main__':

    if len(sys.argv) != 2:
        sys.exit('缺少参数。执行命令: %s COMMAND(start/stop/kill/pid/status)' % sys.argv[0])

    cmd = sys.argv[1].lower()
    #service = TaskService('my_service', pid_dir='/tmp')
    service = TaskService('', pid_dir='/tmp')       #输入name会导致不能接收root logger的日志

    if cmd == 'start':
        try :
            #mount_signal()
            if not service.is_running() :
                service.prepare()
            service.start()
        except Exception as e:
            print('start error:{}'.format(e))
    elif cmd == 'stop':
        try :
            service.stop()
        except Exception as e:
            print('stop error:{}'.format(e))
    elif cmd == 'kill':
        try :
            service.kill()
        except Exception as e:
            print('kill error:{}'.format(e))
    elif cmd == 'pid':
        print(service.get_pid())
    elif cmd == 'status':
        if service.is_running():
            print("Service is running.")
        else:
            print("Service is not running.")
    else:
        sys.exit('未知参数 "%s".' % cmd)