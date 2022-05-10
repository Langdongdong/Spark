
from abc import ABC
from datetime import datetime
from fileinput import filename
from logging import FileHandler, Logger
import logging
import pathlib
from numpy import longlong
from pandas import DataFrame
import pandas
from utility import get_df

from copy import copy
from typing import Any, Dict, List, Optional, Sequence, Type
from vnpy.event import Event, EventEngine
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.constant import (
    Offset,
    Direction,
    OrderType,
    Exchange,
)
from vnpy.trader.event import (
    EVENT_TICK,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_ACCOUNT,
    EVENT_POSITION,
    EVENT_CONTRACT,
)
from vnpy.trader.object import (
    BaseData,
    TickData,
    TradeData,
    OrderData,
    AccountData,
    ContractData,
    PositionData,
    OrderRequest,
    SubscribeRequest,
    CancelRequest,
)

"""
#############################################
PositionData struct has changed.
#############################################
"""
class MAEngine():
    """
    Only use for CTP like api.
    """
    def __init__(self, gateway_classes: Sequence[Type[BaseGateway]], settings: Dict[str, Dict[str, str]]) -> None:
        self.ticks: Dict[str, TickData] = {}
        self.orders: Dict[str, OrderData] = {}
        self.trades: Dict[str, TradeData] = {}
        self.accounts: Dict[str, AccountData] = {}
        self.contracts: Dict[str, ContractData] = {}
        self.positions: Dict[str, PositionData] = {}
        self.active_orders: Dict[str, OrderData] = {}

        self.event_engine = EventEngine()
        self._register_process_event()
        self.event_engine.start()

        self.engines: Dict[str, BaseEngine] = {}
        self._add_engine(self, BackupEngine)
        self._add_engine(self, LogEngine)

        self.gateways: Dict[str, BaseGateway] = {}
        self.gateway_classes = Dict[str, Type[BaseGateway]] = {}
        self._add_gateway_classes(gateway_classes)
        self._add_gateways(settings)
        self._connect_gateways(settings)

        self.susbcribe_gateway: BaseGateway = None

    def _add_gateway(self, gateway_class_name: str, gateway_name: str) -> None:
        gateway_class: Optional[Type[BaseGateway]] = self.get_gateway_class(gateway_class_name)
        if gateway_class:
            gateway = gateway_class(self.event_engine, gateway_name)
            self.gateways[gateway.gateway_name] = gateway

    def _add_gateways(self, settings: Dict[str, Dict[str, str]]) -> None:
        for gateway_name, setting in settings.items():
            gateway_class_name = setting.get("Gateway")
            if gateway_class_name:
                self._add_gateway(gateway_class_name, gateway_name)
                
        self._add_subscribe_gateway()

    def _add_gateway_class(self, gateway_class: Type[BaseGateway]) -> None:
        self.gateway_classes[gateway_class.__name__] = gateway_class

    def _add_gateway_classes(self, gateway_classes: Sequence[Type[BaseGateway]]) -> None:
        for gateway_class in gateway_classes:
            self._add_gateway_class(gateway_class)

    def _add_subscribe_gateway(self) -> None:
        if self.susbcribe_gateway is None:
            self.susbcribe_gateway = self.get_all_gateways()[0]

    def _add_engine(self, engine_class: Any) -> "BaseEngine":
        engine: BaseEngine = engine_class(self)
        self.engines[engine.engine_name] = engine
        return engine

    def _connect(self, setting: Dict[str, str], gateway_name: str) -> None:
        gateway = self.get_gateway(gateway_name)
        if gateway:
            gateway.connect(setting)

    def _connect_gateways(self, settings: Dict[str, Dict[str, str]]) -> None:
        for gateway_name, setting in settings.items():
            self._connect(setting, gateway_name)
        
    def _subscribe(self, req: SubscribeRequest, gateway_name: str) -> None:
        gateway = self.get_gateway(gateway_name)
        if gateway:
            gateway.subscribe(req)

    def _send_order(self, req: OrderRequest, gateway_name: str) -> str:
        gateway = self.get_gateway(gateway_name)
        if gateway:
            return gateway.send_order(req)
        return ""

    def _send_taker_order(self, vt_symbol: str, volume: float, direction: Direction, offset: Offset, gateway_name: str) -> List[str]:
        reqs: List[OrderRequest] = []
        vt_orderids: List[str] = []
        
        tick: TickData = self.get_tick(vt_symbol)
        contract: ContractData = self.get_contract(vt_symbol)
        if tick is None or contract is None:
            vt_orderids.append("")
            return vt_orderids

        if direction == Direction.LONG:
            price = tick.ask_price_1 + contract.pricetick * 2
        else:
            price = tick.bid_price_1 - contract.pricetick * 2

        req = OrderRequest(
            symbol = contract.symbol,
            exchange = contract.exchange,
            price = price,
            volume = volume,
            direction = direction,
            offset = offset,
            type = OrderType.LIMIT
        )

        if offset == Offset.CLOSE:
            position = self.get_position(f"{gateway_name}.{contract.vt_symbol}.{direction.value}")
            if not position or position.volume - position.frozen < volume:
                vt_orderids.append("")
                return vt_orderids

            req.volume = position.volume - position.frozen

            if contract.exchange in [Exchange.SHFE, Exchange.INE]:
                if not position.yd_volume:
                    req.offset = Offset.CLOSETODAY
                elif position.volume == position.yd_volume:
                    req.offset = Offset.CLOSEYESTERDAY
                else:
                    req.volume = position.yd_volume - position.frozen
                    req.offset = Offset.CLOSEYESTERDAY

                    req_td = copy(req)
                    req_td.volume = volume - req.volume
                    req_td.offset = Offset.CLOSEYESTERDAY
                    reqs.append(req_td)

        reqs.append(req)

        for req in reqs:
            vt_orderids.append(self._send_order(req, gateway_name))

        return vt_orderids

    def _cancel_order(self, req: CancelRequest, gateway_name:str) -> None:
        gateway = self.get_gateway(gateway_name)
        if gateway:
            gateway.cancel_order(req)
    
    def _process_tick_event(self, event: Event) -> None:
        tick: TickData = event.data
        self.ticks[tick.vt_symbol] = tick

    def _process_order_event(self, event: Event) -> None:
        order: OrderData = event.data
        self.orders[order.vt_orderid] = order

        if order.is_active():
            self.active_orders[order.vt_orderid] = order
        elif order.vt_orderid in self.active_orders:
            self.active_orders.pop(order.vt_orderid)

    def _process_trade_event(self, event: Event) -> None:
        trade: TradeData = event.data
        self.trades[trade.vt_tradeid] = trade

    def _process_position_event(self, event: Event) -> None:
        position: PositionData = event.data
        self.positions[position.vt_positionid] = position

    def _process_contract_event(self, event: Event) -> None:
        contract: ContractData = event.data
        if not self.get_contract(contract.vt_symbol):
            self.contracts[contract.vt_symbol] = contract

    def _process_account_event(self, event: Event) -> None:
        account: AccountData = event.data
        self.accounts[account.gateway_name] = account

    def _register_process_event(self) -> None:
        self.event_engine.register(EVENT_TICK, self._process_tick_event)
        self.event_engine.register(EVENT_ORDER, self._process_order_event)
        self.event_engine.register(EVENT_TRADE, self._process_trade_event)
        self.event_engine.register(EVENT_ACCOUNT, self._process_account_event)
        self.event_engine.register(EVENT_CONTRACT, self._process_contract_event)
        self.event_engine.register(EVENT_POSITION, self._process_position_event)

    def get_gateway(self, gateway_name: str) -> Optional[BaseGateway]:
        return self.gateways.get(gateway_name)

    def get_gateway_class(self, gateway_class_name: str) -> Optional[Type[BaseGateway]]:
        return self.gateway_classes.get(gateway_class_name)

    def get_subscribe_gateway(self) -> Optional[BaseGateway]:
        return self.susbcribe_gateway

    def get_engine(self, engine_name: str) -> Optional["BaseEngine"]:
        return self.engines.get(engine_name)

    def get_tick(self, vt_symbol: str, use_df: bool = False) -> Optional[TickData]:
        return get_df(self.ticks.get(vt_symbol), use_df)

    def get_order(self, vt_orderid: str, use_df: bool = False) -> Optional[OrderData]:
        return get_df(self.orders.get(vt_orderid), use_df)

    def get_active_order(self, vt_orderid: str, use_df: bool = False) -> Optional[OrderData]:
        return get_df(self.active_orders.get(vt_orderid), use_df)

    def get_trade(self, vt_tradeid: str, use_df: bool = False) -> Optional[TradeData]:
        return get_df(self.trades.get(vt_tradeid), use_df)

    def get_position(self, vt_positionid: str, use_df: bool = False) -> Optional[PositionData]:
        return get_df(self.positions.get(vt_positionid), use_df)

    def get_contract(self, vt_symbol: str, use_df: bool = False) -> Optional[ContractData]:
        return get_df(self.contracts.get(vt_symbol), use_df)

    def get_account(self, gateway_name: str) -> Optional[AccountData]:
        return self.accounts.get(gateway_name)

    def get_all_gateways(self) -> List[BaseGateway]:
        return list(self.gateways.values())

    def get_all_gateway_names(self) -> List[str]:
        return list(self.gateways.keys())
        
    def get_all_gateway_classes(self) -> List[Type[BaseGateway]]:
        return list(self.gateway_classes.values())

    def get_all_gateway_class_names(self) -> List[str]:
        return list(self.gateway_classes.keys())

    def get_all_ticks(self, use_df: bool = False) -> List[TickData]:
        return get_df(list(self.ticks.values()), use_df)

    def get_all_orders(self, use_df: bool = False) -> List[OrderData]:
        return get_df(list(self.orders.values()), use_df)

    def get_all_active_orders(self, use_df: bool = False) -> List[OrderData]:
        return get_df(list(self.active_orders.values()), use_df)

    def get_all_trades(self, use_df: bool = False) -> List[TradeData]:
        return get_df(list(self.trades.values()), use_df)

    def get_all_positions(self, use_df: bool = False) -> List[PositionData]:
        return get_df(list(self.positions.values()), use_df)

    def get_all_contracts(self, use_df: bool = False) -> List[ContractData]:
        return get_df(list(self.contracts.values()), use_df)

    def get_all_accounts(self, use_df: bool = False) -> List[AccountData]:
        return get_df(list(self.accounts.values()), use_df) 

    def is_gateway_inited(self, gateway_name: str) -> bool:
        gateway: Optional[BaseGateway] = self.get_gateway(gateway_name)
        if gateway:
            return gateway.td_api.contract_inited
        return False

    def susbcribe(self, vt_symbols: List[str]) -> None:
        gateway: Optional[BaseGateway] = self.get_subscribe_gateway()
        if gateway:
            for vt_symbol in vt_symbols:
                contract: Optional[ContractData] = self.get_contract(vt_symbol)
                if contract:
                    req: SubscribeRequest = SubscribeRequest(
                        symbol = contract.symbol,
                        exchange = contract.exchange
                    )
                    self._subscribe(req, gateway.gateway_name)

    def buy(self, vt_symbol: str, volume: float, gateway_name: str) -> List[str]:
        return self._send_taker_order(vt_symbol, volume, Direction.LONG, Offset.OPEN, gateway_name)
    
    def sell(self, vt_symbol: str, volume: float, gateway_name: str) -> List[str]:
        return self._send_taker_order(vt_symbol, volume, Direction.SHORT, Offset.CLOSE, gateway_name)

    def short(self, vt_symbol: str, volume: float, gateway_name: str) -> List[str]:
        return self._send_taker_order(vt_symbol, volume, Direction.SHORT, Offset.OPEN, gateway_name)

    def cover(self, vt_symbol: str, volume: float, gateway_name: str) -> List[str]:
        return self._send_taker_order(vt_symbol, volume, Direction.LONG, Offset.CLOSE, gateway_name)

    def cancel_active_order(self, vt_orderid: str) -> None:
        active_order: Optional[OrderData] = self.get_active_order(vt_orderid)
        if active_order is None:
            return
        
        req: CancelRequest = active_order.create_cancel_request()
        self._cancel_order(req, active_order.gateway_name)

    def close(self) -> None:
        self.event_engine.stop()

        for engine in self.engines.values():
            engine.close()

        for gateway in self.gateways.values():
            gateway.close()


