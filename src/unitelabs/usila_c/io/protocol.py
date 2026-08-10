import logging
import grpc
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class ArmHardwareClient:
    """Python侧gRPC客户端，连接本机C++硬件gRPC服务 127.0.0.1:50061"""
    def __init__(self, grpc_addr:str="127.0.0.1:50061"):
        self._addr = grpc_addr
        self._channel: grpc.aio.Channel | None = None
        # 这里后续导入你C++生成的pb2_grpc存根
        # self._stub: ArmHardwareStub | None = None

    async def connect(self):
        """建立到C++硬件服务的gRPC连接"""
        logger.info(f"Connecting to C++ hardware service {self._addr}")
        self._channel = grpc.aio.insecure_channel(self._addr)
        # self._stub = ArmHardwareStub(self._channel)

    async def disconnect(self):
        """断开连接"""
        if self._channel:
            await self._channel.close()
            self._channel = None
        logger.info("Disconnected from C++ hardware service")
