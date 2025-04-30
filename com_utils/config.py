#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Module: config
"""
import os
import sys
import platform
import json

import logging

class grid_model:
    def __init__(self):
        self.enable = 0
        self.btc_holders = float(0)
        self.btc_max = float(0)
        self.volume = float(0)
        self.usdt_max = float(0)
        return
    def _load(self, fields : dict):
        for k, v in fields.items():
            setattr(self, k, v)
        return
    def _save(self) -> dict:
        return self.__dict__

class macd_item:
    def __init__(self):
        self.enable = 0
        self.symbol = ''
        self.interval = ''
        self.last_handled_cross = ''
        return
    def _load(self, fields : dict):
        for k, v in fields.items():
            setattr(self, k, v)
        return
    def _save(self) -> dict:
        return self.__dict__

class security :
    def __init__(self):
        self.api_secret = ''
        self.private_key = ''
        return
    def _load(self, file_name : str, BINARY = False) -> str:
        err = ''
        try :
            if BINARY:
                with open(file_name, 'rb') as f:
                    self.private_key = f.read()
            else:
                with open(file_name, 'r') as f:
                    self.api_secret = f.read().strip('\n')
        except Exception as e:
            #print(e)
            #exit(0)
            err = str(e)
        return err
    
class general:
    def __init__(self):
        #以下参数从配置文件读入
        self.market = ""  # 交易的平台，spot/cm_future/um_future         
        self.platform = ""  #交易的类型，binance_spot/binance_future
        # 订阅的交易K线列表，见配置文件
        self.streams = list()   #"btcusdt@kline_6h"/"btcusdt@bookTicker"
        #API key，如采用HMAC SHA256,则是服务端提供。如才有ED25519，则是LOCAL提供给服务端。
        self.api_key = ''
        #self.api_key_type = 'ED25519/HMAC'
        self.api_key_type = ''
        self.secret_path = ''
        self.private_key_pass = ''

        self.pass_phrase = ''
        self.symbol = ""        # 交易对，如"BTCUSDT"
        # 网格模型参数
        # gap_percent是价格区间，这里设置了5%，即价格波动上下5%，会触发买卖
        self.gap_percent = 0.05             # 网格间隔grid percent
        # 通用参数
        self.quantity = 200                 # 每个订单里的交易数量
        # 服务商规定的参数
        self.min_price = 0.001              # 服务商规定的最小价格单位，参照币种的最小价格单位，比如BTC是小数点后2位
        #0.00001
        self.min_qty = 0.0001                    # 服务商规定的每个订单里的最小交易数量
        # 服务商规定的允许最多同时存在的挂单数量，实际exchange_info里好像没有这个参数
        self.max_orders = 1                 
        
        self.proxy_host = ""  # proxy host
        self.proxy_port = 0  # proxy port
        self.dingding_token = ''        #dingding access_token
        self.dingding_prompt = ""  #钉钉消息提示

        self.handled_cross = 0      #已处理的交叉点毫秒时间戳（K线开始时间）
        self.cross_type = ''        #交叉点类型，golden/death
        self.cross_status = ''      #交叉点状态，buy/sell/faild
        return
    def path_trans(self) -> bool :
        if platform.system().upper() == 'LINUX':
            self.secret_path = self.secret_path.replace('\\', '/')
        elif platform.system().upper() == 'WINDOWS':
            self.secret_path = self.secret_path.replace('/', '\\')
        tmp_path = self.secret_path
        if not os.path.exists(tmp_path) or not os.path.isfile(tmp_path):
            cur_dir = os.getcwd()
            tmp_path = os.path.join(cur_dir, self.secret_path)
            if not os.path.exists(tmp_path) or not os.path.isfile(tmp_path):
                tmp_path = os.path.join(os.path.join(sys.path[0], self.secret_path))
                if not os.path.exists(tmp_path) or not os.path.isfile(tmp_path):
                    logging.error('私钥文件={}不存在'.format(self.secret_path))
                    return False
        
        self.secret_path = tmp_path
        logging.info('私钥文件={}'.format(self.secret_path))
        #print('找到私钥文件={}'.format(self.secret_path))

        abs_path = os.path.abspath(self.secret_path)
        logging.info('私钥文件绝对路径={}'.format(abs_path))
        #print('私钥文件绝对路径={}'.format(abs_path))
        assert(os.path.exists(abs_path))
        assert(os.path.isfile(abs_path))
        self.secret_path = abs_path
        return True
    def _load(self, fields : dict):
        for k, v in fields.items():
            setattr(self, k, v)
        return
    def _save(self) -> dict:
        return self.__dict__
    @property
    def mp(self) -> float:
        return self.min_price
    @property
    def mq(self) -> float:
        return self.min_qty
    #取得最小交易数量的小数精度值
    def get_qty_precision(self) -> int:
        s_min = f"{self.min_qty:f}".rstrip('0')
        return len(str(s_min).split('.')[1])

class Config:
    def GET_CONFIG_FILE() -> str:
        CONFIG = 'config_spot.json'
        cf = ''
        # 确定应用程序是脚本文件还是被冻结的exe
        if getattr(sys, 'frozen', False):
            # 获取应用程序exe的路径
            path = os.path.dirname(sys.executable)
            logging.info('frozen path={}'.format(path))
            cf = os.path.join(path, CONFIG)
            if os.path.exists(cf):
                return cf
            path = os.path.dirname(path)
            cf = os.path.join(path, CONFIG)
            if os.path.exists(cf):
                return cf
            return ''
        elif __file__:
            # 获取脚本程序的路径
            path = os.path.dirname(__file__) 
            logging.info('script path={}'.format(path))
            cf = os.path.join(path, CONFIG)
            if os.path.exists(cf):
                return cf
            path = os.path.dirname(path)
            cf = os.path.join(path, CONFIG)
            if os.path.exists(cf):
                return cf
            return ''
        else :
            return ''
        
        path = os.path.dirname(os.path.realpath(sys.executable))
        logging.info('real path of sys.executalbe={}'.format(path))
        path = os.path.dirname(os.path.realpath(sys.argv[0]))
        logging.info('real path of sys.argv[0]={}'.format(path))
        logging.info('current path(getcwd)={}'.format(os.getcwd()))
        logging.info('sys.prefix={}'.format(sys.prefix))
        logging.info('sys.executable={}'.format(sys.executable))
        logging.info('sys.path[0]={}'.format(sys.path[0]))

        cf = os.path.join(os.getcwd(), CONFIG)
        logging.info('检查是否存在配置文件1={}...'.format(cf))
        if os.path.exists(cf):
            return cf
        cf = os.path.join(sys.path[0], CONFIG)
        logging.info('检查是否存在配置文件2={}...'.format(cf))
        if os.path.exists(cf):
            return cf
        cf = os.path.join(os.path.dirname(__file__), CONFIG)
        logging.info('检查是否存在配置文件3={}...'.format(cf))
        if os.path.exists(cf):
            return cf
        return ''

    def __init__(self):
        self.file_name = ''
        self.loaded = False
        self.__general = general()
        self.macds = list[macd_item]()
        self.__security = security()
        self.__grid_model = grid_model()
        return
    @property
    def general(self) -> general:
        return self.__general
    @property
    def api_key(self) -> str:
        return self.general.api_key
    @property
    def private_key(self) -> str:
        return self.__security.private_key
    @property
    def grid_model(self) -> grid_model:
        return self.__grid_model

    #载入配置文件
    def loads(self, file_name = '') -> bool:
        if self.loaded :
            return True
        if file_name == '' : 
            file_name = Config.GET_CONFIG_FILE()
        if not os.path.exists(file_name):
            logging.error('配置文件=({})不存在'.format(file_name))
            return False

        configures = dict()
        if len(file_name) > 0:
            try:
                with open(file_name) as f:
                    data = f.read()
                    configures = json.loads(data)
            except Exception as e:
                logging.error('载入配置文件{}异常={}'.format(file_name, e))
                return False
            
        if len(configures) == 0:
            logging.error('配置文件{}为空'.format(file_name))
            return False

        self.file_name = file_name
        if 'general' in configures:
            self.__general._load(configures['general'])
            self.__general.path_trans()
        err = ''
        if self.__general.api_key_type == "HMAC" :
            err = self.__security._load(self.__general.secret_path)
        else:
            err = self.__security._load(self.__general.secret_path, BINARY=True)
        if len(err) > 0:
            logging.error('载入私钥文件{}失败，原因={}'.format(self.__general.secret_path, err))
            return False
        if 'macds' in configures:
            for macd in configures['macds']:
                item = macd_item()
                item._load(macd)
                self.macds.append(item)
        if 'grid_model' in configures:
            self.__grid_model._load(configures['grid_model'])

        self.loaded = True
        return True

    def saves(self, file_name = ''):
        if file_name == '':
            file_name = self.file_name
        if file_name == '':
            file_name = Config.GET_CONFIG_FILE()
        if file_name == '':
            logging.error('配置文件名为空。')
            return
        configures = {}
        configures['general'] = self.__general.__dict__
        configures['macds'] = list()
        for macd in self.macds:
            configures['macds'].append(macd.__dict__)
        configures['grid_model'] = self.__grid_model.__dict__
        with open(file_name, 'w') as f:
            json.dump(configures, f, indent=2)
        return
    #返回True表示更新成功，False表示不需要更新
    def update_exchange_info(self, symbol : str, min_price : float, min_qty : float) -> bool:
        if self.__general.symbol == symbol:
            if self.__general.min_price != min_price or self.__general.min_qty != min_qty:
                self.__general.min_price = min_price
                self.__general.min_qty = min_qty
                self.saves()
                return True
            else :
                return False
        else :
            return False
    #取得最后处理过的交叉点时间戳
    def get_hc(self) -> tuple[int, str, str]:
        return self.__general.handled_cross, self.__general.cross_type, self.__general.cross_status
    #更新最后处理过的交叉点时间戳
    def update_hc(self, handled_cross : int, cross_type : str, status = str) -> bool:
        assert(isinstance(handled_cross, int))
        assert(isinstance(cross_type, str))
        assert(handled_cross > 0)
        if self.__general.handled_cross != handled_cross:
            self.__general.handled_cross = handled_cross
            self.__general.cross_type = cross_type
            self.__general.cross_status = status
            self.saves()
            return True
    #返回True表示更新成功，False表示不需要更新
    def update_macd(self, symbol : str, interval : str, last_handled_cross : str) -> bool:
        for macd in self.macds:
            if macd.symbol == symbol and macd.interval == interval:
                if macd.last_handled_cross != last_handled_cross:
                    macd.last_handled_cross = last_handled_cross
                    self.saves()
                    return True
                else :
                    return False
        item = macd_item()
        item.symbol = symbol
        item.interval = interval
        item.last_handled_cross = last_handled_cross
        self.macds.append(item)
        self.saves()
        return True
    
    def get_macd(self, symbol : str, interval : str) -> macd_item:
        for macd in self.macds:
            if macd.symbol == symbol and macd.interval == interval:
                return macd
        return None
    
    def update_grid_holders(self, holders : float) -> bool:
        if self.__grid_model.btc_holders != holders:
            self.__grid_model.btc_holders = round(holders, 5)
            self.saves()
        return True

#config实例
#config = Config()
