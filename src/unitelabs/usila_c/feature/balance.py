import logging
import asyncio
from unitelabs.cdk import sila
from unitelabs.usila_c.socket_client import UdsClient
import socket

logger = logging.getLogger(__name__)

class BalanceCommandError(Exception):
    """天平命令业务失败"""
    pass

class BalanceCommError(Exception):
    """天平UDS通信异常"""
    pass

class BalanceFeature(sila.Feature):
    # 接收外部传入uds客户端实例
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier="Balance",
            version="1.0",
            name="Balance"
        )
        logger.info("🟢 BalanceFeature initialized, UDS injected")
        # 使用传入的参数，不要再读取全局SHARED_UDS
        self.uds: UdsClient = uds
        self._connected: bool = False

    async def _get_uds(self) -> UdsClient:
        """获取UDS客户端，做连接状态校验"""
        # 判空保护
        if self.uds is None:
            raise sila.DeviceError("UDS客户端实例为空，设备未初始化")

        # 👉 先尝试懒连接
        await self._ensure_conn()

        return self.uds

    async def _ensure_conn(self):
        """第一次调用命令时才建立UDS连接，规避CDK静默加载失败问题"""
        if not self._connected:
            print("BalanceFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            print("✅BalanceFeature UDS连接完成")

    @sila.UnobservableCommand()
    async def Tare(self) -> None:
        uds = await self._get_uds()
        resp = await uds.send_request(cmd="Balance.Tare", params={})
        ret_code = resp.get("code", -1)
        if ret_code != 0:
            err_msg = resp.get("msg", "tare command failed")
            raise BalanceCommandError(f"Balance tare fail, code={ret_code}, msg={err_msg}")

    @sila.ObservableProperty()
    async def GrossWeightGram(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="Balance.GetGrossWeight", params={})
                yield float(resp["result"]["weight_g"])
            except Exception as e:
                print(f"读取天平异常 {e}")
            await asyncio.sleep(2) #轮询间隔