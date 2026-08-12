import asyncio
from unitelabs.sila import Client, ClientConfig

async def main():
    cfg = ClientConfig(hostname="10.10.112.204", port=50051, tls=False)
    cli = Client(cfg)
    await cli.open()

    balance = await cli.get_feature("com.unitelabs.usila_c/Balance/v1.0")
    await balance.Tare()
    w = await balance.GrossWeightGram.get()
    print(w)

    await cli.close()

asyncio.run(main())
