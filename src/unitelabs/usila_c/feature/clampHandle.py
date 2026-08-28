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
# Transfer Feature，UDS外部注入，和DeviceBaseFeature架构对齐
# 提供物料转移功能
# -----------------------------------------------------------------------------
class CLAMPFeature(sila.Feature):
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier="CLAMP",
            name="CLAMP",
            category="application",
            version="1.0",
            description="提供物料转移功能",
        )
        logger.info("🟢 CLAMPFeature initialized, UDS injected")
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
            logger.info("CLAMPFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            logger.info("✅ CLAMPFeature UDS连接完成")

    # ------------------------------
    # Commands
    # ------------------------------
    @sila.ObservableCommand(name="TransferItem", errors=[DeviceCommandError])
    async def TransferItem(
        self,
        *,
        source_position: Position3D,
        target_position: Position3D,
        gripper_param: GripperParam,
        release_after_finish: bool,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """
        转移物料。Server自动选择夹爪Z轴。

        .. parameter:: source_position: 源位置（逻辑坐标，单位 mm）
        .. parameter:: target_position: 目标位置（逻辑坐标，单位 mm）
        .. parameter:: gripper_param: 夹爪参数（位置和力）
        .. parameter:: release_after_finish: 是否松开夹爪

        Errors:
            DeviceCommandError: 设备底层命令执行失败
        """
        try:
            intermediate.send("开始物料转移")

            uds = await self._get_uds()

            req_params = {
                "source_position": {"x": source_position.x, "y": source_position.y, "z": source_position.z},
                "target_position": {"x": target_position.x, "y": target_position.y, "z": target_position.z},
                "gripper_param": {"position": gripper_param.position, "force": gripper_param.force},
                "release_after_finish": release_after_finish,
            }

            intermediate.send("取料中...")

            # 拿到CommandExecution对象
            cmd_exec = status.command_execution

            # 单次命令的CommandExecutionUUID（uuid.UUID对象）
            exec_uuid = cmd_exec.command_execution_uuid

            # 转为字符串，用于UDS、日志、下位机通信
            exec_uuid_str = str(exec_uuid)
            intermediate.send(f"当前命令ExecutionUUID: {exec_uuid_str}")

            intermediate.send("下发取试管指令至下位机")

            resp = await uds.send_request(cmd="grab_tube", params=req_params, uuid=exec_uuid_str, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "grab_tube command failed")
                raise DeviceCommandError(f"grab_tube fail, code={ret_code}, msg={err_msg}")

            intermediate.send("下发x、y运动指令至下位机")
            resp = await uds.send_request(cmd="move_serial", params=req_params, uuid=exec_uuid_str, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "move_serial command failed")
                raise DeviceCommandError(f"move_serial fail, code={ret_code}, msg={err_msg}")

            intermediate.send("下发放下试管指令至下位机")
            resp = await uds.send_request(cmd="put_tube", params=req_params, uuid=exec_uuid_str, timeout=timeout)
            ret_code = resp.get("code", -1)

            if ret_code != 0:
                err_msg = resp.get("msg", "put_tube command failed")
                raise DeviceCommandError(f"put_tube fail, code={ret_code}, msg={err_msg}")

            intermediate.send("物料转移完成")

            return CommandResult.from_dict(
                success=True,
                message="物料转移完成",
                data={
                    "source_x": str(source_position.x),
                    "source_y": str(source_position.y),
                    "source_z": str(source_position.z),
                    "target_x": str(target_position.x),
                    "target_y": str(target_position.y),
                    "target_z": str(target_position.z),
                    "release_after_finish": str(release_after_finish),
                },
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"转移失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("TransferItem exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})
