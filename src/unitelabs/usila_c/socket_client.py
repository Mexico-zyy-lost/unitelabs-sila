import asyncio
import json
from typing import Dict, Any


class UdsClient:
    """Unix Domain Socket 异步客户端，对接C++网关"""
    def __init__(self, sock_path: str):
        self.sock_path = sock_path
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self.timeout = 10.0

    async def connect(self):
        """连接C++ UDS服务端，在create_app中调用"""
        self.reader, self.writer = await asyncio.open_unix_connection(self.sock_path)

    async def send_request(self, cmd: str, params: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            import uuid
            req_id = str(uuid.uuid4())
            payload = json.dumps({"cmd": cmd, "params": params, "req_id": req_id}) + "\n"

            # 调试打印UDS发出报文
            print(f"[UDS SEND] {payload.strip()}")

            self.writer.write(payload.encode("utf‑8"))
            await self.writer.drain()

            async def read_one_line():
                return await self.reader.readline()

            line = await asyncio.wait_for(read_one_line(), timeout=self.timeout)
            raw_line = line.decode("utf‑8").strip()
            print(f"[UDS RECV] {raw_line}")

            resp = json.loads(raw_line)
            if resp["req_id"] != req_id:
                raise RuntimeError(f"UDS req_id mismatch, expect {req_id}, got {resp['req_id']}")
            return resp

    async def close(self):
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            self.reader = None
            self.writer = None
