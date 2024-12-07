#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Module: config
"""
import os
import json

class macd_item:
    def __init__(self):
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
    def _load(self, file_name : str, BINARY = False):
        try :
            if BINARY:
                with open(file_name, 'rb') as f:
                    self.private_key = f.read()
            else:
                with open(file_name, 'r') as f:
                    self.api_secret = f.read().strip('\n')
        except Exception as e:
            print(e)
            exit(0)
        return
    
class general:
    def __init__(self):
        self.market = "spot"  # 交易的平台, spot/cm_future/um_future         
        self.platform = "binance_spot"
        # 订阅的交易K线列表，见配置文件
        self.streams = ["btcusdt@kline_6h", "btcusdt@bookTicker"]
        #API key，如采用HMAC SHA256,则是服务端提供。如才有ED25519，则是LOCAL提供给服务端。
        self.api_key = "XYCWi1jlDJcOPG8MltM0plnPQlmqFd0wuvCKVuokovxlmwXBADoCI7Ea78h6bX2Y"
        self.api_key_type = 'ED25519'
        self.secret_path = "D:/src/python/myLV_bt/data/MYLV_E.pem"        #私钥文件路径？

        self.private_key_pass = ''

        self.pass_phrase = ''
        self.symbol = "BTCUSDT"
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
        return
    def _load(self, fields : dict):
        for k, v in fields.items():
            setattr(self, k, v)
        return
    def _save(self) -> dict:
        return self.__dict__
    #取得最小交易数量的小数精度值
    def get_qty_precision(self) -> int:
        s_min = f"{self.min_qty:f}".rstrip('0')
        return len(str(s_min).split('.')[1])

class Config:
    CONFIG_FILE = "D:/src/python/myLV_bt/config_spot.json"

    def GET_CONFIG_FILE() -> str:
        CONFIG = 'config_spot.json'
        cf = os.path.join(os.getcwd(), CONFIG)
        return cf

    def __init__(self):
        self.file_name = ''
        self.general = general()
        self.macds = list[macd_item]()
        self.__security = security()
        return

    @property
    def api_key(self) -> str:
        return self.general.api_key
    @property
    def private_key(self) -> str:
        return self.__security.private_key

    #载入配置文件
    def loads(self, file_name = '') -> bool:
        if file_name == '':
            file_name = self.CONFIG_FILE

        configures = dict()
        if len(file_name) > 0:
            try:
                with open(file_name) as f:
                    data = f.read()
                    configures = json.loads(data)
            except Exception as e:
                print('错误：载入配置文件{}异常={}'.format(file_name, e))
                return False
            
        if len(configures) == 0:
            print("错误：配置文件{}载入词典失败。".format(file_name))
            return False
        self.file_name = file_name
        if 'general' in configures:
            self.general._load(configures['general'])
        if self.general.api_key_type == "HMAC" :
            self.__security._load(self.general.secret_path)
        else:
            self.__security._load(self.general.secret_path, BINARY=True)

        if 'macds' in configures:
            for macd in configures['macds']:
                item = macd_item()
                item._load(macd)
                self.macds.append(item)
        return True

    def saves(self, file_name = ''):
        if file_name == '':
            file_name = self.file_name
        if file_name == '':
            file_name = Config.GET_CONFIG_FILE()
        if file_name == '':
            print('错误：配置文件名为空')
            return
        configures = {}
        configures['general'] = self.general.__dict__
        configures['macds'] = list()
        for macd in self.macds:
            configures['macds'].append(macd.__dict__)
        with open(file_name, 'w') as f:
            json.dump(configures, f, indent=2)
        return
    #返回True表示更新成功，False表示不需要更新
    def update_exchange_info(self, symbol : str, min_price : float, min_qty : float) -> bool:
        if self.general.symbol == symbol:
            if self.general.min_price != min_price or self.general.min_qty != min_qty:
                self.general.min_price = min_price
                self.general.min_qty = min_qty
                self.saves()
                return True
            else :
                return False
        else :
            return False
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

#config实例
#config = Config()
