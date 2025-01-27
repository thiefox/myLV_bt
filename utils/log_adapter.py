from enum import Enum, unique
import logging

@unique
class COLOR(Enum) :
    WHITE = 0          
    RED = 1,
    YELLOW = 2,
    GREEN = 3

def color_print(msg : str, color : COLOR = COLOR.WHITE) :
    if color == COLOR.WHITE :
        print("\033[0;37;40m{}\033[0m".format(msg))
    elif color == COLOR.RED :
        print("\033[0;31;40m{}\033[0m".format(msg))
    elif color == COLOR.YELLOW :
        print("\033[0;33;40m{}\033[0m".format(msg))
    elif color == COLOR.GREEN :
        print("\033[0;32;40m{}\033[0m".format(msg))
        return

# Redirect print statements to the logger
class LoggerWriter:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, message):
        if message != '\n':
            self.logger.log(self.level, message)

    def flush(self):
        pass