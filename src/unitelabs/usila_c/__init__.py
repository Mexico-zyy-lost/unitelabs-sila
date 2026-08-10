import collections.abc
import dataclasses
from importlib.metadata import version

from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig

from unitelabs.usila_c.feature.arm.arm_feature import ArmControlFeature

# 导入自己的硬件客户端与SiLA Feature
from unitelabs.usila_c.io.protocol import ArmHardwareClient

__version__ = version("unitelabs-pro-c")


@dataclasses.dataclass
class ProCConfig(ConnectorBaseConfig):
    """Configuration for the dev-c."""

    sila_server: SiLAServerConfig = dataclasses.field(
        default_factory=lambda: SiLAServerConfig(
            name="dev-c",
            type="Example",
            description=(
                """
                gy-dev
                """
            ),
            version=str(__version__),
            vendor_url="https://unitelabs.io/",
        )
    )


async def create_app(config: ProCConfig) -> collections.abc.AsyncGenerator[Connector, None]:
    """Create the connector application."""

    app = Connector(config)

    # 初始化连接本机C++硬件gRPC服务(127.0.0.1:50061)
    hw_client = ArmHardwareClient(grpc_addr="127.0.0.1:50061")
    await hw_client.connect()

    # 注册机械臂Feature
    app.add_feature(ArmControlFeature(hw_client=hw_client))

    yield app

    # 服务关闭时，释放gRPC客户端资源
    await hw_client.disconnect()
