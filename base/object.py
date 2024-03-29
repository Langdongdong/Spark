from dataclasses import dataclass

from .constant import OrderRequestType
from vnpy.trader.constant import Exchange

@dataclass
class OrderRequest:
    ContractID: str
    Op1: str
    Op2: str
    volume: float

    def __post_init__(self) -> None:
        self.vt_symbol = OrderRequest.convert_to_vt_symbol(self.ContractID)
        self.order_request_type = OrderRequest.convert_to_order_request_type(self.Op1, self.Op2)

    @staticmethod
    def convert_to_vt_symbol(symbol: str) -> str:
        spl = symbol.split(".")
        pre = spl[0].lower()
        suf = spl[1]

        if suf == "CZC":
            pre = pre.upper()
            suf = Exchange.CZCE.value

        elif suf == "SHF":
            suf = Exchange.SHFE.value

        return f"{pre}.{suf}"

    @staticmethod
    def convert_to_order_request_type(Op1: str, Op2: str) -> OrderRequestType:
        if Op1 == "Open":
            if Op2 == "Buy":
                return OrderRequestType.BUY
            else:
                return OrderRequestType.SHORT
        else:
            if Op2 == "Buy":
                return OrderRequestType.COVER
            else:
                return OrderRequestType.SELL