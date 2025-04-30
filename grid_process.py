# coding=utf-8

import numpy as np
import pandas as pd

import logging
from datetime import datetime
import time

import base_item
import data_loader

from com_utils import config
from com_utils import utility

import binance_spot_wrap as bsw
from processor_template import processor_T, UPDATE_KLINE_RESULT, UPDATE_TRADE_RESULT

'''
价格中枢设定为：前一交易日的收盘价
从阻力位到压力位分别为：1.03 * open、1.02 * open、1.01 * open、open、0.99 * open、0.98 * open、0.97 * open
每变动一个网格，交易量变化100个单位
'''

class grid_process(processor_T):
    UP_EMPTY_BUY = '网格向上突破，空仓触发买入。'
    UP_HOLD_SELL = '网格向上突破，触发卖出。'
    DOWN_FULL_SELL = '网格向下突破，满仓触发平仓止损。'
    DOWN_HOLD_BUY = '网格向下突破，触发买入。'

    def __init__(self, symbol : base_item.trade_symbol, su : base_item.save_unit, cfg : config.Config) -> None:
        super().__init__(symbol, su, cfg, 0)
        super()._set_name('GRID_processor')

        logging.info('初始化网格交易策略，BTC_MAX={}, USDT_MAX={}, VOLUME={}, 当前持仓={}...'.format(super().config.grid_model.btc_max, 
            super().config.grid_model.usdt_max, super().config.grid_model.volume, super().config.grid_model.btc_holders))

        if not self.reset() :
            logging.error('网格交易策略初始化复位失败。')
            assert(False)
        return 
    
    @property
    def holders(self) -> float:
        """
        获取当前持仓量
        :return: 当前持仓量
        """
        return round(self.__holders, 5)
    @property
    def center(self) -> float:
        # 以前一日的收盘价为中枢价格
        return round(float(self.__last_D_Kline[4]), 2) if len(self.__last_D_Kline) > 0 else 0.0
    def reset(self) -> bool:
        # 储存前一个网格所处区间，用来和最新网格所处区间作比较
        self.last_grid = 0
        self.last_price = float(0.0)
        self.__last_D_Kline = list()    # 上一条固化的日线K线数据
        # 记录上一次交易时网格范围的变化情况（例如从4区到5区，记为4,5）
        self.grid_change_last = [0,0]       #固定前小后大，防止两个区间来回跳动
        # 每变动一格，增减的数量
        self.VOLUME = super().config.grid_model.volume  # 每次交易的数量
        self.MAX_HOLDER = super().config.grid_model.btc_max          # 最大持仓量，超过平仓
        self.__holders = float(0.0)          # 当前持仓量，初始化为0
        #self.__holders = round(super().config.grid_model.btc_holders, 5)          # 通过grid模块买入的总持仓量，需要写入配置文件
        self.USDT_MAX = int(super().config.grid_model.usdt_max)        # 最大可用的USDT数量
        if self.VOLUME <= 0 or self.MAX_HOLDER <= 0 or self.VOLUME > self.MAX_HOLDER:
            logging.error('网格交易策略初始化失败，VOLUME={}，MAX_HOLDER={}。'.format(self.VOLUME, self.MAX_HOLDER))
            return False
        if not self.sync_balance() :
            logging.error('网格交易策略初始化失败，无法获取当前持仓量和可用USDT。')
            return False

        self.band = np.array([0.90, 0.92, 0.94, 0.96, 0.98, 1, 1.02, 1.04, 1.06, 1.08, 1.10]) * self.center
        self.band = np.around(self.band, 2)
        return True
    def _enable_action(self) :
        logging.info('网格交易策略enable_action，当前enable状态={}，数据复位...'.format(self._enable))
        self.reset()
        return
    def sync_balance(self) -> bool : 
        bs_wraper = bsw.binance_spot_wrapper()
        if bs_wraper.init() :
            balances = bs_wraper.get_all_balances()
            btc_total = float(0)
            usdt_asset = float(0)
            for balance in balances :
                if balance['asset'] == 'USDT' :
                    usdt_asset = round(float(balance['free']), 2)
                elif balance['asset'] == 'BTC' :
                    btc_total = round(float(balance['free']), 5)
            logging.info('当前可用USDT={}，BTC={}。'.format(usdt_asset, btc_total))
            changed = False
            if self.USDT_MAX > usdt_asset:
                self.USDT_MAX = usdt_asset
                super().config.grid_model.usdt_max = self.USDT_MAX
                changed = True
            '''
            if self.__holders == 0 or self.__holders > btc_total:
                self.__holders = btc_total
                super().config.update_grid_holders(self.__holders)
                changed = True
            '''
            if changed:
                logging.critical('网格交易策略最大可用USDT={}，最大持仓量={}。'.format(self.USDT_MAX, self.MAX_HOLDER))
                super().config.saves()
                logging.info('网格交易策略配置文件保存成功。')
            logging.critical('网格交易策略当前可用USDT={}，当前持币量（忽略）={}。'.format(self.USDT_MAX, btc_total))
            return True
        else :
            return False

    def update_center(self) -> int :
        now = int(datetime.now().timestamp()) * 1000
        NEW = False
        UPDATE = False
        d1 = base_item.kline_interval.d1
        if self.__last_D_Kline is None or len(self.__last_D_Kline) == 0:
            logging.info('当前时间={}，last_D_Kline为空，第一次处理。'.format(utility.timestamp_to_string(now)))
            NEW = True
        else:
            last_begin = self.__last_D_Kline[0]  # 上一日K线的开始时间
            step = d1.calc_step(last_begin, now)
            logging.info('当前时间={}，上次K线开始时间={}，步长={}'.format(utility.timestamp_to_string(now), utility.timestamp_to_string(last_begin), step))
            #if step > 0:
            if step > 1:
                #assert(step == 1)
                UPDATE = True

        if NEW or UPDATE:
            kline = super().query_last_fixed_kline(d1)
            if kline is None or len(kline) == 0:
                logging.error('获取上一日K线数据失败。')
                return -1
            if len(self.__last_D_Kline) > 0:
                if self.__last_D_Kline[0] == kline[0]:
                    logging.error('获取上一日K线数据失败，时间戳重复={}。'.format(utility.timestamp_to_string(kline[0])))
                    assert(False)
                    return -1
                logging.info('缓存的K线开始时间={}，获取的最后固定K线开始时间={}。'.format(utility.timestamp_to_string(self.__last_D_Kline[0]),
                    utility.timestamp_to_string(kline[0])))
            self.__last_D_Kline = kline
            logging.critical('更新价格中枢，NEW={}，K线开始时间={}，收盘价格={}'.format(NEW, utility.timestamp_to_string(self.__last_D_Kline[0]), self.center))   
            # 更新网格范围
            self.band = np.array([0.90, 0.92, 0.94, 0.96, 0.98, 1, 1.02, 1.04, 1.06, 1.08, 1.10]) * self.center
            self.band = np.around(self.band, 2)
            logging.info('重新网格范围设定={}'.format(self.band))
            if UPDATE :
                old_grid = self.last_grid
                self.last_grid = pd.cut([self.last_price], self.band, labels=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10])[0]
                logging.info('中枢价格更新后调整last_grid，old_pos={}，new_pos={}。'.format(old_grid, self.last_grid))
            else :
                assert(self.last_grid == 0)
            return 1         
        else :
            return 0

    def get_grid_inter(self, grid : int) -> tuple[float, float]:
        """
        获取网格区间的上下限
        :param grid: 网格区间
        :return: 上下限价格
        """
        if grid < 0 or grid >= len(self.band):
            return 0, 0
        if grid == 0:
            return 0, self.band[grid]
        elif grid == len(self.band) - 1:
            return self.band[grid - 1], 0
        else :
            return self.band[grid - 1], self.band[grid]

    #重载父类need_query方法
    def need_query(self) -> tuple[int, int, base_item.kline_interval]:
        if super().enable :
            return super().need_query()
        else :
            return -1, 0, super().su.interval

    # 每分钟调用process处理器
    def update_kline(self, kline : list, interval : base_item.kline_interval) -> tuple[UPDATE_KLINE_RESULT, dict]:
        ukr = UPDATE_KLINE_RESULT()
        infos = dict()
        assert(interval.get_unit().lower() == 'm')
        result = self.update_center()
        if result == 0 :
            logging.info('网格交易策略目前不需要更新价格中枢。')
        elif result == -1:
            logging.error('网格交易策略更新价格中枢失败。')
        elif result == 1:
            logging.info('网格交易策略更新价格中枢成功。')
        else:
            logging.critical('异常：update_center返回={}'.format(result))

        if self.center <= 0:
            logging.error('网格交易策略未初始化基准价格，无法进行网格交易。')
            return ukr, infos
        assert(self.center > 0)
        cur_price = round(float(kline[4]), 2)  # 最新价格
        # 获取当前仓位
        # 设置网格和当前价格所处的网格区域
        #self.band = np.array([0.97, 0.98, 0.99, 1, 1.01, 1.02, 1.03]) * self.center
        #self.band = np.array([0.94, 0.96, 0.98, 1, 1.02, 1.04, 1.06]) * self.center

        grid = pd.cut([cur_price], self.band, labels=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10])[0]
        # 如果价格超出网格设置范围，则提示调节网格宽度和数量
        if np.isnan(grid):
            logging.info('当前价格={}，波动超过网格范围，可适当调节网格宽度和数量。'.format(cur_price))
        # 如果新的价格所处网格区间和前一个价格所处的网格区间不同，说明触碰到了网格线，需要进行交易
        # 如果新网格大于前一天的网格，做空或平多
        cur_inter = self.get_grid_inter(grid)
        last_inter = self.get_grid_inter(self.last_grid)
        logging.info('中枢价格={}，当前价格={}，属于网格={}，价格区间=[{} - {}]。前一个网格={}，价格区间=[{} - {}]'.format(self.center, cur_price, 
            grid, cur_inter[0], cur_inter[1], self.last_grid, last_inter[0], last_inter[1]))
        if self.last_grid < grid:
            # 记录新旧格子范围（按照小大排序）
            grid_change_new = [self.last_grid, grid]
            # 几种例外：
            # 当last_grid = 0 时是初始阶段，不构成信号
            # 如果此时grid = 3，说明当前价格仅在开盘价之下的3区域中，没有突破网格线
            # 如果此时grid = 4，说明当前价格仅在开盘价之上的4区域中，没有突破网格线
            if self.last_grid == 0:
                self.last_grid = grid
                self.last_price = cur_price
                return ukr, infos
            assert(self.last_grid != 0)
            # 如果前一次开仓是4-5，这一次是5-4，算是没有突破，不成交
            if grid_change_new != self.grid_change_last:
                # 更新前一次的数据
                self.last_grid = grid
                self.last_price = cur_price
                self.grid_change_last = grid_change_new
                assert(self.holders >= 0)
                # 向上突破网格线
                if self.holders == 0:
                    # 当前持仓量为0，启动建仓
                    logging.info('网格向上突破，当前未持仓，触发买入={}...'.format(self.VOLUME))
                    ukr.trade.begin_trade(base_item.TRADE_STATUS.BUY, self.UP_EMPTY_BUY)
                    infos = super().buy_market(self.VOLUME)
                    logging.info('buy_market()返回值={}'.format(infos))
                    if infos['local_code'] == 0:
                        self.__holders += self.VOLUME
                        #super().config.update_grid_holders(self.holders)
                        ukr.trade.end_trade(base_item.TRADE_STATUS.BUY, UPDATE_TRADE_RESULT.SUCCESS)
                        logging.info('网格向上突破，初始化建仓数量=（{}）成功。'.format(self.VOLUME))
                    else:
                        logging.error('网格向上突破，初始化建仓数量=（{}）失败。code={}，msg={}。'.format(self.VOLUME,
                            infos['local_code'], infos['local_msg']))
                        ukr.trade.end_trade(base_item.TRADE_STATUS.FAILED, infos['local_msg'])
                else:
                    # 平多（卖出）或开空
                    logging.info('网格向上突破，当前持仓量={}，触发卖出={}...'.format(self.holders, self.VOLUME))
                    ukr.trade.begin_trade(base_item.TRADE_STATUS.SELL, self.UP_HOLD_SELL)
                    infos = super().sell_martket(self.VOLUME)
                    logging.info('sell_market()返回值={}'.format(infos))
                    if infos['local_code'] == 0:
                        self.__holders -= self.VOLUME
                        #super().config.update_grid_holders(self.holders)
                        logging.info('网格向上突破，卖出数量=（{}）成功，剩余持仓=（{}）。'.format(self.VOLUME, self.holders))
                        ukr.trade.end_trade(base_item.TRADE_STATUS.SELL, UPDATE_TRADE_RESULT.SUCCESS)
                    else:
                        logging.error('网格向上突破，卖出数量=（{}）失败，当前持仓={}。code={}，msg={}。'.format(self.VOLUME,
                            self.holders, infos['local_code'], infos['local_msg']))
                        ukr.trade.end_trade(base_item.TRADE_STATUS.FAILED, infos['local_msg'])
            else :
                logging.info('拉锯阶段，忽略该次网格突破。')
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
                self.last_price = cur_price
                return ukr, infos
            assert(self.last_grid != 0)
            # 如果前一次开仓是4-5，这一次是5-4，算是没有突破，不成交
            if grid_change_new != self.grid_change_last:
                # 更新前一次的数据
                self.last_grid = grid
                self.last_price = cur_price
                self.grid_change_last = grid_change_new
                # 向下突破网格线
                if self.holders + self.VOLUME >= self.MAX_HOLDER:
                    logging.info('网格向下突破，当前持仓量={}，触发平仓...'.format(self.holders))
                    ukr.trade.begin_trade(base_item.TRADE_STATUS.SELL, self.DOWN_FULL_SELL)
                    infos = super().sell_martket(self.holders)
                    logging.info('sell_market()返回值={}'.format(infos))
                    if infos['local_code'] == 0:
                        self.__holders = float(0.0)
                        #super().config.update_grid_holders(self.__holders)
                        logging.info('网格向下突破，平仓数量=（{}）成功。'.format(self.holders))
                        ukr.trade.end_trade(base_item.TRADE_STATUS.SELL, UPDATE_TRADE_RESULT.SUCCESS)
                    else:
                        logging.error('网格向下突破，平仓数量=（{}）失败。code={}，msg={}。'.format(self.holders,
                            infos['local_code'], infos['local_msg']))
                        ukr.trade.end_trade(base_item.TRADE_STATUS.FAILED, infos['local_msg'])
                else:
                    # 平空（买入）或开多
                    logging.info('网格向下突破，当前持仓量={}，触发买入...'.format(self.holders))
                    ukr.trade.begin_trade(base_item.TRADE_STATUS.BUY, self.DOWN_HOLD_BUY)
                    infos = super().buy_market(self.VOLUME)
                    logging.info('buy_market()返回值={}'.format(infos))
                    if infos['local_code'] == 0:
                        self.__holders += self.VOLUME
                        #super().config.update_grid_holders(self.__holders)
                        logging.info('网格向下突破，买入数量=（{}）成功，剩余持仓=（{}）。'.format(self.VOLUME, self.holders))
                        ukr.trade.end_trade(base_item.TRADE_STATUS.BUY, UPDATE_TRADE_RESULT.SUCCESS)
                    else:
                        logging.error('网格向下突破，买入数量=（{}）失败，当前持仓={}。code={}，msg={}。'.format(self.VOLUME,
                            self.holders, infos['local_code'], infos['local_msg']))
                        ukr.trade.end_trade(base_item.TRADE_STATUS.FAILED, infos['local_msg'])
        return ukr, infos
    
def test():
    #获取格林威治时间
    times = time.time()
    gmtimes = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(times))
    print('格林威治时间：', gmtimes)
    my_times = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(times))
    print('本地时间：', my_times)
    #now = bsw.get_server_time()
    return

#test()


