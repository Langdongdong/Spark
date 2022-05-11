import asyncio, pathlib, pandas, sys, re
from typing import Dict, Set, Tuple

from pandas import DataFrame
from MultiAccountTrade.utility import is_trade_period
from object import OrderRequest
from engine import MAEngine

from vnpy.trader.constant import Direction
from vnpy_ctp import CtpGateway
from vnpy_rohon import RohonGateway

from twap import TWAP
from utility import is_night_period

AM_SYMBOL = []

TWAP_SETTING = {
    "TIME": 60,
    "INTERVAL": 30
}

FILE_SETTING = {
    "ORDER_DIR_PATH": "",
    "BACKUP_DIR_PATH": "",
    "POSITION_DIR_PATH": "",
    "LOG_DIR_PATH": ""
}

ACCOUNT_SETTING = {
    "account_name_01": {
        "用户名": "",
        "密码": "",
        "经纪商代码": "",
        "交易服务器": "",
        "行情服务器": "",
        "产品名称": "",
        "授权编码": "",
        "Gateway": "CtpGateway"
    },
    "account_name_02": {
        "用户名": "",
        "密码": "",
        "经纪商代码": "",
        "交易服务器": "",
        "行情服务器": "",
        "产品名称": "",
        "授权编码": "",
        "Gateway": "RohonGateway"
    }
}

async def run():
    print(">>>>> START SCRIPT >>>>>")
    while True:
        if is_trade_period():
            print(">>>>> START TRADING >>>>>")
            break
        await asyncio.sleep(5)

    engine = MAEngine([CtpGateway, RohonGateway], ACCOUNT_SETTING)
    engine.debug("Engine inited")

    subscribes, queue = load_data(engine)
    engine.debug("Data loaded")

    while True: 
        if engine.is_gateway_inited(engine.get_subscribe_gateway().gateway_name):
            engine.susbcribe(subscribes)
            break
        asyncio.sleep(3)
    engine.debug("Symbols subscribed")

    while True:
        not_inited_gateway_names = [n for n in engine.get_all_gateway_names() if not engine.is_gateway_inited(n)]
        if len(not_inited_gateway_names) == 0:
            break
        await asyncio.sleep(3)
    engine.debug("All gateways inited")
    
    tasks = []
    for i in range(len(engine.gateways) * 5):
        tasks.append(asyncio.create_task(run_twap(engine, queue)))

    await queue.join()
    engine.debug("Complete all TWAP")

    await asyncio.gather(*tasks, return_exceptions=True)

    engine.close()
    sys.exit()

async def run_twap(engine: MAEngine, queue: asyncio.Queue, twap_setting: Dict[str, int]):
    while not queue.empty():
        data = await queue.get()

        await TWAP(engine, data[0], data[1], twap_setting).run()

        queue.task_done()

def load_data(engine: MAEngine) -> Tuple[Set[str], asyncio.Queue]:
    """
    Load and process data from the specified csv file.\n
    Output a set of symbol subscriptions and a queue of order requests.
    """   
    subscribes: Set[str] = set()
    queue: asyncio.Queue = asyncio.Queue()

    order_dir_path = pathlib.Path(FILE_SETTING["ORDER_DIR_PATH"])
    backup_dir_path = pathlib.Path(FILE_SETTING["BACKUP_DIR_PATH"])
    if not backup_dir_path.exists():
        backup_dir_path.mkdir()

    try:
        iter = order_dir_path.iterdir()
        last = next(iter)
        for last in iter: pass
        file_date = re.match("[0-9]*",last.name).group()
    except:
        print("SFTP remote server has not be turned on.")
        sys.exit(0)

    for gateway_name in engine.get_all_gateway_names():
        order_file_path = order_dir_path.joinpath(f"{file_date}_{gateway_name}.csv")
        backup_file_path = backup_dir_path.joinpath(f"{file_date}_{gateway_name}_backup.csv")
        engine.add_backup_file_path(gateway_name, backup_file_path)

        requests: DataFrame = engine.load_backup_data(gateway_name)
        if requests is None:
            requests = pandas.read_csv(order_file_path)
            engine.add_backup_data(gateway_name, requests)
            engine.backup(gateway_name)

        if is_night_period():
            requests = requests[requests["ContractID"].apply(lambda x:(re.match("[^0-9]*", x, re.I).group().upper() not in AM_SYMBOL))]
        
        for row in requests.itertuples():
            if getattr(row, "Num") <= 0:
                continue
            request = OrderRequest(getattr(row, "ContractID"), getattr(row, "Op1"), getattr(row, "Op2"), getattr(row, "Num"))
            queue.put_nowait((gateway_name, request))

        subscribes.update([OrderRequest.convert_to_vt_symbol(symbol) for symbol in requests["ContractID"].tolist()])

    return subscribes, queue

def save_position(engine: MAEngine) -> None:
    positions: DataFrame = engine.get_all_positions(True)

    positions["direction"] = positions["direction"].apply(lambda x : "Buy" if x == Direction.LONG else "Sell")
    positions.sort_values(["direction", "symbol"], ascending = [True, True], inplace = True)
    positions = positions[positions["volume"] != 0]

    for gateway_name in 

if __name__ == "__main__":
    asyncio.run(run())