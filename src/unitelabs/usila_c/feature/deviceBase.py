from dataclasses import dataclass
import typing
import asyncio
import logging
from unitelabs.cdk import sila
from unitelabs.usila_c.socket_client import UdsClient

logger = logging.getLogger(__name__)


class DeviceCommandError(Exception):
    """设备业务命令执行失败"""
    pass


class DeviceCommError(Exception):
    """设备UDS底层通信异常"""
    pass


# -----------------------------------------------------------------------------
# 通用SiLA Struct 定义
# -----------------------------------------------------------------------------
@dataclass
class KeyValueItem(sila.CustomDataType):
    """键值对项，用于模拟 map<string, string>。

    Attributes:
        Key: 键
        Value: 值
    """
    key: str
    value: str

@dataclass
class CommandResult(sila.CustomDataType):
    """命令执行结果。

    Attributes:
        Success: 是否成功
        Message: 结果消息
        Data: 附加键值数据列表
    """
    success: bool
    message: str
    data: typing.List[KeyValueItem]

    @staticmethod
    def from_dict(success: bool, message: str, data: typing.Dict[str, str]) -> "CommandResult":
        kv_list = [KeyValueItem(key=k, value=v) for k, v in data.items()]
        return CommandResult(success=success, message=message, data=kv_list)

    def to_dict(self) -> typing.Dict[str, str]:
        return {item.key: item.value for item in self.data}


@dataclass
class Position3D(sila.CustomDataType):
    """逻辑坐标（单位 mm）。

    Attributes:
        X: X 坐标
        Y: Y 坐标
        Z: Z 坐标
    """
    x: float
    y: float
    z: float


@dataclass
class MotorPosition3D(sila.CustomDataType):
    """电机坐标（pulse / mm）。

    Attributes:
        Mx: 电机 X
        My: 电机 Y
        Mz: 电机 Z
    """
    mx: float
    my: float
    mz: float


@dataclass
class CalibrationPair(sila.CustomDataType):
    """标定点对。

    Attributes:
        LogicalPos: 逻辑坐标
        MotorPos: 电机坐标
    """
    logical_pos: Position3D
    motor_pos: MotorPosition3D


@dataclass
class GripperParam(sila.CustomDataType):
    """夹爪参数。

    Attributes:
        Position: 位置
        Force: 力
    """
    position: float
    force: float


# -----------------------------------------------------------------------------
# DeviceBase Feature，UDS外部注入，和BalanceFeature架构对齐
            #description = "提供设备初始化、急停、通用参数设置、坐标标定及状态查询功能",

