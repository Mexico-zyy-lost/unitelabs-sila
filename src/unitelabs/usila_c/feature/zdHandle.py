import asyncio
import logging

from unitelabs.cdk import sila

from unitelabs.usila_c.feature.baseCtrl import (
    CommandResult,
    DeviceCommandError,
)
from unitelabs.usila_c.socket_client import UdsClient

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Vortex Feature，UDS外部注入，和DeviceBaseFeature架构对齐
# 提供振荡功能
# -----------------------------------------------------------------------------
class ZDFeature(sila.Feature):
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier="ZD", name="ZD", category="application", version="1.0", description="提供粉体振荡功能"
        )
        logger.info("🟢 ZDFeature initialized, UDS injected")
        self.uds: UdsClient = uds
        self._connected: bool = False

    async def _get_uds(self) -> UdsClient:
        """获取UDS客户端，做连接状态校验，与DeviceBaseFeature保持一致"""
        if self.uds is None:
            raise sila.DeviceError("UDS客户端实例为空，设备未初始化")
        await self._ensure_conn()
        return self.uds

    async def _ensure_conn(self):
        """懒连接，第一次命令调用才建立UDS连接"""
        if not self._connected:
            logger.info("ZDFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            logger.info("✅ ZDFeature UDS连接完成")

    # ------------------------------
    # Commands
    # ------------------------------
    @sila.ObservableCommand(name="StartVortex", errors=[DeviceCommandError])
    async def StartVortex(
        self,
        *,
        duration: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        执行振荡。

        .. parameter:: duration: 振荡时长（单位 ms）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始执行振荡")

            uds = await self._get_uds()

            req_params = {
                "duration": duration,
            }

            intermediate.send("下发振荡指令至下位机")

            resp = await uds.send_request(cmd="StartVortex", params=req_params, timeout=timeout)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "StartVortex command failed")
                raise DeviceCommandError(f"StartVortex fail, code={ret_code}, msg={err_msg}")

            intermediate.send("振荡完成")

            return CommandResult.from_dict(
                success=True,
                message="振荡完成",
                data={
                    "duration_ms": str(duration),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"振荡失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("StartVortex exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})
