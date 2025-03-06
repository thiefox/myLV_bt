import binance.binance_spot as BS

from utils import config
from utils import utility
from utils import log_adapter

import base_item

class binance_spot_wrapper:
    def __init__(self) :
        self.cfg = config.Config()
        return
    def init(self) -> bool:
        if not self.cfg.loads():
            log_adapter.color_print('异常：加载配置文件失败。', log_adapter.COLOR.RED)
            return False
        return True
    @property
    def API_KEY(self) -> str:
        return self.cfg.api_key
    @property
    def PRI_KEY(self) -> str:
        return self.cfg.private_key    
    def is_valid(self) -> bool:
        return len(self.API_KEY) > 0 and len(self.PRI_KEY) > 0
    def get_exchange_params(self, symbol : base_item.crypto_symbol) -> tuple[float, float]:
        min_price = float(0)
        min_quantity = float(0)
        http_client = BS.BinanceSpotHttp(api_key=self.API_KEY, private_key=self.PRI_KEY)
        params = http_client.get_exchange_params(symbol.value)
        if params is None:
            log_adapter.color_print('异常：获取交易对参数失败。', log_adapter.COLOR.RED)
        else : 
            if 'min_quantity' in params : 
                min_quantity = float(params['min_quantity'])
            if 'min_price' in params:
                min_price = float(params['min_price'])
        return min_price, min_quantity

    
    def get_price(self, symbol : base_item.crypto_symbol) -> float:
        http_client = BS.BinanceSpotHttp(api_key=self.API_KEY, private_key=self.PRI_KEY)
        sell_price = 0
        try :
            infos = http_client.get_ticker(symbol.value)
            if infos is not None :
                buy_price = round(float(infos['bidPrice']), 2)
                buy_qty = round(float(infos['bidQty']), 5)
                sell_price = round(float(infos['askPrice']), 2)
                sell_qty = round(float(infos['askQty']), 5)
                #print('买价（最高）={}, 买量={:.6f}, 卖价（最低）={}, 卖量={:.6f}'.format(buy_price, buy_qty, sell_price, sell_qty))
        except Exception as e:
            log_adapter.color_print('异常：获取币种{}价格失败，原因：{}'.format(symbol.value, e), log_adapter.COLOR.RED)
        return sell_price

    def get_all_balances(self) -> list[dict]:
        http_client = BS.BinanceSpotHttp(api_key=self.API_KEY, private_key=self.PRI_KEY)
        infos = http_client.get_account_info()
        balances = list()
        try :
            for balance in infos['balances']:
                if float(balance['free']) > 0 or float(balance['locked']) > 0:
                    balances.append(balance)
                    #print('balance={}'.format(balance))
        except Exception as e:
            log_adapter.color_print('异常：获取全币种余额失败，原因：{}'.format(e), log_adapter.COLOR.RED)
        return balances

    def get_banlance(self, symbol : base_item.crypto_symbol) -> tuple[float, float]:
        free = 0
        locked = 0
        balances = self.get_all_balances()
        try :
            for balance in balances:
                if balance['asset'].upper() == symbol.value.upper() :
                    free = float(balance['free'])
                    locked = float(balance['locked'])
                    break
        except Exception as e:
            log_adapter.color_print('异常：获取{}余额失败，原因：{}'.format(symbol.value, e), log_adapter.COLOR.RED)
        return free, locked
    #市价买入
    #amount: 买入数量。如果为0，则满仓买入。
    def buy_with_market(self, symbol : base_item.crypto_symbol, amount : float = 0) -> dict:
        assert(len(self.API_KEY) > 0)
        assert(len(self.PRI_KEY) > 0)
        assert(isinstance(symbol, base_item.crypto_symbol))
        http_client = BS.BinanceSpotHttp(api_key=self.API_KEY, private_key=self.PRI_KEY)
        infos = http_client.buy_market(symbol.value, amount=amount)
        try:
            if infos['local_code'] == 0:
                request_qty = float(infos['origQty'])
                executed_qty = float(infos['executedQty'])
                log_adapter.color_print('重要：买单完成，请求数量={}, 成交数量={}。'.format(request_qty, executed_qty), log_adapter.COLOR.GREEN)
                fills = infos['fills']
                for fill in fills:
                    price = round(float(fill['price']), 2)
                    qty = round(float(fill['qty']), 5)
                    log_adapter.color_print('重要：---买单价格={}, 成交数量={}'.format(price, qty), log_adapter.COLOR.GREEN)
            else :
                assert(infos['local_code'] == -1)
                log_adapter.color_print('异常：市价买入失败，币种={}，数量={}，原因={}。'.format(symbol.value, 
                    amount, infos['local_msg']), log_adapter.COLOR.RED)
        except Exception as e:
            log_adapter.color_print('异常：获取买单信息失败，原因={}。'.format(e), log_adapter.COLOR.RED)
        return infos
    #市价卖出
    #amount: 卖出数量。如果为0，则全部卖出。
    def sell_with_market(self, symbol : base_item.crypto_symbol, amount : float = 0) -> dict:
        assert(len(self.API_KEY) > 0)
        assert(len(self.PRI_KEY) > 0)  
        assert(isinstance(symbol, base_item.crypto_symbol))
        http_client = BS.BinanceSpotHttp(api_key=self.API_KEY, private_key=self.PRI_KEY)
        infos = http_client.sell_market(symbol.value, amount=amount)
        assert(infos is not None)
        try:
            if infos['local_code'] == 0:
                request_qty = float(infos['origQty'])
                executed_qty = float(infos['executedQty'])
                log_adapter.color_print('重要：卖单完成，请求数量={}, 成交数量={}。'.format(request_qty, executed_qty), log_adapter.COLOR.GREEN)
                fills = infos['fills']
                for fill in fills:
                    price = round(float(fill['price']), 2)
                    qty = round(float(fill['qty']), 5)
                    log_adapter.color_print('重要：---卖单价格={}, 成交数量={}'.format(price, qty), log_adapter.COLOR.GREEN)
            else :
                assert(infos['local_code'] == -1)
                log_adapter.color_print('异常：市价卖出失败，币种={}，数量={}，原因={}。'.format(symbol.value, 
                    amount, infos['local_msg']), log_adapter.COLOR.RED)
        except Exception as e:
            log_adapter.color_print('异常：获取卖单信息失败，原因={}。'.format(e), log_adapter.COLOR.RED)
        return infos

