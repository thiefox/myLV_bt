#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Module: config

"""

import json


class Config:

    def __init__(self):
        self.market: str = "spot"  # 交易的平台
        self.streams: list = None  # 交易steams
        self.api_key: str = None
        self.api_key_type: str = None
        self.secret_path: str = None
        self.api_secret: str = None
        self.private_key: str = None
        self.private_key_pass: str = None
        self.pass_phrase = None
        self.symbol = "BTCUSDT"
        # gap_percent是价格区间，这里设置了5%，即价格波动上下5%，会触发买卖
        self.gap_percent = 0.05             # 网格间隔grid percent
        self.quantity = 200                 # 每个订单里的交易数量
        self.min_price = 0.001              # 服务商规定的最小价格单位，参照币种的最小价格单位，比如BTC是小数点后2位
        self.min_qty = 1                    # 服务商规定的每个订单里的最小交易数量
        self.max_orders = 1                 # 服务商规定的允许最多同时存在的挂单数量
        self.proxy_host = ""  # proxy host
        self.proxy_port = 0  # proxy port
        self.dingding_token: str = None  #dingding access_token
        self.dingding_prompt = ""  #dingding key_word
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
