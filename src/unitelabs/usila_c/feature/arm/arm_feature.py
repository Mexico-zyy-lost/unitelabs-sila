from unitelabs import sila
from unitelabs.usila_c.io.protocol import ArmHardwareClient


class ArmControlFeature(sila.Feature):
    feature_identifier = "com.robot.arm.control"
    feature_version = "1.0"
    feature_display_name = "ArmControl"

    def __init__(self, hw_client: ArmHardwareClient):
        super().__init__()
        self._hw = hw_client

    @sila.command(display_name="MoveToJointPositions")
    async def move_to_joint_positions(self, target_positions: list[float]) -> None:
        """移动机械臂到目标关节角度列表（6个值）"""
        if len(target_positions) != 6:
            raise sila.NotOkException(
                "INVALID_PARAMETERS",
                "target_positions must contain exactly 6 joint values"
            )
        try:
            ok = await self._hw.move_joints(target_positions)
        except grpc.aio.AioRpcError as e:
            raise sila.NotOkException(
                "DEVICE_ERROR",
                f"hardware service unreachable: {e.details()}"
            ) from e

        if not ok:
            raise sila.NotOkException("DEVICE_BUSY", "hardware report busy")

    @sila.ObservableProperty(display_name="JointPositions")
    async def joint_positions(self) -> list[float]:
        """可订阅：当前关节角度"""
        try:
            pos, _ = await self._hw.get_state()
            return pos
        except grpc.aio.AioRpcError as e:
            raise sila.NotOkException("DEVICE_ERROR", f"hardware error:{e.details()}") from e

    @sila.ObservableProperty(display_name="IsMoving")
    async def is_moving(self) -> bool:
        """可订阅：机械臂是否正在运动"""
        try:
            _, moving = await self._hw.get_state()
            return moving
        except grpc.aio.AioRpcError as e:
            raise sila.NotOkException("DEVICE_ERROR", f"hardware error:{e.details()}") from e
