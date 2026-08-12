from unitelabs.cdk import sila
from unitelabs.usila_c.socket_client import UdsClient

class BalanceFeature(sila.Feature):
    def __init__(self, uds: UdsClient):
        super().__init__(
            identifier="Balance",
            version="1.0",
            name="Balance"
        )
        self.uds = uds

    # 删除 on_startup 里面的 connect！connect提升到create_app中
    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass

    @sila.UnobservableCommand()
    async def Tare(self) -> None:
        resp = await self.uds.send_request(cmd="Balance.Tare", params={})
        if resp["status"] != "ok":
            raise sila.CommandExecutionError(f"Balance tare fail:{resp}")

    # 新版：ObservableProperty 可订阅属性；不需要订阅就换成 @sila.UnobservableProperty()
    @sila.ObservableProperty()
    async def GrossWeightGram(self) -> float:
        resp = await self.uds.send_request(cmd="Balance.GetGrossWeight", params={})
        return float(resp["result"]["weight_g"])
