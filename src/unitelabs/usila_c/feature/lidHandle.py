import asyncio
import logging

from unitelabs.cdk import sila

from unitelabs.usila_c.feature.devicebase import (
    CommandResult,
    DeviceCommandError,
    Position3D,
)
from unitelabs.usila_c.socket_client import UdsClient

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# LiquidHandling Feature，UDS外部注入，和DeviceBaseFeature架构对齐
# 提供分液功能
# -----------------------------------------------------------------------------
class LIDFeature(sila.Feature):
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier="LID",
            name="LID",
            category="application",
            version="1.0",
            description="提供分液功能",
        )
        logger.info("🟢 LIDFeature initialized, UDS injected")
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
            logger.info("LIDFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            logger.info("✅ LIDFeature UDS连接完成")

    # ------------------------------
    # Commands
    # ------------------------------
    @sila.ObservableCommand(name="AttachTip", errors=[DeviceCommandError])
    async def AttachTip(
        self, *, tip_position: Position3D, press_force: float, status: sila.Status, intermediate: sila.Intermediate[str]
    ) -> CommandResult:
        """
        安装Tip头。Server自动选择移液Z轴。

        .. parameter:: tip_position: Tip位置（逻辑坐标，单位 mm）
        .. parameter:: press_force: 压装力（单位 N）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            status.update(progress=0.1)
            intermediate.send("开始安装Tip头")

            uds = await self._get_uds()

            req_params = {
                "tip_position": {"x": tip_position.x, "y": tip_position.y, "z": tip_position.z},
                "press_force": press_force,
            }

            status.update(progress=0.5)
            intermediate.send("下发安装指令至下位机")

            resp = await uds.send_request(cmd="LID.AttachTip", params=req_params)

            status.update(progress=0.9)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "AttachTip command failed")
                raise DeviceCommandError(f"AttachTip fail, code={ret_code}, msg={err_msg}")

            status.update(progress=1.0)
            intermediate.send("Tip头安装完成")

            return CommandResult.from_dict(
                success=True,
                message="Tip头安装完成",
                data={
                    "tip_position_x": str(tip_position.x),
                    "tip_position_y": str(tip_position.y),
                    "tip_position_z": str(tip_position.z),
                    "press_force": str(press_force),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            status.update(progress=1.0)
            intermediate.send(f"Tip头安装失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("AttachTip exception")
            status.update(progress=1.0)
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="Aspirate", errors=[DeviceCommandError])
    async def Aspirate(
        self,
        *,
        target_position: Position3D,
        volume: float,
        aspirate_speed: float,
        immersion_depth: float,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        吸液。

        .. parameter:: target_position: 吸液位置（逻辑坐标，单位 mm）
        .. parameter:: volume: 吸液体积（单位 μL）
        .. parameter:: aspirate_speed: 吸液速度（单位 μL/s）
        .. parameter:: immersion_depth: 浸入深度（单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            status.update(progress=0.1)
            intermediate.send("开始吸液")

            uds = await self._get_uds()

            req_params = {
                "target_position": {"x": target_position.x, "y": target_position.y, "z": target_position.z},
                "volume": volume,
                "aspirate_speed": aspirate_speed,
                "immersion_depth": immersion_depth,
            }

            status.update(progress=0.4)
            intermediate.send("针头下降中...")

            status.update(progress=0.7)
            intermediate.send("下发吸液指令至下位机")

            resp = await uds.send_request(cmd="LID.Aspirate", params=req_params)

            status.update(progress=0.95)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "Aspirate command failed")
                raise DeviceCommandError(f"Aspirate fail, code={ret_code}, msg={err_msg}")

            status.update(progress=1.0)
            intermediate.send("吸液完成")

            return CommandResult.from_dict(
                success=True,
                message="吸液完成",
                data={
                    "target_position_x": str(target_position.x),
                    "target_position_y": str(target_position.y),
                    "target_position_z": str(target_position.z),
                    "volume": str(volume),
                    "aspirate_speed": str(aspirate_speed),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            status.update(progress=1.0)
            intermediate.send(f"吸液失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("Aspirate exception")
            status.update(progress=1.0)
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="Dispense", errors=[DeviceCommandError])
    async def Dispense(
        self,
        *,
        target_position: Position3D,
        volume: float,
        dispense_speed: float,
        immersion_depth: float,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        排液。

        .. parameter:: target_position: 排液位置（逻辑坐标，单位 mm）
        .. parameter:: volume: 排液体积（单位 μL）
        .. parameter:: dispense_speed: 排液速度（单位 μL/s）
        .. parameter:: immersion_depth: 浸入深度（单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            status.update(progress=0.1)
            intermediate.send("开始排液")

            uds = await self._get_uds()

            req_params = {
                "target_position": {"x": target_position.x, "y": target_position.y, "z": target_position.z},
                "volume": volume,
                "dispense_speed": dispense_speed,
                "immersion_depth": immersion_depth,
            }

            status.update(progress=0.4)
            intermediate.send("针头下降中...")

            status.update(progress=0.7)
            intermediate.send("下发排液指令至下位机")

            resp = await uds.send_request(cmd="LID.Dispense", params=req_params)

            status.update(progress=0.95)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "Dispense command failed")
                raise DeviceCommandError(f"Dispense fail, code={ret_code}, msg={err_msg}")

            status.update(progress=1.0)
            intermediate.send("排液完成")

            return CommandResult.from_dict(
                success=True,
                message="排液完成",
                data={
                    "target_position_x": str(target_position.x),
                    "target_position_y": str(target_position.y),
                    "target_position_z": str(target_position.z),
                    "volume": str(volume),
                    "dispense_speed": str(dispense_speed),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            status.update(progress=1.0)
            intermediate.send(f"排液失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("Dispense exception")
            status.update(progress=1.0)
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="EjectTip", errors=[DeviceCommandError])
    async def EjectTip(
        self,
        *,
        eject_position: Position3D,
        eject_force: float,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        退Tip头。

        .. parameter:: eject_position: 退Tip位置（逻辑坐标，单位 mm）
        .. parameter:: eject_force: 退Tip力（单位 N）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            status.update(progress=0.1)
            intermediate.send("开始退Tip头")

            uds = await self._get_uds()

            req_params = {
                "eject_position": {"x": eject_position.x, "y": eject_position.y, "z": eject_position.z},
                "eject_force": eject_force,
            }

            status.update(progress=0.5)
            intermediate.send("下发退Tip指令至下位机")

            resp = await uds.send_request(cmd="LID.EjectTip", params=req_params)

            status.update(progress=0.9)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "EjectTip command failed")
                raise DeviceCommandError(f"EjectTip fail, code={ret_code}, msg={err_msg}")

            status.update(progress=1.0)
            intermediate.send("Tip头退出完成")

            return CommandResult.from_dict(
                success=True,
                message="Tip头退出完成",
                data={
                    "eject_position_x": str(eject_position.x),
                    "eject_position_y": str(eject_position.y),
                    "eject_position_z": str(eject_position.z),
                    "eject_force": str(eject_force),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            status.update(progress=1.0)
            intermediate.send(f"Tip头退出失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("EjectTip exception")
            status.update(progress=1.0)
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})
