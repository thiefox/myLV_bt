#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Module: config

"""

import json


class Config:
    def __init__(self):
        self.market: str = "spot"  # 交易的平台, spot/cm_future/um_future         
        #"platform": "binance_spot",
        self.streams: list = None  # 订阅的交易K线列表，见配置文件

        #API key，如采用HMAC SHA256,则是服务端提供。如才有ED25519，则是LOCAL提供给服务端。
        self.api_key: str = None            
        self.api_key_type: str = None       #ED25519 or HMAC
        self.secret_path: str = None        #私钥文件路径？

        self.api_secret: str = None
        self.private_key: str = None
        self.private_key_pass: str = None

        self.pass_phrase = None
        self.symbol = "BTCUSDT"
        # 网格模型参数
        # gap_percent是价格区间，这里设置了5%，即价格波动上下5%，会触发买卖
        self.gap_percent = 0.05             # 网格间隔grid percent
        # 通用参数
        self.quantity = 200                 # 每个订单里的交易数量
        # 服务商规定的参数
        self.min_price = 0.001              # 服务商规定的最小价格单位，参照币种的最小价格单位，比如BTC是小数点后2位
        self.min_qty = 1                    # 服务商规定的每个订单里的最小交易数量
        self.max_orders = 1                 # 服务商规定的允许最多同时存在的挂单数量
        self.proxy_host = ""  # proxy host
        self.proxy_port = 0  # proxy port
        self.dingding_token: str = None  #dingding access_token
        self.dingding_prompt = ""  #钉钉消息提示
    #载入配置文件
    def loads(self, config_file=None):
        """ Load config file.

        Args:
            config_file: config json file.
        """
        configures = {}
        if config_file:
            try:
                with open(config_file) as f:
                    data = f.read()
                    configures = json.loads(data)
            except Exception as e:
                print(e)
                exit(0)
            if not configures:
                print("config json file error!")
                exit(0)
        self._update(configures)
    #读取配置数据
    def _update(self, update_fields : dict):
        """
        更新update fields.
        :param update_fields:
        :return: None
        """
        for k, v in update_fields.items():
            setattr(self, k, v)

        try:
            if self.api_key_type == "HMAC":         #HMAC SHA256签名
                with open(self.secret_path, 'r') as f:
                    self.api_secret = f.read().strip('\n')
            else:
                with open(self.secret_path, 'rb') as f:
                    self.private_key =  f.read() 
        except Exception as e:
            print(e)
            exit(0)

#config实例
config = Config()
