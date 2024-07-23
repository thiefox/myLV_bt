import requests
import time
import os

import sys
import time
import logging
from binance import BinanceSpotHttp

from utils import config
#from utils import utility, round_to, dingding_info
from utils import utility
from enum import Enum
import logging
from datetime import datetime

api_key = 'XYCWi1jlDJcOPG8MltM0plnPQlmqFd0wuvCKVuokovxlmwXBADoCI7Ea78h6bX2Y'
api_secret = 'your_api_secret'

def get_account_balance():
    url = 'https://api.binance.com/api/v3/account'
    headers = {'X-MBX-APIKEY': api_key}
    response = requests.get(url, headers=headers, params={'timestamp': int(time.time() * 1000), 'recvWindow': 5000})
    if response.status_code == 200:
        account_info = response.json()
        balances = account_info['balances']
        for balance in balances:
            if float(balance['free']) > 0 or float(balance['locked']) > 0:
                print(f"Asset: {balance['asset']}, Free: {balance['free']}, Locked: {balance['locked']}")
    else:
        print(f"Error: {response.status_code}")

def test_spot():
    cfg = config.Config()
    cfg.loads(config.Config.CONFIG_FILE)
    
    http_clinet = BinanceSpotHttp(api_key=cfg.api_key, private_key=cfg.private_key)
    infos = http_clinet.get_account_info()
    for item in infos['balances']:
        if float(item['free']) > 0  or float(item['locked']) > 0:
            print(f"Asset: {item['asset']}, Free: {item['free']}, Locked: {item['locked']}")

    return

#get_account_balance()
test_spot()
