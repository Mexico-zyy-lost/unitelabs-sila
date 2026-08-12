import collections.abc
import dataclasses
from importlib.metadata import version

# from unitelabs.cdk.config import ProCConfig

from unitelabs.cdk import Connector, ConnectorBaseConfig, SiLAServerConfig
# 新增导入
from unitelabs.usila_c.socket_client import UdsClient
from unitelabs.usila_c.feature.Balance import BalanceFeature

__version__ = version("unitelabs-pro-c")


@dataclasses.dataclass
class ProCConfig(ConnectorBaseConfig):
    """Configuration for the dev‑c."""

    sila_server: SiLAServerConfig = dataclasses.field(
        default_factory=lambda: SiLAServerConfig(
            name="dev‑c",
            type="Example",
            description="""gy‑dev""",
            version=str(__version__),
            vendor_url="https://unitelabs.io/",
        )
    )

    # 关键：features 列表，填入工厂函数，老CDK会异步调用这个工厂
    features: list = dataclasses.field(default_factory=list)


async def create_app(config: ProCConfig) -> collections.abc.AsyncGenerator[Connector, None]:
    """Create the connector application."""

    socket_path = "/tmp/rk_uds.sock"
    shared_uds = UdsClient(sock_path=socket_path)

    # 定义Feature工厂，CDK会异步执行这个函数
    async def balance_feature_factory(connector: Connector):
        try:
            await shared_uds.connect()
            feat = BalanceFeature(uds=shared_uds)
            print(f"✅balance feature工厂执行成功，feature id={feat.identifier}")
            return feat
        except Exception as e:
            import traceback
            print("❌balance_feature_factory 执行异常！")
            print(traceback.format_exc())
            # 抛出异常，如果工厂报错，让connector直接崩溃，不要静默跳过
            raise

    # 将工厂填入config.features，框架自动调用并注册feature
    config.features = [balance_feature_factory]

    app = Connector(config)

    setattr(app, "_shared_uds", shared_uds)

    yield app

    # shutdown清理
    uds: UdsClient = getattr(app, "_shared_uds", None)
    if uds is not None:
        await uds.close()
