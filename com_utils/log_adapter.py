import logging.handlers
import os
import sys
from datetime import datetime
from enum import Enum, unique
import logging

@unique
class COLOR(Enum) :
    WHITE = 0          
    RED = 1,
    YELLOW = 2,
    GREEN = 3

def color_print(msg : str, color : COLOR = COLOR.WHITE) :
    COLORED = True
    try :
        if sys.stdout.name == '<stdout>' :
            pass
        else :
            COLORED = False
    except Exception as e:
        COLORED = False
    if COLORED :
        if color == COLOR.WHITE :
            print("\033[0;37;40m{}\033[0m".format(msg))
        elif color == COLOR.RED :
            print("\033[0;31;40m{}\033[0m".format(msg))
        elif color == COLOR.YELLOW :
            print("\033[0;33;40m{}\033[0m".format(msg))
        elif color == COLOR.GREEN :
            print("\033[0;32;40m{}\033[0m".format(msg))
        else :
            print(msg)
    else :
        print(msg)
    return

# Redirect print statements to the logger
class LoggerWriter:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    @property
    def name(self) -> str:
        return '<LoggerWriter>'

    def write(self, message):
        if message != '\n':
            self.logger.log(self.level, message)

    def flush(self):
        pass

import logging

class ColorFormatter(logging.Formatter):
    white = "\x1b[37;20m"
    green = "\x1b[32;20m"
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    #format_s = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    format_s = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    FORMATS = {
        logging.DEBUG: white + format_s + reset,
        logging.INFO: green + format_s + reset,
        logging.WARNING: yellow + format_s + reset,
        logging.ERROR: red + format_s + reset,
        logging.CRITICAL: bold_red + format_s + reset
    }

    def format(self, record) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)    
    
def log_to_console(level = logging.DEBUG) -> None:
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)   
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(ColorFormatter())
    logger.addHandler(console)     
    return    

def log_to_file(file_name : str, level = logging.DEBUG, ROTATE = True) -> None:
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)   
    str_now = datetime.strftime(datetime.now(), '%Y-%m-%d %H-%M-%S') 
    pwd = os.getcwd()
    log_dir = os.path.join(pwd, 'log')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_name = '{}-{}.txt'.format(file_name, str_now)
    log_file = os.path.join(log_dir, file_name)
    if ROTATE :
        file_handler = logging.handlers.RotatingFileHandler(log_file, mode='a', encoding='utf-8', maxBytes=1024*1024, backupCount=2)
    else :
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(ColorFormatter.format_s))
    logger.addHandler(file_handler)
    return
    
def color_console_sample():
    logger = logging.getLogger("My_app")
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(ColorFormatter())
    logger.addHandler(ch)
    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")
    logger.critical("critical message")
    return

#color_console_sample()