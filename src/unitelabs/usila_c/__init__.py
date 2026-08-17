import traceback
import collections.abc
import dataclasses
from importlib.metadata import version

from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig
from unitelabs.usila_c.socket_client import UdsClient

from unitelabs.usila_c.feature.balance import BalanceFeature
from unitelabs.usila_c.feature.deviceBase import DeviceBaseFeature

__version__ = version("unitelabs-pro-c")
# 模块全局变量，供BalanceFeature获取UDS客户端
SHARED_UDS: UdsClient | None = None

@dataclasses.dataclass
class ProCConfig(ConnectorBaseConfig):
    sila_server: SiLAServerConfig = dataclasses.field(
        default_factory=lambda: SiLAServerConfig(
            name="dev-c",
            type="Example",
            description="gy‑dev",
            version=str(__version__),
            vendor_url="https://unitelabs.io/",
        )
    )
    # 增加这一行，接收yaml的features字符串列表，供框架loader使用
    features: list[str] = dataclasses.field(default_factory=list)


async def create_app(config: ProCConfig) -> collections.abc.AsyncGenerator[Connector, None]:
    print(f"DEBUG loaded features config: {config.features}")

    global SHARED_UDS
    socket_path = "/tmp/rk_uds.sock"

    # 创建UDS对象，connect不在这里执行（放到feature内部懒连接）
    SHARED_UDS = UdsClient(sock_path=socket_path)

    app = Connector(config)

    # =========手动实例化Feature，把UDS客户端注入进去=========
    try:
        balance_feat = BalanceFeature(uds=SHARED_UDS)
        app.register(balance_feat)

        deviceBase_feat = DeviceBaseFeature(uds=SHARED_UDS);
        app.register(deviceBase_feat);
    except ValueError as e:
        traceback.print_exc()
        raise
   
    print("✅ Manually registered BalanceFeature && DeviceBase with UDS client injected")

    yield app

    # shutdown阶段关闭UDS连接
    if SHARED_UDS is not None:
        await SHARED_UDS.close()