import logging

from unitelabs.cdk import sila

from unitelabs.usila_c.feature.baseCtrl import (
    CommandResult,
)
from unitelabs.usila_c.socket_client import UdsClient

logger = logging.getLogger(__name__)


class WsCommandError(Exception):
    """天平命令业务失败"""


class WsCommError(Exception):
    """天平UDS通信异常"""


class WSFeature(sila.Feature):
    # 接收外部传入uds客户端实例
    def __init__(self, uds: UdsClient):
        super().__init__(identifier="WS", version="1.0", name="WS")
        logger.info("🟢 WSFeature initialized, UDS injected")
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
            print("WSFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            print("✅WSFeature UDS连接完成")

    @sila.UnobservableCommand(name="Tare", errors=[WsCommandError])
    async def Tare(
        self,
        *,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        try:
            intermediate.send("开始去皮")
            uds = await self._get_uds()
            resp = await uds.send_request(cmd="Tare", params={}, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "tare command failed")
                raise WsCommandError(f"WS tare fail, code={ret_code}, msg={err_msg}")

            intermediate.send("去皮完成")
            return CommandResult.from_dict(
                success=True,
                message="去皮成功",
                data={
                    "status": "tare_ok",
                },
            )
        except asyncio.CancelledError:
            raise
        except WsCommandError as e:
            intermediate.send(f"去皮失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("Tare exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableProperty(name="GrossWeightGram")
    async def GrossWeightGram(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="S", params={}, timeout=10)
                ret_code = resp.get("code", -1)
                if ret_code != 0:
                    err_msg = resp.get("msg", "gross weight read failed")
                    logger.warning(f"WS GrossWeightGram fail, code={ret_code}, msg={err_msg}")
                    yield 0.0
                else:
                    weight_g = float(resp.get("result", {}).get("weight_g", 0.0))
                    yield weight_g
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"读取天平异常 {e}")
                yield 0.0
            await asyncio.sleep(2)
