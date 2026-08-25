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
    @sila.ObservableCommand(name="rotate_open", errors=[DeviceCommandError])
    async def OpenCap(
        self,
        *,
        mode: str,
        container_diameter: float,
        open_position: Position3D,
        cap_place_position: Position3D,
        open_gripper_param: GripperParam,
        close_gripper_param: GripperParam,
        rotation_cycles: int,
        rotation_speed: float,
        rotation_force: float,
        z_lift_height: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        开盖。Server自动选择夹爪Z轴。

        .. parameter:: mode: 模式,open/close
        .. parameter:: container_diameter: 容器直径（单位 mm）
        .. parameter:: open_position: 开盖位置（逻辑坐标，单位 mm）
        .. parameter:: cap_place_position: 盖子放置位置（逻辑坐标，单位 mm）
        .. parameter:: open_gripper_param: 开盖夹爪参数
        .. parameter:: close_gripper_param: 关盖夹爪参数
        .. parameter:: rotation_cycles: 旋转圈数
        .. parameter:: rotation_speed: 旋转速度（单位 rpm）
        .. parameter:: rotation_force: 旋转力矩（单位 N·m）
        .. parameter:: z_lift_height: Z抬升高度（单位 mm）

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始开盖")

            uds = await self._get_uds()

            req_params = {
                "container_diameter": container_diameter,
                "open_position": {"x": open_position.x, "y": open_position.y, "z": open_position.z},
                "cap_place_position": {"x": cap_place_position.x, "y": cap_place_position.y, "z": cap_place_position.z},
                "open_gripper_param": {"position": open_gripper_param.position, "force": open_gripper_param.force},
                "close_gripper_param": {"position": close_gripper_param.position, "force": close_gripper_param.force},
                "rotation_cycles": rotation_cycles,
                "rotation_speed": rotation_speed,
                "rotation_force": rotation_force,
                "z_lift_height": z_lift_height,
            }

            intermediate.send("夹紧容器")

            if mode == "open":
                resp = await uds.send_request(cmd="rotate_open", params=req_params, timeout=timeout)
                intermediate.send("旋转开盖中...")
            else:
                resp = await uds.send_request(cmd="rotate_close", params=req_params, timeout=timeout)
                intermediate.send("旋转关盖中...")
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "rotate_open command failed")
                raise DeviceCommandError(f"rotate_open fail, code={ret_code}, msg={err_msg}")

            intermediate.send("开盖完成")

            return CommandResult.from_dict(
                success=True,
                message="开盖完成",
                data={
                    "container_diameter": str(container_diameter),
                    "rotation_cycles": str(rotation_cycles),
                    "rotation_speed": str(rotation_speed),
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
