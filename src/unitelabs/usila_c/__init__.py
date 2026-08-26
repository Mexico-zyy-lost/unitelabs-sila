import collections.abc
import dataclasses
import traceback
from importlib.metadata import version

from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig

from unitelabs.usila_c.feature.authentication_service import AuthenticationService
from unitelabs.usila_c.feature.baseCtrl import DeviceBaseFeature
from unitelabs.usila_c.feature.capHandle import CAPFeature
from unitelabs.usila_c.feature.clampHandle import CLAMPFeature
from unitelabs.usila_c.feature.debugCtrl import DebugFeature
from unitelabs.usila_c.feature.ffqHandle import FFQFeature
from unitelabs.usila_c.feature.lidHandle import LIDFeature
from unitelabs.usila_c.feature.wsHandle import WSFeature
from unitelabs.usila_c.feature.zdHandle import ZDFeature
from unitelabs.usila_c.socket_client import UdsClient

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
        app.register(AuthenticationService())

        balance_feat = WSFeature(uds=SHARED_UDS)
        app.register(balance_feat)

        deviceBase_feat = DeviceBaseFeature(uds=SHARED_UDS)
        app.register(deviceBase_feat)

        powderDosing_feat = FFQFeature(uds=SHARED_UDS)
        app.register(powderDosing_feat)

        liquidHandling_feat = LIDFeature(uds=SHARED_UDS)
        app.register(liquidHandling_feat)

        cap_feat = CAPFeature(uds=SHARED_UDS)
        app.register(cap_feat)

        transfer_feat = CLAMPFeature(uds=SHARED_UDS)
        app.register(transfer_feat)

        vortex_feat = ZDFeature(uds=SHARED_UDS)
        app.register(vortex_feat)

        debug_feat = DebugFeature(uds=SHARED_UDS)
        app.register(debug_feat)

    except ValueError:
        traceback.print_exc()
        raise

    print("✅ Manually registered BalanceFeature && DeviceBase with UDS client injected")

    yield app

    # shutdown阶段关闭UDS连接
    if SHARED_UDS is not None:
        await SHARED_UDS.close()
