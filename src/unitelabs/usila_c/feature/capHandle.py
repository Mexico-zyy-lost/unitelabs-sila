import asyncio
import logging

from unitelabs.cdk import sila

from unitelabs.usila_c.feature.baseCtrl import (
    CommandResult,
    DeviceCommandError,
    GripperParam,
    Position3D,
)
from unitelabs.usila_c.socket_client import UdsClient

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# CAP Feature，UDS外部注入，和DeviceBaseFeature架构对齐
# 提供容器开关盖功能
# -----------------------------------------------------------------------------
class CAPFeature(sila.Feature):
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier="CAP",
            name="CAP",
            category="application",
            version="1.0",
            description="提供容器开关盖功能",
        )
        logger.info("🟢 CAPFeature initialized, UDS injected")
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
            logger.info("CAPFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            logger.info("✅ CAPFeature UDS连接完成")

    # ------------------------------
    # Commands
    # ------------------------------
    @sila.ObservableCommand(name="OpenLid", errors=[DeviceCommandError])
    async def OpenCap(
        self,
        *,
        ContainerDiameter: float,
        OpenPosition: Position3D,
        LidPlacePosition: Position3D,
        OpenGripperParam: GripperParam,
        RotationCycles: int,
        RotationSpeed: float,
        RotationForce: float,
        ZLiftHeight: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        开盖。Server自动选择夹爪Z轴。

        .. parameter:: ContainerDiameter: 容器直径（单位 mm）
        .. parameter:: OpenPosition: 开盖位置（逻辑坐标，单位 mm）
        .. parameter:: LidPlacePosition: 盖子放置位置（逻辑坐标，单位 mm）
        .. parameter:: OpenGripperParam: 开盖夹爪参数
        .. parameter:: RotationCycles: 旋转圈数
        .. parameter:: RotationSpeed: 旋转速度（单位 rpm）
        .. parameter:: RotationForce: 旋转力矩（单位 N·m）
        .. parameter:: ZLiftHeight: Z抬升高度（单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始开盖")

            uds = await self._get_uds()

            req_params = {
                "container_diameter": ContainerDiameter,
                "OpenPosition": {"x": OpenPosition.x, "y": OpenPosition.y, "z": OpenPosition.z},
                "cap_place_position": {"x": LidPlacePosition.x, "y": LidPlacePosition.y, "z": LidPlacePosition.z},
                "open_gripper_param": {"tod": OpenGripperParam.position, "mot": OpenGripperParam.force},
                "rotation_cycles": RotationCycles,
                "rotation_speed": RotationSpeed,
                "rotation_force": RotationForce,
                "z_lift_height": ZLiftHeight,
            }

            intermediate.send("夹紧容器")

            # 拿到CommandExecution对象
            cmd_exec = status.command_execution

            # 单次命令的CommandExecutionUUID（uuid.UUID对象）
            exec_uuid = cmd_exec.command_execution_uuid

            # 转为字符串，用于UDS、日志、下位机通信
            exec_uuid_str = str(exec_uuid)

            intermediate.send(f"当前命令ExecutionUUID: {exec_uuid_str}")

            resp = await uds.send_request(cmd="rotate_open", params=req_params, uuid=exec_uuid_str, timeout=timeout)
            intermediate.send("旋转开盖中...")
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "rotate_open command failed")
                raise DeviceCommandError(f"rotate_open fail, code={ret_code}, msg={err_msg}")

            intermediate.send("开盖完成")

            return CommandResult.from_dict(
                success=True,
                message="开盖完成",
                data={
                    "container_diameter": str(ContainerDiameter),
                    "rotation_cycles": str(RotationCycles),
                    "rotation_speed": str(RotationSpeed),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"开盖失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("OpenCap exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="CloseLid", errors=[DeviceCommandError])
    async def CloseCap(
        self,
        *,
        ContainerDiameter: float,
        ClosePosition: Position3D,
        LidPickPosition: Position3D,
        CloseGripperParam: GripperParam,
        RotationCycles: int,
        RotationSpeed: float,
        RotationForce: float,
        ZLiftHeight: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        关盖。Server自动选择夹爪Z轴。

        .. parameter:: ContainerDiameter: 容器直径（单位 mm）
        .. parameter:: ClosePosition: 关盖位置（逻辑坐标，单位 mm）
        .. parameter:: LidPickPosition: 盖子放置位置（逻辑坐标，单位 mm）
        .. parameter:: CloseGripperParam: 关盖夹爪参数
        .. parameter:: RotationCycles: 旋转圈数
        .. parameter:: RotationSpeed: 旋转速度（单位 rpm）
        .. parameter:: RotationForce: 旋转力矩（单位 N·m）
        .. parameter:: ZLiftHeight: Z抬升高度（单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始关盖")

            uds = await self._get_uds()

            req_params = {
                "container_diameter": ContainerDiameter,
                "close_position": {"x": ClosePosition.x, "y": ClosePosition.y, "z": ClosePosition.z},
                "cap_place_position": {"x": LidPickPosition.x, "y": LidPickPosition.y, "z": LidPickPosition.z},
                "close_gripper_param": {"position": CloseGripperParam.position, "force": CloseGripperParam.force},
                "rotation_cycles": RotationCycles,
                "rotation_speed": RotationSpeed,
                "rotation_force": RotationForce,
                "z_lift_height": ZLiftHeight,
            }

            intermediate.send("夹紧容器")

            # 拿到CommandExecution对象
            cmd_exec = status.command_execution

            # 单次命令的CommandExecutionUUID（uuid.UUID对象）
            exec_uuid = cmd_exec.command_execution_uuid

            # 转为字符串，用于UDS、日志、下位机通信
            exec_uuid_str = str(exec_uuid)

            intermediate.send(f"当前命令ExecutionUUID: {exec_uuid_str}")

            resp = await uds.send_request(cmd="rotate_close", params=req_params, uuid=exec_uuid_str, timeout=timeout)
            intermediate.send("旋转关盖中...")
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "rotate_close command failed")
                raise DeviceCommandError(f"rotate_close fail, code={ret_code}, msg={err_msg}")

            intermediate.send("关盖完成")

            return CommandResult.from_dict(
                success=True,
                message="关盖完成",
                data={
                    "container_diameter": str(container_diameter),
                    "rotation_cycles": str(rotation_cycles),
                    "rotation_speed": str(rotation_speed),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"关盖失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("CloseCap exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})
