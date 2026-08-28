import asyncio
import logging

from unitelabs.cdk import sila

from unitelabs.usila_c.feature.baseCtrl import CommandResult, DeviceCommandError
from unitelabs.usila_c.socket_client import UdsClient

logger = logging.getLogger(__name__)


class DebugFeature(sila.Feature):
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier="Debug",
            name="Debug",
            category="application",
            version="1.0",
            description="调试模式功能集合，包含夹爪调试、轴单步调试、LED控制、移液器调试等功能",
        )
        logger.info("🟢 DebugFeature initialized, UDS injected")
        self.uds: UdsClient = uds
        self._connected: bool = False

    async def _get_uds(self) -> UdsClient:
        """获取UDS客户端，做连接状态校验，与DeviceBaseFeature保持一致"""
        if self.uds is None:
            raise sila.DeviceError("UDS客户端实例为空，设备未初始化")
        await self._ensure_conn()
        return self.uds

    async def _ensure_conn(self):
        """第一次调用命令时才建立UDS连接"""
        if not self._connected:
            logger.info("DebugFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            logger.info("✅ DebugFeature UDS连接完成")

    @sila.ObservableCommand(name="GripperRelease", errors=[DeviceCommandError])
    async def GripperRelease(
        self,
        *,
        speed: float,
        position: float,
        force: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """以指定速度、力矩将夹爪松开至指定位置"""
        try:
            intermediate.send("开始夹爪松开")
            uds = await self._get_uds()
            params = {"speed": speed, "position": position, "force": force}

            intermediate.send("下发夹爪松开指令至下位机")
            resp = await uds.send_request(cmd="GripperRelease", params=params, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "GripperRelease command failed")
                raise DeviceCommandError(f"GripperRelease fail, code={ret_code}, msg={err_msg}")

            intermediate.send("夹爪松开完成")
            return CommandResult.from_dict(
                True,
                "夹爪松开完成",
                {"speed": str(speed), "position": str(position), "force": str(force)},
            )
        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"夹爪松开失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("GripperRelease exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="GripperGrasp", errors=[DeviceCommandError])
    async def GripperGrasp(
        self,
        *,
        speed: float,
        position: float,
        force: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """以指定速度、力矩将夹爪夹紧至指定位置"""
        try:
            intermediate.send("开始夹爪夹紧")
            uds = await self._get_uds()
            params = {"speed": speed, "position": position, "force": force}

            intermediate.send("下发夹爪夹紧指令至下位机")
            resp = await uds.send_request(cmd="GripperGrasp", params=params, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "GripperGrasp command failed")
                raise DeviceCommandError(f"GripperGrasp fail, code={ret_code}, msg={err_msg}")

            intermediate.send("夹爪夹紧完成")
            return CommandResult.from_dict(
                True,
                "夹爪夹紧完成",
                {"speed": str(speed), "position": str(position), "force": str(force)},
            )
        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"夹爪夹紧失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("GripperGrasp exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="GripperRotate", errors=[DeviceCommandError])
    async def GripperRotate(
        self,
        *,
        speed: float,
        position: float,
        force: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """以指定速度、力矩旋转夹爪至指定角度"""
        try:
            intermediate.send("开始夹爪旋转")
            uds = await self._get_uds()
            params = {"speed": speed, "position": position, "force": force}

            intermediate.send("下发夹爪旋转指令至下位机")
            resp = await uds.send_request(cmd="GripperRotate", params=params, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "GripperRotate command failed")
                raise DeviceCommandError(f"GripperRotate fail, code={ret_code}, msg={err_msg}")

            intermediate.send("夹爪旋转完成")
            return CommandResult.from_dict(
                True,
                "夹爪旋转完成",
                {"speed": str(speed), "position": str(position), "force": str(force)},
            )
        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"夹爪旋转失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("GripperRotate exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="GripperHome", errors=[DeviceCommandError])
    async def GripperHome(
        self,
        *,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """夹爪回零点"""
        try:
            intermediate.send("开始夹爪归零")
            uds = await self._get_uds()
            intermediate.send("下发夹爪归零指令至下位机")
            resp = await uds.send_request(cmd="GripperHome", params={}, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "GripperHome command failed")
                raise DeviceCommandError(f"GripperHome fail, code={ret_code}, msg={err_msg}")

            intermediate.send("夹爪归零完成")
            return CommandResult.from_dict(True, "夹爪归零完成", {})
        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"夹爪归零失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("GripperHome exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableCommand(name="AxisStepMove", errors=[DeviceCommandError])
    async def AxisStepMove(
        self,
        *,
        axis: str,
        speed: float,
        position: float,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """指定轴以指定速度单步移动到目标位置"""
        try:
            valid_axes = {"X_M", "Y_M", "FFQ_M", "LID_M", "CLAM_Z", "PRESS_M", "ROTATE_M", "JF_M", "ZD_M"}
            if axis not in valid_axes:
                raise DeviceCommandError(f"AxisStepMove invalid axis={axis!r}, supported={sorted(valid_axes)}")

            intermediate.send(f"开始{axis}轴单步移动")
            uds = await self._get_uds()
            params = {"t": axis, "spd": speed, "atc": position}

            intermediate.send("下发轴单步移动指令至下位机")
            resp = await uds.send_request(cmd="mov", params=params, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "AxisStepMove command failed")
                raise DeviceCommandError(f"AxisStepMove fail, code={ret_code}, msg={err_msg}")

            intermediate.send(f"{axis}轴单步移动完成")
            return CommandResult.from_dict(
                True,
                f"{axis}轴单步移动完成",
                {"axis": axis, "speed": str(speed), "position": str(position)},
            )
        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"轴单步移动失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("AxisStepMove exception")
            err_msg = f"通信超时:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.UnobservableCommand(name="LedOn", errors=[DeviceCommandError])
    async def LedOn(self, *, index: int, timeout: int = 10) -> CommandResult:
        """打开指定索引的LED"""
        try:
            uds = await self._get_uds()
            resp = await uds.send_request(cmd="LedOn", params={"index": index}, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "LedOn command failed")
                raise DeviceCommandError(f"LedOn fail, code={ret_code}, msg={err_msg}")
            return CommandResult.from_dict(True, "LED打开成功", {"index": str(index)})
        except DeviceCommandError as e:
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("LedOn exception")
            return CommandResult.from_dict(False, f"通信异常:{e!s}", {})

    @sila.UnobservableCommand(name="LedOff", errors=[DeviceCommandError])
    async def LedOff(self, *, index: int, timeout: int = 10) -> CommandResult:
        """关闭指定索引的LED"""
        try:
            uds = await self._get_uds()
            resp = await uds.send_request(cmd="LedOff", params={"index": index}, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "LedOff command failed")
                raise DeviceCommandError(f"LedOff fail, code={ret_code}, msg={err_msg}")
            return CommandResult.from_dict(True, "LED关闭成功", {"index": str(index)})
        except DeviceCommandError as e:
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("LedOff exception")
            return CommandResult.from_dict(False, f"通信异常:{e!s}", {})

    @sila.ObservableCommand(name="PipettorHome", errors=[DeviceCommandError])
    async def PipettorHome(
        self,
        *,
        timeout: int = 10,
        status: sila.Status,
        intermediate: sila.Intermediate[str],
    ) -> CommandResult:
        """移液器回零点"""
        try:
            intermediate.send("开始移液器归零")
            uds = await self._get_uds()
            intermediate.send("下发移液器归零指令至下位机")
            resp = await uds.send_request(cmd="It", params={}, timeout=timeout)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "PipettorHome command failed")
                raise DeviceCommandError(f"PipettorHome fail, code={ret_code}, msg={err_msg}")

            intermediate.send("移液器归零完成")
            return CommandResult.from_dict(True, "移液器归零完成", {})
        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            intermediate.send(f"移液器归零失败:{e!s}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("PipettorHome exception")
            err_msg = f"通信异常:{e!s}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

    @sila.ObservableProperty(name="PipettorPressure")
    async def PipettorPressure(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="Qp", params={}, timeout=10)
                result = resp.get("result", {})
                pressure = result.get("pressure", result.get("value", 0.0))
                yield float(pressure)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"读取PipettorPressure异常 {e}")
                yield 0.0
            await asyncio.sleep(0.2)

    @sila.ObservableProperty(name="PipettorWorkState")
    async def PipettorWorkState(self) -> int:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="GetPipettorWorkState", params={}, timeout=10)
                result = resp.get("result", {})
                state = result.get("state", result.get("status", 0))
                yield int(state)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"读取PipettorWorkState异常 {e}")
                yield 0
            await asyncio.sleep(0.2)