# -----------------------------------------------------------------------------
class DeviceBaseFeature(sila.Feature):
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier = "DeviceBase",
            name = "DeviceBase",
            category = "core",
            version = "1.0"
        )
        logger.info("🟢 DeviceBaseFeature initialized, UDS injected")
        self.uds: UdsClient = uds
        self._connected: bool = False

    async def _get_uds(self) -> UdsClient:
        """获取UDS客户端，做连接状态校验，与BalanceFeature保持一致"""
        if self.uds is None:
            raise sila.DeviceError("UDS客户端实例为空，设备未初始化")
        await self._ensure_conn()
        return self.uds

    async def _ensure_conn(self):
        """懒连接，第一次命令调用才建立UDS连接"""
        if not self._connected:
            logger.info("DeviceBaseFeature: 正在建立UDS连接 ...")
            await self.uds.connect()
            self._connected = True
            logger.info("✅ DeviceBaseFeature UDS连接完成")

    # ------------------------------
    # Observable Properties 轮询上报，和Balance.GrossWeightGram风格统一
    # ------------------------------
    @sila.ObservableProperty()
    async def DeviceState(self) -> int:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetDeviceState", params={})
                yield int(resp["result"]["status"])
            except Exception as e:
                logger.warning(f"读取DeviceState异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def FaultReason(self) -> str:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetFaultReason", params={})
                yield str(resp["result"]["fault_reason"])
            except Exception as e:
                logger.warning(f"读取FaultReason异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def XPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetXPos", params={})
                yield float(resp["result"]["logic"])
            except Exception as e:
                logger.warning(f"读取XPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def XMotorPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetXPos", params={})
                yield float(resp["result"]["motor"])
            except Exception as e:
                logger.warning(f"读取XMotorPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def YPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetYPos", params={})
                yield float(resp["result"]["logic"])
            except Exception as e:
                logger.warning(f"读取YPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def YMotorPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetYPos", params={})
                yield float(resp["result"]["motor"])
            except Exception as e:
                logger.warning(f"读取YMotorPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def PowderZPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetPowderZPos", params={})
                yield float(resp["result"]["logic"])
            except Exception as e:
                logger.warning(f"读取PowderZPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def PowderZMotorPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetPowderZPos", params={})
                yield float(resp["result"]["motor"])
            except Exception as e:
                logger.warning(f"读取PowderZMotorPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def GripperZPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetGripperZPos", params={})
                yield float(resp["result"]["logic"])
            except Exception as e:
                logger.warning(f"读取GripperZPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def GripperZMotorPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetGripperZPos", params={})
                yield float(resp["result"]["motor"])
            except Exception as e:
                logger.warning(f"读取GripperZMotorPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def LiquidZPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetLiquidZPos", params={})
                yield float(resp["result"]["logic"])
            except Exception as e:
                logger.warning(f"读取LiquidZPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def LiquidZMotorPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetLiquidZPos", params={})
                yield float(resp["result"]["motor"])
            except Exception as e:
                logger.warning(f"读取LiquidZMotorPosition异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def GripperForce(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetGripperState", params={})
                yield float(resp["result"]["force"])
            except Exception as e:
                logger.warning(f"读取GripperForce异常 {e}")
            await asyncio.sleep(0.2)

    @sila.ObservableProperty()
    async def GripperPosition(self) -> float:
        while True:
            try:
                uds = await self._get_uds()
                resp = await uds.send_request(cmd="DeviceBase.GetGripperState", params={})
                yield float(resp["result"]["position"])
            except Exception as e:
                logger.warning(f"读取GripperPosition异常 {e}")
            await asyncio.sleep(0.2)

    # ------------------------------
    # Commands
    # ------------------------------
    @sila.ObservableCommand(
        name="Initialize",
        errors=[DeviceCommandError]
    )
    async def Initialize(
        self,
        *,
        status: sila.Status,
        intermediate: sila.Intermediate[str]
    ) -> None:
        """执行设备上电初始化，包括各轴回零、传感器自检

        Errors:
            DeviceCommandError: 设备底层初始化命令执行失败
        """
        try:
            status.update(progress=0.1)
            intermediate.send("开始执行设备初始化")

            uds = await self._get_uds()
            resp = await uds.send_request(cmd="DeviceBase.Initialize", params={})
            ret_code = resp.get("code", -1)

            status.update(progress=0.7)

            if ret_code != 0:
                err_msg = resp.get("msg", "initialize command failed")
                raise DeviceCommandError(f"Initialize fail, code={ret_code}, msg={err_msg}")

            status.update(progress=1.0)
            intermediate.send("初始化完成")

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            # 抛出SiLA标准业务异常，由CDK框架向外输出错误
            raise e
        except Exception as e:
            logger.exception("Initialize exception")
            raise DeviceCommandError(f"通信异常:{str(e)}") from e


    @sila.UnobservableCommand(name="EmergencyStop")
    async def EmergencyStop(self) -> CommandResult:
        """立即停止所有运动，进入安全状态"""
        try:
            uds = await self._get_uds()
            resp = await uds.send_request(cmd="DeviceBase.EmergencyStop", params={})
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "emergency stop command failed")
                raise DeviceCommandError(f"EmergencyStop fail, code={ret_code}, msg={err_msg}")

            return CommandResult.from_dict(True, "急停执行成功", {})
        except DeviceCommandError as e:
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("EmergencyStop exception")
            return CommandResult.from_dict(False, f"通信异常:{str(e)}", {})


    @sila.UnobservableCommand(name="SetGeneralParameters")
    async def SetGeneralParameters(
        self,
        x_speed: float,
        y_speed: float,
        powder_z_speed: float,
        gripper_z_speed: float,
        liquid_z_speed: float,
        gripper_speed: float,
    ) -> CommandResult:
        """设置各轴运动速度等通用参数。

        .. parameter:: x_speed: X 轴速度
        .. parameter:: y_speed: Y 轴速度
        .. parameter:: powder_z_speed: 粉末 Z 轴速度
        .. parameter:: gripper_z_speed: 夹爪 Z 轴速度
        .. parameter:: liquid_z_speed: 液体 Z 轴速度
        .. parameter:: gripper_speed: 夹爪速度
        """
        try:
            uds = await self._get_uds()
            params = {
                "x_speed": x_speed,
                "y_speed": y_speed,
                "powder_z_speed": powder_z_speed,
                "gripper_z_speed": gripper_z_speed,
                "liquid_z_speed": liquid_z_speed,
                "gripper_speed": gripper_speed,
            }
            resp = await uds.send_request(cmd="DeviceBase.SetGeneralParameters", params=params)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "SetGeneralParameters failed")
                raise DeviceCommandError(f"SetGeneralParameters fail, code={ret_code}, msg={err_msg}")

            out_data = {k: str(v) for k, v in params.items()}
            return CommandResult.from_dict(True, "通用参数设置成功", out_data)
        except DeviceCommandError as e:
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("SetGeneralParameters exception")
            return CommandResult.from_dict(False, f"通信异常:{str(e)}", {})


    @sila.ObservableCommand(name="CoordinateCalibration")
    async def CoordinateCalibration(
        self,
        powder_z_calibration: list[CalibrationPair],
        gripper_z_calibration: list[CalibrationPair],
        liquid_z_calibration: list[CalibrationPair],
        *,
        status: sila.Status,
        intermediate: sila.Intermediate[str]
    ) -> CommandResult:
        """对3个Z轴分别进行坐标系‑电机坐标映射标定，每轴取3对映射点"""
        try:
            status.update(progress=0.1)
            intermediate.send("开始坐标标定")

            uds = await self._get_uds()

            # SiLA struct转成可以发给UDS下位机的原生dict
            def _cal_pair_to_dict(p: CalibrationPair):
                return {
                    "logical_pos": {"x": p.logical_pos.x, "y": p.logical_pos.y, "z": p.logical_pos.z},
                    "motor_pos": {"mx": p.motor_pos.mx, "my": p.motor_pos.my, "mz": p.motor_pos.mz},
                }

            req_params = {
                "powder_z_calibration": [_cal_pair_to_dict(it) for it in powder_z_calibration],
                "gripper_z_calibration": [_cal_pair_to_dict(it) for it in gripper_z_calibration],
                "liquid_z_calibration": [_cal_pair_to_dict(it) for it in liquid_z_calibration],
            }

            status.update(progress=0.4)
            intermediate.send("下发标定参数至下位机")

            resp = await uds.send_request(cmd="DeviceBase.CoordinateCalibration", params=req_params)

            status.update(progress=0.8)
            ret_code = resp.get("code", -1)
            if ret_code != 0:
                err_msg = resp.get("msg", "CoordinateCalibration failed")
                raise DeviceCommandError(f"CoordinateCalibration fail, code={ret_code}, msg={err_msg}")

            res_data = resp.get("result", {})
            status.update(progress=1.0)
            intermediate.send("坐标标定完成")

            return CommandResult.from_dict(
                success=True,
                message="坐标标定完成",
                data={
                    "powder_z_residual": str(res_data.get("powder_z_residual", "")),
                    "gripper_z_residual": str(res_data.get("gripper_z_residual", "")),
                    "liquid_z_residual": str(res_data.get("liquid_z_residual", "")),
                    "calibration_timestamp": str(res_data.get("calibration_timestamp", ""))
                }
            )

        except asyncio.CancelledError:
            raise
        except DeviceCommandError as e:
            status.update(progress=1.0)
            intermediate.send(f"标定失败:{str(e)}")
            return CommandResult.from_dict(False, str(e), {})
        except Exception as e:
            logger.exception("CoordinateCalibration exception")
            status.update(progress=1.0)
            err_msg = f"通信异常:{str(e)}"
            intermediate.send(err_msg)
            return CommandResult.from_dict(False, err_msg, {})

