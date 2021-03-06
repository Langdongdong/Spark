from typing import Any, Dict
from vnpy_ctp import CtpGateway
from vnpy_rohon import RohonGateway
# 180.168.146.187:10201
# 180.168.146.187:10211
# 180.168.146.187:10130
# 180.168.146.187:10131

# Set the file path params.
FILE_SETTING = {
    "LOAD_DIR_PATH": "Z:/position/TRADE/",
    "POSITION_DIR_PATH": "Z:/HOLD/",
    "BACKUP_DIR_PATH": "Z:/backup/",
}

# Set the Sniper algo params.
SNIPER_SETTING = {
    "INTERVAL": 10,
    "HIT": 5,
    "LIMIT": 5
}

configs: Dict[str, Any] = {
    "accounts": {
        "DDTEST1": {
            "用户名": "083231",
            "密码": "wodenvshen199!",
            "经纪商代码": "9999",
            "交易服务器": "180.168.146.187:10201",
            "行情服务器": "180.168.146.187:10211",
            "产品名称": "simnow_client_test",
            "授权编码": "0000000000000000",
            "gateway": CtpGateway
        },
        # "DDTEST2": {
        #     "用户名": "201414",
        #     "密码": "wodenvshen199!",
        #     "经纪商代码": "9999",
        #     "交易服务器": "180.168.146.187:10130",
        #     "行情服务器": "180.168.146.187:10131",
        #     "产品名称": "simnow_client_test",
        #     "授权编码": "0000000000000000",
        #     "gateway": "CtpGateway"
        # }
    },

    
}