class BaseEngine(ABC):
    def __init__(self, ma_engine:MAEngine, engine_name: str) -> None:
        self.ma_engine = ma_engine
        self.engine_name = engine_name

    def close(self) -> None:
        pass
    

class BackupEngine(BaseEngine):
    def __init__(self, ma_engine: MAEngine) -> None:
        super().__init__(ma_engine, "backup")
        self.backup_data: Dict[str, DataFrame]  = {}
        self.backup_file_paths: Dict[str, str] = {}

    def add_function(self) -> None:
        self.ma_engine.add_backup_file_path = self.add_backup_file_path
        self.ma_engine.get_backup_file_path = self.get_backup_file_path
        self.ma_engine.add_backup_data = self.add_backup_data
        self.ma_engine.get_backup_data = self.get_backup_data
        self.ma_engine.load_backup_data = self.load_backup_data
        self.ma_engine.backup = self.backup

    def add_backup_file_path(self, gateway_name: str, file_path: str) -> None:
        self.backup_file_paths[gateway_name] = file_path
    
    def get_backup_file_path(self, gateway_name: str) -> str:
        return self.backup_file_paths.get(gateway_name)

    def add_backup_data(self, gateway_name: str, data: DataFrame) -> None:
        self.backup_data[gateway_name] = data

    def get_backup_data(self, gateway_name: str) -> Optional[Any]:
        return self.backup_data.get(gateway_name)

    def load_backup_data(self, gateway_name:str) -> Optional[DataFrame]:
        file_path = self.get_backup_file_path(gateway_name)
        if pathlib.Path(file_path).exists():
            data = pandas.read_csv(file_path)
            self.add_backup_data(gateway_name, data)
            return data
        return None

    def backup(self, gateway_name: str) -> None:
        data: DataFrame = self.get_backup_data(gateway_name)
        backup_file_path: str = self.get_backup_file_path(gateway_name)
        data.to_csv(backup_file_path)

    def close(self) -> None:
        for gateway_name, data in self.backup_data:
            data.to_csv(self.get_backup_file_path(gateway_name), index = False)


class LogEngine(BaseEngine):
    def __init__(self, ma_engine: MAEngine) -> None:
        super().__init__(ma_engine, "log")

        self.logger: Logger = logging.getLogger("MAEngine")
        self.formatter = logging.Formatter("%(asctime)s  %(levelname)s: %(message)s")

        self.add_console_handler()
        self.add_file_handler()

        self.add_function()

    def add_function(self) -> None:
        self.ma_engine.debug = self.logger.debug
        self.ma_engine.info = self.logger.info
        self.ma_engine.warning = self.logger.warning
        self.ma_engine.error = self.logger.error
        self.ma_engine.critical = self.logger.critical

    def add_console_handler(self) -> None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(self.formatter)
        self.logger.addHandler(console_handler)
    
    def add_file_handler(self) -> None:
        file_name = f"{datetime.now().strftime('%Y%m%d')}.log"
        file_path = pathlib.Path(FILE_SETTING["LOG_DIR_PATH"]).joinpath(file_name)
        file_handler = logging.FileHandler(file_path, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(self.formatter)
        self.logger.addHandler(file_handler)

    