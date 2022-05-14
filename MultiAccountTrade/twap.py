import asyncio, math
from typing import List, Dict

from pandas import DataFrame

from engine import  MAEngine
from constant import OrderMode
from object import OrderAsking

class TWAP():
    def __init__(self, engine: MAEngine, gateway_name: str, request: OrderAsking, setting: Dict[str, int]) -> None:
        self.engine: MAEngine = engine
        self.gateway_name: str = gateway_name
        self.request: OrderAsking = request
        
        self.time: int = setting.get("TIME")
        self.interval: int = setting.get("INTERVAL")

        self.vt_orderids: List[str] = []
        self.traded_volume: float = 0
        self.twap_volume: float = self.get_twap_volume()

        self.engine.log(f"Excecute TWAP {self.request.vt_symbol} {self.request.order_mode.value} {self.request.volume}", self.gateway_name)

    async def run(self) -> None:
        while self.traded_volume < self.request.volume:
            self.send_order()
            await asyncio.sleep(self.interval)
            self.cancel_active_orders()
            await asyncio.sleep(1)
            self.update_traded_volume()
            backup(
                self.engine,
                self.gateway_name,
                self.request,
                self.request.volume - self.traded_volume
                )
        
        self.engine.log(f"Complete TWAP {self.request.vt_symbol}", self.gateway_name)
            
    def send_order(self) -> List[str]:
        volume = min(self.twap_volume, self.request.volume - self.traded_volume)
        if self.request.order_mode == OrderMode.BUY:
            self.vt_orderids = self.engine.buy(self.request.vt_symbol, volume, self.gateway_name)
        elif self.request.order_mode == OrderMode.SELL:
            self.vt_orderids = self.engine.sell(self.request.vt_symbol, volume, self.gateway_name)
        elif self.request.order_mode == OrderMode.SHORT:
            self.vt_orderids = self.engine.short(self.request.vt_symbol, volume, self.gateway_name)
        elif self.request.order_mode == OrderMode.COVER:
            self.vt_orderids = self.engine.cover(self.request.vt_symbol, volume, self.gateway_name)

    def cancel_active_orders(self) -> None:
        for vt_orderid in self.vt_orderids:
            active_order = self.engine.get_active_order(vt_orderid)
            if active_order:
                self.engine.canor
            self.engine.cancel_active_order(vt_orderid)

    def update_traded_volume(self) -> None:
        for vt_orderid in self.vt_orderids:
            order = self.engine.get_order(vt_orderid)
            if order:
                self.traded_volume += order.traded        

    def get_twap_volume(self) -> float:
        return max(float(math.floor(self.request.volume / (self.time / self.interval))), 1.0)


def backup(engine: MAEngine, gateway_name: str, request: OrderAsking, left_volume: float):
    data: DataFrame = engine.get_backup_data(gateway_name)

    idx = data.loc[
        (data["ContractID"] == request.ContractID) &
        (data["Op1"] == request.Op1) &
        (data["Op2"] == request.Op2)
    ].index.values[0]
    data.loc[idx, "Num"] = left_volume

    engine.backup(gateway_name)

    engine.log(f"Backup {request.vt_symbol} {request.order_mode.value} left {left_volume}", gateway_name)