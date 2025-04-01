# coding=utf-8

import numpy as np
import pandas as pd

import logging

import base_item
import data_loader

from com_utils import config

import binance_spot_wrap

'''
价格中枢设定为：前一交易日的收盘价
从阻力位到压力位分别为：1.03 * open、1.02 * open、1.01 * open、open、0.99 * open、0.98 * open、0.97 * open
每变动一个网格，交易量变化100个单位
'''

class grid_process(object):
    def __init__(self, config : config.Config):
        self.__config = config
        logging.info('初始化网格交易策略，MAX={}, 当前持仓={}...'.format(self.__config.grid_model.max, self.__config.grid_model.holders))
        # 策略标的为SHFE.rb1901
        self.SYMBOL = base_item.trade_symbol.BTCUSDT
        # 订阅SHFE.rb1901, bar频率为1min
        #subscribe(symbols = self.symbol, frequency='60s')
        # 每变动一格，增减的数量
        self.VOLUME = float(0.1)
        # 储存前一个网格所处区间，用来和最新网格所处区间作比较
        self.last_grid = 0
        # 以前一日的收盘价为中枢价格
        self.__center = float(0)
        # 记录上一次交易时网格范围的变化情况（例如从4区到5区，记为4,5）
        self.grid_change_last = [0,0]       #固定前小后大，防止两个区间来回跳动
        self.MAX_HOLDER = float(1)          # 最大持仓量，超过平仓
        self.__holders = self.__config.grid_model.holders          # 通过grid模块买入的总持仓量，需要写入配置文件

    def update_benchmark_price(self, price : float) -> None:
        """
        更新基准价格
        :param price: 基准价格
        :return: None
        """
        self.__center = price
        return

    @property
    def holders(self) -> float:
        """
        获取当前持仓量
        :return: 当前持仓量
        """
        return self.__holders

    #市价买单，如果amount=0，则满仓买入
    #返回dict有效则成功，None为买入失败
    def buy_market(self, amount : float = 0) -> dict:
        bsw = binance_spot_wrap.binance_spot_wrapper()
        if bsw.init() :
            amount = amount if amount > 0 else self.VOLUME
            return bsw.buy_with_market(self.SYMBOL.get_base(), amount)
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
            amount = amount if amount > 0 else self.VOLUME
            return bsw.sell_with_market(self.SYMBOL.get_base(), amount)
        else :
            infos = dict()
            infos['local_code'] = -1
            infos['local_msg'] = 'bsw初始化失败'
            return infos

    # 每分钟调用process处理器
    def on_process(self, kline):
        if self.__center <= 0:
            logging.error('网格交易策略未初始化基准价格，无法进行网格交易。')
            return
        assert(self.__center > 0)
        cur_price = round(float(kline[4]), 2)  # 最新价格
        # 获取当前仓位
        # 设置网格和当前价格所处的网格区域
        self.band = np.array([0.97, 0.98, 0.99, 1, 1.01, 1.02, 1.03]) * self.__center
        self.band = np.array([0.94, 0.96, 0.98, 1, 1.02, 1.04, 1.06]) * self.__center

        grid = pd.cut([cur_price], self.band, labels=[1, 2, 3, 4, 5, 6])[0]
        # 如果价格超出网格设置范围，则提示调节网格宽度和数量
        if np.isnan(grid):
            logging.info('当前价格={}，波动超过网格范围，可适当调节网格宽度和数量。'.format(cur_price))
        # 如果新的价格所处网格区间和前一个价格所处的网格区间不同，说明触碰到了网格线，需要进行交易
        # 如果新网格大于前一天的网格，做空或平多
        logging.info('当前网格={}，前一个网格={}'.format(grid, self.last_grid))
        if self.last_grid < grid:
            # 记录新旧格子范围（按照小大排序）
            grid_change_new = [self.last_grid, grid]
            # 几种例外：
            # 当last_grid = 0 时是初始阶段，不构成信号
            # 如果此时grid = 3，说明当前价格仅在开盘价之下的3区域中，没有突破网格线
            # 如果此时grid = 4，说明当前价格仅在开盘价之上的4区域中，没有突破网格线
            if self.last_grid == 0:
                self.last_grid = grid
                return
            assert(self.last_grid != 0)
            # 如果前一次开仓是4-5，这一次是5-4，算是没有突破，不成交
            if grid_change_new != self.grid_change_last:
                # 更新前一次的数据
                self.last_grid = grid
                self.grid_change_last = grid_change_new
                assert(self.holders >= 0)
                # 向上突破网格线
                if self.holders == 0:
                    # 当前持仓量为0，启动建仓
                    logging.info('网格向上突破，当前未持仓，触发买入...')
                    infos = self.buy_market(self.VOLUME)
                    if infos['local_code'] == 0:
                        self.__holders += self.VOLUME
                        self.__config.update_grid_holders(self.holders)
                        logging.info('网格向上突破，初始化建仓数量=（{}）成功。'.format(self.VOLUME))
                    else:
                        logging.error('网格向上突破，初始化建仓数量=（{}）失败。code={}，msg={}。'.format(self.VOLUME,
                            infos['local_code'], infos['local_msg']))
                else:
                    # 平多（卖出）或开空
                    logging.info('网格向上突破，当前持仓量={}，触发卖出...'.format(self.holders))
                    infos = self.sell_martket(self.VOLUME)
                    if infos['local_code'] == 0:
                        self.__holders -= self.VOLUME
                        self.__config.update_grid_holders(self.__holders)
                        logging.info('网格向上突破，卖出数量=（{}）成功，剩余持仓=（{}）。'.format(self.VOLUME, self.holders))
                    else:
                        logging.error('网格向上突破，卖出数量=（{}）失败，当前持仓={}。code={}，msg={}。'.format(self.VOLUME,
                            self.holders, infos['local_code'], infos['local_msg']))

        # 如果新网格小于前一天的网格，做多或平空
        elif self.last_grid > grid:
            # 记录新旧格子范围（按照小大排序）
            grid_change_new = [grid, self.last_grid]
            # 几种例外：
            # 当last_grid = 0 时是初始阶段，不构成信号
            # 如果此时grid = 3，说明当前价格仅在开盘价之下的3区域中，没有突破网格线
            # 如果此时grid = 4，说明当前价格仅在开盘价之上的4区域中，没有突破网格线
            if self.last_grid == 0:
                self.last_grid = grid
                return
            assert(self.last_grid != 0)
            # 如果前一次开仓是4-5，这一次是5-4，算是没有突破，不成交
            if grid_change_new != self.grid_change_last:
                # 更新前一次的数据
                self.last_grid = grid
                self.grid_change_last = grid_change_new
                # 向下突破网格线
                if self.holders + self.VOLUME >= self.MAX_HOLDER:
                    logging.info('网格向下突破，当前持仓量={}，触发平仓...'.format(self.holders))
                    infos = self.sell_martket(self.holders)
                    if infos['local_code'] == 0:
                        self.__holders = 0
                        self.__config.update_grid_holders(self.__holders)
                        logging.info('网格向下突破，平仓数量=（{}）成功。'.format(self.holders))
                    else:
                        logging.error('网格向下突破，平仓数量=（{}）失败。code={}，msg={}。'.format(self.holders,
                            infos['local_code'], infos['local_msg']))
                else:
                    # 平空（买入）或开多
                    logging.info('网格向下突破，当前持仓量={}，触发买入...'.format(self.holders))
                    infos = self.buy_market(self.VOLUME)
                    if infos['local_code'] == 0:
                        self.__holders += self.VOLUME
                        self.__config.update_grid_holders(self.__holders)
                        logging.info('网格向下突破，买入数量=（{}）成功，剩余持仓=（{}）。'.format(self.VOLUME, self.holders))
                    else:
                        logging.error('网格向下突破，买入数量=（{}）失败，当前持仓={}。code={}，msg={}。'.format(self.VOLUME,
                            self.holders, infos['local_code'], infos['local_msg']))



