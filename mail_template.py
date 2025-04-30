from enum import Enum
import logging

from com_utils import mail_qq
from base_item import TRADE_STATUS
from processor_template import UPDATE_TRADE_RESULT

BUY_SIGNAL_NOTIFY   = '重要：处理器{}在时间={}发出买入信号，原因={}，价格={}$，请及时关注。'
SELL_SIGNAL_NOTIFY  = '重要：处理器{}在时间={}发出卖出信号，原因={}，价格={}$，请及时关注。'
BOUGHT_SUCCESS_NOTIFY = '重要：处理器{}在时间={} TRIGGER={} 触发买入并成功，价格={}$，数量={}个。\n当前资产情况：余额={}$，币数量={}，总资产={}$。'
SOLD_SUCCESS_NOTIFY   = '重要：处理器{}在时间={} TRIGGER={} 触发卖出并成功，价格={}$，数量={}个。\n当前资产情况：余额={}$，币数量={}，总资产={}$。'
TRADE_FAILED_NOTIFY  = '异常：处理器{}在时间={} TRIGGER={} 触发交易失败，原因={}。'
BANANCE_NOTIFY = '重要：时间={}，当前余额={}$，币数量={}，币价={}$，总资产={}$。'

# 邮件类型枚举
class mail_type(Enum):
    UNKNOW = 0
    TRADE = 1
    BALANCE = 2

class mail_content() :
    def __init__(self, receiver : str) -> None:
        self.__processor = 'general'
        self.__receiver = receiver
        self.__type = mail_type.UNKNOW
        self.__utr = UPDATE_TRADE_RESULT()
        self.__time = ''
        self.__price = float(0)         #平均成交价格
        self.__request_quantity = float(0)
        self.__executed_quantity = float(0)
        self.__fills = list()
        self.__balance = float(0)         #USDT余额
        self.__total_quantity = float(0)  #币的总数量
        return
    @property
    def receiver(self) -> str:
        return self.__receiver
    @property       #交易数量
    def trade_count(self) -> float:
        return round(self.__executed_quantity, 5)
    @property       #当前币价或平均成交价格
    def price(self) -> float:
        return round(self.__price, 2)
    @property
    def time_str(self) -> str:
        return self.__time
    @property
    def balance(self) -> float:
        return round(self.__balance, 2)
    @property           #币的总数量
    def total_count(self) -> float:
        return round(self.__total_quantity, 5)
    @property            #总资产
    def asset(self) -> float:
        return round(self.balance + self.__total_quantity * self.price, 2)
    @property
    def UTR(self) -> UPDATE_TRADE_RESULT:
        return self.__utr
    @UTR.setter
    def UTR(self, value : UPDATE_TRADE_RESULT) -> None:
        self.__utr = value
        return
    @property
    def processor(self) -> str:
        return self.__processor
    @processor.setter
    def processor(self, value : str) -> None:
        self.__processor = value
        return        
    #交易状态更新
    def update_trade(self, time : str, utr : UPDATE_TRADE_RESULT, infos : dict) -> None:
        self.__type = mail_type.TRADE
        self.__time = time
        self.__utr = utr
        if infos is not None :
            try:
                self.__request_quantity = round(float(infos['origQty']), 5)
                self.__executed_quantity = round(float(infos['executedQty']), 5)
                fills = infos['fills']
                if len(fills) == 1:
                    fill = fills[0]
                    piece_qty = round(float(fill['qty']), 5)
                    piece_price = round(float(fill['price']), 2)
                    assert(piece_qty == self.__executed_quantity)
                    self.__price = piece_price
                else :
                    total_price = 0
                    total_qty = 0
                    for fill in fills:
                        piece_qty = round(float(fill['qty']), 5)
                        piece_price = round(float(fill['price']), 2)
                        self.__fills.append((piece_qty, piece_price))        #数量，价格
                        total_qty += piece_qty
                        total_price += piece_qty * piece_price
                    assert(total_qty == self.__executed_quantity)
                    self.__price = round(total_price / self.__executed_quantity, 2)
            except Exception as e:
                logging.error('解析成交信息失败，错误信息={}。'.format(e))
                logging.error('成交信息={}'.format(infos))
        return
    def update_balance(self, time : str, balances : list, price : float) -> None:
        assert(isinstance(balances, list))
        if self.__type == mail_type.UNKNOW :
            self.__type = mail_type.BALANCE
        if price > 0 :
            self.__price = price
        if time != '' :
            self.__time = time
        try :
            for balance in balances:
                if balance['asset'].upper() == 'USDT' :
                    self.__balance = round(float(balance['free']) + float(balance['locked']), 2)
                elif balance['asset'].upper() == 'BTC' :
                    self.__total_quantity = round(float(balance['free']) + float(balance['locked']), 5)
        except Exception as e:
            logging.error('解析余额信息失败，错误信息={}。'.format(e))
            logging.error('余额信息={}'.format(balances))
        return
    
    def gen_mail(self) -> tuple[str, str] :
        title = '未知'
        content = '未知原因的异常。'
        if self.__type == mail_type.TRADE :
            if self.UTR.status == TRADE_STATUS.BUY :
                content = BOUGHT_SUCCESS_NOTIFY.format(self.processor, self.time_str, self.UTR.reason, self.price, self.trade_count,
                    self.balance, self.total_count, self.asset)
                title = '买入成功'
            elif self.UTR.status == TRADE_STATUS.SELL :
                content = SOLD_SUCCESS_NOTIFY.format(self.processor, self.time_str, self.UTR.reason, self.price, self.trade_count,
                    self.balance, self.total_count, self.asset)
                title = '卖出成功'
            elif self.UTR.status == TRADE_STATUS.FAILED :
                content = TRADE_FAILED_NOTIFY.format(self.processor, self.time_str, self.UTR.reason, self.UTR.info)
                title = '交易失败'
            else :
                content = '未知交易状态={}，TRIGGER={}，原因={}，请检查。'.format(self.UTR.status, self.UTR.reason, self.UTR.info)
                title = '处理异常'
        elif self.__type == mail_type.BALANCE :
            content = BANANCE_NOTIFY.format(self.time_str, self.balance, self.total_count, self.price, self.asset)
            title = '币价-{}'.format(int(self.price))
        else :
            pass
        return title, content
    
    def send_mail(self) -> bool:
        title, content = self.gen_mail()
        return mail_qq.send_email(self.receiver, title, content)
    
    def write_mail(self, title : str, msg : str) -> bool:
        return mail_qq.send_email(self.receiver, title, msg)

