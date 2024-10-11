import base_item
import data_loader

#生成MACD模式每日收益曲线
def calc_MACD_daily_profit(year_begin : int, year_end : int, interval : base_item.kline_interval) -> list:
    INIT_CASH = 10000
    cash = float(INIT_CASH)     #初始资金
    amount = float(0)       #持有的币数量
    fee = 0.001
    buy_price = 0
    klines = data_loader.load_klines_years(base_item.trade_symbol.BTCUSDT, year_begin, year_end, interval)
    print('共载入的K线数据记录={}'.format(len(klines)))
    if len(klines) == 0:
        return list()
    INIT_PRICE = round(float(klines[0][1]), 4)
    print('开始计算MACD模式的每日收益...')
    dates = [timestamp_to_string(kline[0]) for kline in klines]
    #把dates转换为numpy数组
    dates = numpy.array(dates)
    closed_prices = [float(kline[4]) for kline in klines]
    macd, signal = calculate_macd(klines)
    assert(isinstance(macd, numpy.ndarray))
    assert(len(macd) == len(klines))
    crossovers = find_macd_crossovers(macd, signal)
    print('共找到{}个MACD交叉点'.format(len(crossovers)))
    accounts = [simple_account()] * len(macd)       #每日的账户信息
    accounts[0].deposit(INIT_CASH)                  #初始资金
    gold_ops = list()       #金叉操作
    dead_ops = list()       #死叉操作
    draw_ops = list()       #回撤操作
    gold_ignore_ops = list()    #忽略的金叉
    dead_ignore_ops = list()    #忽略的死叉
    operations = list()     #操作记录
    for i in range(1, len(klines)):
        handled = False
        accounts[i] = copy.deepcopy(accounts[i-1])  #复制前一天的账户信息
        date_str = datetime.strptime(dates[i], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        print('处理第{}天={}...'.format(i, date_str))
        if accounts[i].amount > 0:  #当前为持仓状态
            # 只保留年月日
            hold_days = accounts[i].hold_days(date_str)
            assert(i > hold_days)
            prefit = calc_profit_scale(closed_prices, i-hold_days, i)
            print('持仓天数={}，日期={}，币价={}，持仓收益={:.2f}%'.format(hold_days, date_str, closed_prices[i], prefit*100))
            info = find_prev_peak(closed_prices, i)
            assert(info[1] >= 0)
            print('前一个峰值币价={}，索引={}'.format(info[0], info[1]))
            prefit = calc_profit_scale(closed_prices, info[1], i)
            print('前一个峰值到当前日期的收益={:.2f}%'.format(prefit*100))
            #info = calc_max_drawdown(closed_prices[i-hold_days:i])
            #if info[0] > MAX_DRAWDOWN:
            if prefit < -MAX_DRAWDOWN:
                print('重要：日期={}，持仓{}天后的回撤已超过上限={:.2f}%，清仓...'.format(date_str, hold_days, prefit*100))
                sell_price = closed_prices[i]
                print('通知：日期={}，操作=卖出(回撤)，价格={}, 数量={}...'.format(date_str, sell_price, accounts[i].amount))
                accounts[i].sell_all(sell_price, date_str, fee)
                print('通知：回撤卖出操作完成，当前资金={}, 当前币数={}。'.format(accounts[i].cash, accounts[i].amount))
                draw_ops.append(i)
                operations.append(i)
                handled = True

        if not handled and i in [c[0] for c in crossovers]:
            index = [c[0] for c in crossovers].index(i)
            if crossovers[index][1] == '金叉':
                if accounts[i].amount == 0:
                    buy_price = float(klines[i][4])
                    print('重要：日期={}，出现金叉，可用资金={}, 币价={}, 可买数量={}'.format(date_str, accounts[i].cash, 
                        buy_price, accounts[i].max_buy_amount(buy_price, fee)))
                    amount = accounts[i].buy_all(buy_price, date_str, fee)
                    assert(amount > 0)
                    print('重要：日期={}, 金叉买入操作完成，当前资金={}, 当前币数={}。'.format(date_str, accounts[i].cash, accounts[i].amount))
                    gold_ops.append(i)
                    operations.append(i)
                    handled = True
                else :
                    gold_ignore_ops.append(i)
                    print('异常：日期={}, 金叉买入信号，已为持仓状态(资金={}，持币={})，放弃该金叉。'.format(date_str, 
                        accounts[i].cash, accounts[i].amount))
            else :
                assert(crossovers[index][1] == '死叉')
                if accounts[i].amount > 0:
                    sell_price = float(klines[i][4])
                    print('重要：日期={}，出现死叉，卖出操作，价格={}, 数量={}...'.format(date_str, sell_price, accounts[i].amount))
                    accounts[i].sell_all(sell_price, date_str, fee)
                    print('重要：日期={}, 死叉卖出操作完成，当前资金={}, 当前币数={}。'.format(date_str, accounts[i].cash, accounts[i].amount))
                    dead_ops.append(i)
                    operations.append(i)
                    handled = True
                else :
                    dead_ignore_ops.append(i)
                    print('异常：日期={}, 死叉卖出信号，无持仓状态(资金={}，持币={})，放弃该死叉。'.format(date_str, accounts[i].cash, accounts[i].amount))
        else :
            #保持上一天的状态
            if i in [c[0] for c in crossovers] :
                index = [c[0] for c in crossovers].index(i)
                if crossovers[index][1] == '金叉':
                    gold_ignore_ops.append(i)
                else :
                    assert(crossovers[index][1] == '死叉')
                    dead_ignore_ops.append(i)
            pass
            
    #最后一天卖出
    if accounts[-1].amount > 0:
        sell_price = float(klines[-1][4])
        date_str = datetime.strptime(dates[-1], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        print('重要：最后一天卖出操作，日期={}, 价格={}, 数量={}...'.format(date_str, sell_price, accounts[-1].amount))
        accounts[-1].sell_all(sell_price, date_str, fee)
        operations.append(len(accounts)-1)
        
    print('------------------------------------------------------------')
    assert(accounts[-1].amount == 0)
    print('重要：MACD模式最终资金=={}, 最终币数={}。'.format(accounts[-1].cash, accounts[-1].amount))

    profits = [0] * len(accounts)
    for i in range(len(accounts)):
        profits[i] = accounts[i].total_asset(closed_prices[i])

    print('起始资金={}, 起始币数量={}, 起始币价格={}, 结束币价格={}'.format(INIT_CASH, 0, INIT_PRICE, closed_prices[-1]))
    print('MACD模式最终资金={}, 最终收益={}.'.format(accounts[-1].cash, accounts[-1].cash-INIT_CASH))
    
    print('金叉买入次数={}, 金叉买入列表={}.'.format(len(gold_ops), ', '.join([str(x) for x in gold_ops])))
    print('死叉卖出次数={}, 死叉卖出列表={}.'.format(len(dead_ops), ', '.join([str(x) for x in dead_ops])))
    print('回撤卖出次数={}, 回撤卖出列表={}.'.format(len(draw_ops), ', '.join([str(x) for x in draw_ops])))
    print('忽略金叉次数={}, 忽略金叉列表={}.'.format(len(gold_ignore_ops), ', '.join([str(x) for x in gold_ignore_ops])))
    print('忽略死叉次数={}, 忽略死叉列表={}.'.format(len(dead_ignore_ops), ', '.join([str(x) for x in dead_ignore_ops])))
    print('开始打印买卖操作...')
    BUY_OP = True
    for index in range(0, len(operations)):
        i = operations[index]
        date_str = datetime.strptime(dates[i], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        if BUY_OP:
            print('金叉买入：i={}，日期={}，价格={}，数量={}，剩余资金={}. 总值={}.'.format(i, date_str, closed_prices[i],
                accounts[i].amount, accounts[i].cash, profits[i]))
            BUY_OP = False
        else :
            REASON = '死叉'
            buy_i = operations[index-1]
            profit = calc_profit_scale(closed_prices, buy_i, i)
            if i in draw_ops:
                REASON = '回撤'
            print('({})卖出：i={}，日期={}，价格={}，数量={}，操作收益={:.2f}%. 剩余资金={}. 总值={}.'.format(REASON, i,
                date_str, closed_prices[i], accounts[i-1].amount, profit*100, accounts[i].cash, profits[i]))
            BUY_OP = True
    print('打印买卖操作结束.')
    info = calc_max_drawdown(profits)
    begin_str = datetime.strptime(dates[info[1]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    end_str = datetime.strptime(dates[info[2]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    print('MACD最大连续回撤={:.2f}%, bi={}={}, ei={}={}'.format(info[0]*100, info[1], begin_str, info[2], end_str))
    before = profits[info[1]-1]
    after = profits[info[2]+1]
    print('MACD模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
    print('MACD模式最大连续回撤的前一天={}'.format(before))
    print_list_range(profits, info[1], info[2], hint=0)
    print('MACD模式最大连续回撤的后一天={}'.format(after))
    info = calc_hold_days_with_accounts(accounts)
    print('MACD模式ACCOUNTS计算，总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    info = calc_hold_days_with_profit(profits)
    print('MACD模式PROFIT计算，总天数={}, 总持仓天数={}, 最长一次持仓天数={}'.format(len(klines), info[0], info[1]))
    print('------------------------------------------------------------')
    #开始计算起始买币，最终卖币收益
    amount = INIT_CASH/INIT_PRICE
    cash = round(amount * closed_prices[-1] * (1 - fee), 2)
    print('持仓模式最终资金={}, 最终收益={}'.format(cash, cash-INIT_CASH))        
    info = calc_max_drawdown(closed_prices)
    begin_str = datetime.strptime(dates[info[1]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    end_str = datetime.strptime(dates[info[2]], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    print('持仓模式最大连续回撤={:.2f}%, bi={}={}, ei={}={}'.format(info[0]*100, info[1], begin_str, info[2], end_str))
    before = closed_prices[info[1]-1]
    after = closed_prices[info[2]+1]
    print('持仓模式最大连续回撤的前一天={}, 后一天={}, 回撤={}'.format(before, after, after-before))
    print('持仓模式最大连续回撤的前一天={}'.format(before))
    #print_list_range(closed_prices, info[1], info[2], hint=0)
    print('持仓模式最大连续回撤的后一天={}'.format(after))
    '''
    print('开始打印每日收益...')
    for i in range(len(profits)):
        print('index={}, date={}, profit={}'.format(i, dates[i], profits[i]))
    print('打印每日收益结束.')
    '''
    return profits
