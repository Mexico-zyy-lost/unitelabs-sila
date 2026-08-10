import logging

import grpc.aio

from .hardware_pb2 import Empty, JointTarget
from .hardware_pb2_grpc import ArmHardwareStub

logger = logging.getLogger(__name__)


class ArmHardwareClient:
    """连接本机C++硬件gRPC服务"""

    def __init__(self, grpc_addr: str = "127.0.0.1:50061"):
        self._addr = grpc_addr
        self._channel: grpc.aio.Channel | None = None
        self._stub: ArmHardwareStub | None = None

    async def connect(self):
        logger.info(f"ArmHardwareClient connect to {self._addr}")
        self._channel = grpc.aio.insecure_channel(self._addr)
        self._stub = ArmHardwareStub(self._channel)

    async def disconnect(self):
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
        logger.info("ArmHardwareClient disconnected")

    async def move_joints(self, positions: list[float]) -> bool:
        """请求C++层执行关节运动"""
        if self._stub is None:
            raise RuntimeError("hardware client not connected")
        req = JointTarget(positions=positions)
        resp = await self._stub.MoveJoints(req)
        return resp.success

    async def get_state(self) -> tuple[list[float], bool]:
        """读取机械臂状态：关节位置、是否运动中"""
        if self._stub is None:
            raise RuntimeError("hardware client not connected")
        resp = await self._stub.GetStatus(Empty())
        return list(resp.positions), resp.is_moving
