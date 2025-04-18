#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Module: utils
"""

import requests
import json
from pathlib import Path
from decimal import Decimal
import os
import time
from datetime import datetime

#确保临时目录存在
def _get_trader_dir(temp_name: str) -> tuple[Path, Path]:
    """
    Get path where trader is running in.
    """
    cwd = Path.cwd()
    temp_path = cwd.joinpath(temp_name)

    if temp_path.exists():
        return cwd, temp_path

    if not temp_path.exists():
        temp_path.mkdir()

    return cwd, temp_path


TRADER_DIR, TEMP_DIR = _get_trader_dir("trader")


def get_file_path(filename: str):
    """
    Get path for temp file with filename.
    """
    return TEMP_DIR.joinpath(filename)


def get_folder_path(folder_name: str):
    """
    Get path for temp folder with folder name.
    """
    folder_path = TEMP_DIR.joinpath(folder_name)
    if not folder_path.exists():
        folder_path.mkdir()
    return folder_path

def confirm_sub_path(sub_name : str) -> Path:
    cwd = Path.cwd()
    path_sub = cwd.joinpath(sub_name)
    if not path_sub.exists():
        path_sub.mkdir()
    return path_sub


def load_json(filename: str):
    """
    Load data from json file in temp path.
    """
    filepath = get_file_path(filename)

    if filepath.exists():
        with open(filepath, mode="r", encoding="UTF-8") as f:
            data = json.load(f)
        return data
    else:
        save_json(filename, {})
        return {}


def save_json(filename: str, data: dict):
    """
    Save data into json file in temp path.
    """
    filepath = get_file_path(filename)
    with open(filepath, mode="w+", encoding="UTF-8") as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )


def round_to(value: float, target: float) -> float:
    """
    Round price to price tick value.
    """
    value = Decimal(str(value))
    target = Decimal(str(target))
    rounded = float(int(round(value / target)) * target)
    return rounded

#发送钉钉消息
def dingding_info(token: str, prompt: str, symbol: str, content: str):
    headers = {'Content-Type': 'application/json;charset=utf-8'}
    api_url = "https://oapi.dingtalk.com/robot/send?access_token=%s" % token
    info_text = "%s %s %s" % (prompt, symbol, content)
    json_text = {
        "msgtype": "text",
        "at": {
            "atMobiles": [],
            "isAtAll": False
        },
        "text": {
            "content": info_text
        }
    }
    requests.post(api_url, json.dumps(json_text), headers=headers).content
    return

#币安int时间戳（毫秒）转换为datetime
def timestamp_to_datetime(time_stamp : int) -> datetime:
    #print('input={}'.format(time_stamp/1000))
    return datetime.fromtimestamp(float(time_stamp/1000))

#币安int时间戳（毫秒）转换为字符串时间
#字符串时间格式='2000-01-01 00:00:00'
def timestamp_to_string(time_stamp : int, ONLY_DATE = False) -> str:
    assert(isinstance(time_stamp, int))
    #print('input={}'.format(time_stamp/1000))
    time_array = time.localtime(float(time_stamp/1000))
    if ONLY_DATE :
        str_date = time.strftime("%Y-%m-%d", time_array)
    else :
        str_date = time.strftime("%Y-%m-%d %H:%M:%S", time_array)
    return str_date

#字符串时间转换为币安int时间戳（毫秒）
#字符串时间格式='2000-01-01 00:00:00'
def string_to_timestamp(str_date : str, ONLY_DATE = False) -> int:
    #print('input={}'.format(str_date))
    if ONLY_DATE :
        time_array = time.strptime(str_date, "%Y-%m-%d")
    else :
        time_array = time.strptime(str_date, "%Y-%m-%d %H:%M:%S")
    time_stamp = int(time.mktime(time_array) * 1000)
    return time_stamp

#获取一年的天数
def days_in_year(year : int) -> int:
    assert(year > 0)
    #是否闰年
    def is_leap_year(year : int) -> bool:
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 366 if is_leap_year(year) else 365

#获取一个月的天数
def days_in_month(year : int, month : int) -> int:
    assert(month >= 1 and month <= 12)
    #是否闰年
    def is_leap_year(year : int) -> bool:
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    #每月天数
    month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month == 2 and is_leap_year(year):
        return 29
    return month_days[month - 1]

#判断某天是否当年当月的最后一天
def is_last_day(year : int, month : int, day : int) -> bool:
    assert(year > 0 and month >= 1 and month <= 12 and day >= 1 and day <= 31)
    return day == days_in_month(year, month)
