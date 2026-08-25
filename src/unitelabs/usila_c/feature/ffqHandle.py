import asyncio
import logging

from unitelabs.cdk import sila

from unitelabs.usila_c.feature.baseCtrl import (
    CommandResult,
    DeviceCommandError,
    Position3D,
)
from unitelabs.usila_c.socket_client import UdsClient

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# PowderDosing Feature，UDS外部注入，和DeviceBaseFeature架构对齐
# 提供粉体装载、卸载、取粉、吐粉功能
# -----------------------------------------------------------------------------
class FFQFeature(sila.Feature):
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier="FFQ",
            name="FFQ",
            category="application",
            version="1.0",
            description="提供粉体装载、卸载、取粉、吐粉功能",
        )
        logger.info("🟢 FFQFeature initialized, UDS injected")
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
            logger.info("FFQFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            logger.info("✅ FFQFeature UDS连接完成")

    # ------------------------------
    # Commands
    # ------------------------------
    @sila.ObservableCommand(name="LoadPowderBucket", errors=[DeviceCommandError])
    async def LoadPowderBucket(
        self,
        *,
        load_position: Position3D,
        type: int = 1,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
        ctx: ExecutionContext,
    ) -> CommandResult:
        """
        装载粉桶。Server自动选择分粉Z轴，解算电机坐标后执行。

        .. parameter:: load_position: 装载位置（逻辑坐标，单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始装载粉桶")

            uds = await self._get_uds()

            exec_uuid = ctx.execution_uuid
            intermediate.send(f"当前命令ExecutionUUID: {exec_uuid}")

            req_params = {"load_position": {"x": load_position.x, "y": load_position.y, "z": load_position.z}}

            intermediate.send("下发装载指令至下位机")

            if type == 1:
                resp = await uds.send_request(cmd="load_bucket_1", params=req_params, timeout=timeout)
            elif type == 2:
                resp = await uds.send_request(cmd="load_bucket_2", params=req_params, timeout=timeout)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "load_bucket command failed")
                raise DeviceCommandError(f"load_bucket fail, code={ret_code}, msg={err_msg}")

            intermediate.send("粉桶装载完成")

            return CommandResult.from_dict(
                success=True,
                message="粉桶装载完成",
                data={
                    "load_position_x": str(load_position.x),
                    "load_position_y": str(load_position.y),
                    "load_position_z": str(load_position.z),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"装载失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("LoadPowderBucket exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="UnloadPowderBucket", errors=[DeviceCommandError])
    async def UnloadPowderBucket(
        self,
        *,
        unload_position: Position3D,
        type: int = 1,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        卸载粉桶。

        .. parameter:: unload_position: 卸载位置（逻辑坐标，单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始卸载粉桶")

            uds = await self._get_uds()

            req_params = {"unload_position": {"x": unload_position.x, "y": unload_position.y, "z": unload_position.z}}

            intermediate.send("下发卸载指令至下位机")

            if type == 1:
                resp = await uds.send_request(cmd="unload_bucket_1", params=req_params, timeout=timeout)
            elif type == 2:
                resp = await uds.send_request(cmd="unload_bucket_2", params=req_params, timeout=timeout)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "unload_bucket command failed")
                raise DeviceCommandError(f"unload_bucket fail, code={ret_code}, msg={err_msg}")

            intermediate.send("粉桶卸载完成")

            return CommandResult.from_dict(
                success=True,
                message="粉桶卸载完成",
                data={
                    "unload_position_x": str(unload_position.x),
                    "unload_position_y": str(unload_position.y),
                    "unload_position_z": str(unload_position.z),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"卸载失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("UnloadPowderBucket exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="PickPowder", errors=[DeviceCommandError])
    async def PickPowder(
        self,
        *,
        target_x: float,
        target_y: float,
        powder_surface_z: float,
        pick_depth: float,
        compact_depth: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        取粉。Server自动选择分粉Z轴。

        .. parameter:: target_x: 目标X坐标（逻辑坐标，单位 mm）
        .. parameter:: target_y: 目标Y坐标（逻辑坐标，单位 mm）
        .. parameter:: powder_surface_z: 粉面高度Z（逻辑坐标，单位 mm）
        .. parameter:: pick_depth: 取粉深度（单位 mm）
        .. parameter:: compact_depth: 压实深度（单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始取粉")

            uds = await self._get_uds()

            req_params = {
                "target_x": target_x,
                "target_y": target_y,
                "powder_surface_z": powder_surface_z,
                "pick_depth": pick_depth,
                "compact_depth": compact_depth,
            }

            intermediate.send("下发取粉指令至下位机")

            resp = await uds.send_request(cmd="take_powder", params=req_params, timeout=timeout)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "take_powder command failed")
                raise DeviceCommandError(f"take_powder fail, code={ret_code}, msg={err_msg}")

            intermediate.send("取粉完成")

            return CommandResult.from_dict(
                success=True,
                message="取粉完成",
                data={
                    "target_x": str(target_x),
                    "target_y": str(target_y),
                    "powder_surface_z": str(powder_surface_z),
                    "pick_depth": str(pick_depth),
                    "compact_depth": str(compact_depth),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"取粉失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("PickPowder exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="DispensePowder", errors=[DeviceCommandError])
    async def DispensePowder(
        self,
        *,
        target_position: Position3D,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        吐粉。

        .. parameter:: target_position: 吐粉目标位置（逻辑坐标，单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始吐粉")

            uds = await self._get_uds()

            req_params = {"target_position": {"x": target_position.x, "y": target_position.y, "z": target_position.z}}

            intermediate.send("下发吐粉指令至下位机")

            resp = await uds.send_request(cmd="spit_powder_1", params=req_params, timeout=timeout)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "spit_powder_1 command failed")
                raise DeviceCommandError(f"spit_powder_1 fail, code={ret_code}, msg={err_msg}")

            intermediate.send("吐粉完成")

            return CommandResult.from_dict(
                success=True,
                message="吐粉完成",
                data={
                    "target_position_x": str(target_position.x),
                    "target_position_y": str(target_position.y),
                    "target_position_z": str(target_position.z),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"吐粉失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("DispensePowder exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})
