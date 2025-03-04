from enum import Enum

from utils import mail_qq
import base_item

GOLD_CROSS_NOTIFY   = '重要：时间={} 类型={}，发生金叉买入信号，价格={}$，请及时关注。'
DEAD_CROSS_NOTIFY   = '重要：时间={} 类型={}，发生死叉卖出信号，价格={}$，请及时关注。'
GOLD_CROSS_BOUGHT      = '重要：时间={} 类型={}，发生金叉买入事件，价格={}$，已经买入{}个。\n当前资产情况：余额={}$，币数量={}，总资产={}$。'
DEAD_CROSS_SOLD     = '重要：时间={} 类型={}，发生死叉卖出事件，价格={}$，已经卖出{}个。\n当前资产情况：余额={}$，币数量={}，总资产={}$。'
GOLD_CROSS_BUY_FAILED = '异常：时间={} 类型={}，金叉买入失败。原因：{}。'
DEAD_CROSS_SELL_FAILED = '异常：时间={} 类型={}，死叉卖出失败。原因：{}。'
BANANCE_NOTIFY = '重要：时间={}，当前余额={}$，币数量={}，币价={}$，总资产={}$。'

# 邮件类型枚举
class mail_type(Enum):
    UNKNOW = 0
    CROSS_NOTIFY = 1
    TRADE_SUCCESS = 2
    TRADE_FAILED = 3
    BALANCE = 4

class mail_content() :
    def __init__(self, receiver : str) -> None:
        self.__receiver = receiver
        self.__type = mail_type.UNKNOW
        self.__time = ''
        self.__cross = base_item.MACD_CROSS.NONE
        self.__price = float(0)         #平均成交价格
        self.__request_quantity = float(0)
        self.__executed_quantity = float(0)
        self.__fills = list()
        self.__balance = float(0)         #USDT余额
        self.__total_quantity = float(0)  #币的总数量
        self.__reason = ''                     #失败的原因信息
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
    def cross(self) -> base_item.MACD_CROSS:
        return self.__cross
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
    def reason(self) -> str:
        return self.__reason
        
    def update_with_notify(self, time : str, cross : base_item.MACD_CROSS) -> None:
        self.__type = mail_type.CROSS_NOTIFY
        self.__time = time
        self.__cross = cross
        return
    def update_with_failed(self, time : str, cross : base_item.MACD_CROSS, reason : str) -> None:
        self.__type = mail_type.TRADE_FAILED
        self.__time = time
        self.__cross = cross
        self.__reason = reason
        return
    def update_with_success(self, time : str, cross : base_item.MACD_CROSS, infos : dict) -> None:
        self.__type = mail_type.TRADE_SUCCESS
        self.__time = time
        self.__cross = cross
        assert(infos is not None)
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
            pass
        return
    def update_with_balance(self, time : str, balances : list, price : float) -> None:
        assert(isinstance(balances, list))
        if self.__type == mail_type.UNKNOW :
            self.__type = mail_type.BALANCE
        if price > 0 :
            self.__price = price
        if time != '' :
            self.__time = time
        for balance in balances:
            if balance['asset'].upper() == 'USDT' :
                self.__balance = round(float(balance['free']) + float(balance['locked']), 2)
            elif balance['asset'].upper() == 'BTC' :
                self.__total_quantity = round(float(balance['free']) + float(balance['locked']), 5)
        return
    
    def gen_mail(self) -> tuple[str, str] :
        title = '未知'
        content = '未知原因的异常。'
        if self.__type == mail_type.CROSS_NOTIFY :
            if self.cross.is_golden() :
                content = GOLD_CROSS_NOTIFY.format(self.time_str, self.cross.value, self.price)
                title = '金叉信号'
            elif self.cross.is_dead() :
                content = DEAD_CROSS_NOTIFY.format(self.time_str, self.cross.value, self.price)
                title = '死叉信号'
        elif self.__type == mail_type.TRADE_SUCCESS :
            if self.cross.is_golden() :
                content = GOLD_CROSS_BOUGHT.format(self.time_str, self.cross.value, self.price, self.trade_count, self.balance,
                    self.total_count, self.asset)
                title = '金叉买入'
            elif self.cross.is_dead() :
                content = DEAD_CROSS_SOLD.format(self.time_str, self.cross.value, self.price, self.trade_count, self.balance, 
                    self.total_count, self.asset)
                title = '死叉卖出'
        elif self.__type == mail_type.TRADE_FAILED :
            if self.cross.is_golden() :
                content = GOLD_CROSS_BUY_FAILED.format(self.time_str, self.cross.value, self.reason)
                title = '金叉买入失败'
            elif self.cross.is_dead() :
                content = DEAD_CROSS_SELL_FAILED.format(self.time_str, self.cross.value, self.reason)
                title = '死叉卖出失败'
        elif self.__type == mail_type.BALANCE :
            content = BANANCE_NOTIFY.format(self.time_str, self.balance, self.total_count, self.price, self.asset)
            title = '资产信息'
        else :
            pass
        return title, content
    
    def send_mail(self) -> bool:
        title, content = self.gen_mail()
        return mail_qq.send_email(self.receiver, title, content)
    
    def write_mail(self, title : str, msg : str) -> bool:
        return mail_qq.send_email(self.receiver, title, msg)

