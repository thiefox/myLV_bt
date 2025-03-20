import logging
import socket

import binance.binance_spot as BS

from com_utils import config
from com_utils import utility
from com_utils import log_adapter

import base_item

class binance_spot_wrapper:
    def __init__(self) :
        self.cfg = config.Config()
        return
    def init(self) -> bool:
        if not self.cfg.loads():
            logging.error('加载配置文件失败。')
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
    def check_DNS(self) -> bool:
        ip_address = socket.gethostbyname('api.binance.com')
        logging.info('DNS解析api.binance.com的IP地址={}'.format(ip_address))
        try :
            socket.inet_aton(ip_address)
            logging.info('IP地址合法。')
            return True
        except Exception as e:
            logging.error('IP地址非法，原因={}'.format(e))
            return False
    def get_server_time(self) -> int:
        http_client = BS.BinanceSpotHttp(api_key=self.API_KEY, private_key=self.PRI_KEY)
        infos = http_client.get_server_time()
        server_time = 0
        if infos is not None :
            if 'serverTime' in infos:
                server_time = int(infos['serverTime'])
                logging.info('获取服务器时间={}'.format(utility.timestamp_to_string(server_time)))
        return server_time

    def get_exchange_params(self, symbol : base_item.crypto_symbol) -> tuple[float, float]:
        min_price = float(0)
        min_quantity = float(0)
        http_client = BS.BinanceSpotHttp(api_key=self.API_KEY, private_key=self.PRI_KEY)
        params = http_client.get_exchange_params(symbol.value)
        if params is None:
            logging.error('获取交易对参数失败。')
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
                logging.debug('买价（最高）={}, 买量={:.6f}, 卖价（最低）={}, 卖量={:.6f}'.format(buy_price, buy_qty, sell_price, sell_qty))
        except Exception as e:
            logging.error('获取币种{}价格失败，原因：{}'.format(symbol.value, e))
        return sell_price

    def get_all_balances(self) -> list[dict]:
        http_client = BS.BinanceSpotHttp(api_key=self.API_KEY, private_key=self.PRI_KEY)
        infos = http_client.get_account_info()
        balances = list()
        try :
            for balance in infos['balances']:
                if float(balance['free']) > 0 or float(balance['locked']) > 0:
                    balances.append(balance)
                    logging.debug('balance={}'.format(balance))
        except Exception as e:
            logging.error('获取全币种余额失败，原因：{}'.format(e))
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
            logging.error('获取{}余额失败，原因：{}'.format(symbol.value, e))
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
                logging.info('买单完成，请求数量={}, 成交数量={}。'.format(request_qty, executed_qty))
                fills = infos['fills']
                for fill in fills:
                    price = round(float(fill['price']), 2)
                    qty = round(float(fill['qty']), 5)
                    logging.debug('---买单价格={}, 成交数量={}'.format(price, qty))
            else :
                logging.critical('市价买入失败，币种={}，数量={}，原因={}。'.format(symbol.value, amount, infos['local_msg']))
        except Exception as e:
            logging.error('获取买单信息失败，原因={}。'.format(e))
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
                logging.info('卖单完成，请求数量={}, 成交数量={}。'.format(request_qty, executed_qty))
                fills = infos['fills']
                for fill in fills:
                    price = round(float(fill['price']), 2)
                    qty = round(float(fill['qty']), 5)
                    logging.debug('---卖单价格={}, 成交数量={}'.format(price, qty))
            else :
                logging.error('市价卖出失败，币种={}，数量={}，原因={}。'.format(symbol.value, amount, infos['local_msg']))
        except Exception as e:
            logging.error('获取卖单信息失败，原因={}。'.format(e))
        return infos

