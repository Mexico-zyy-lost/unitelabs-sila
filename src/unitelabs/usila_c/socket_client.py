import asyncio
import json
from typing import Any


class UdsClient:
    """
    Unix Domain Socket 异步客户端，对接C++网关。

    设计原则：
    - 仅维护一条长连接
    - 下发命令后，等待最终 answer，不再假设必须立刻返回一条单行结果
    - ack 以 msg == "accepted" 表示已接收，不作为最终业务结论
    - answer 以 msg == "done" 表示执行完成，才作为最终状态
    - 其它回复直接透传，不额外包装
    - 超时时间通过每个 command 的结构体字段 mws 下发给下位机
    """

    def __init__(self, sock_path: str, timeout: float = 10.0):
        self.sock_path = sock_path
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self.timeout = timeout

        self._pending: dict[str, asyncio.Future] = {}
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._reader_task: asyncio.Task | None = None
        self._closed = False

    async def connect(self):
        """连接并启动后台 reader loop"""
        if self.reader is not None and self.writer is not None:
            return
        self.reader, self.writer = await asyncio.open_unix_connection(self.sock_path)
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        try:
            while not self._closed:
                line = await self.reader.readline()
                if not line:
                    raise ConnectionError("UDS connection closed by peer")
                raw = line.decode("utf-8").strip()
                print("[UDS RECV]", raw)
                try:
                    msg = json.loads(raw)
                except Exception as exc:
                    print("Invalid JSON from UDS:", exc, raw)
                    continue

                uuid = msg.get("uuid")
                if uuid and uuid in self._pending:
                    fut = self._pending.get(uuid)
                    if fut is not None and not fut.done() and self._is_answer_message(msg):
                        fut.set_result(msg)

                if uuid and uuid in self._subs:
                    for q in list(self._subs.get(uuid, [])):
                        try:
                            q.put_nowait(msg)
                        except asyncio.QueueFull:
                            pass
        except Exception as exc:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(exc)
            self._pending.clear()
            for uuid, queues in list(self._subs.items()):
                for q in queues:
                    try:
                        q.put_nowait({"uuid": uuid, "type": "error", "error": str(exc)})
                    except Exception:
                        pass
            print("UDS read loop terminated:", exc)

    @staticmethod
    def _is_answer_message(msg: dict[str, Any]) -> bool:
        """
        按协议判定是否为最终 answer：

        - ack：{"uuid": ..., "code": 0, "msg": "accepted", "result": {}}
        - answer：{"uuid": ..., "code": 0, "msg": "done", "result": {...}}
        - 其它直接透传的回复，也按最终结果处理
        """
        msg_type = msg.get("type")
        if msg_type in ("answer", "result", "response"):
            return True

        msg_value = msg.get("msg")
        if msg_value == "accepted":
            return False
        if msg_value == "done":
            return True

        if msg.get("final") is True:
            return True

        if "code" in msg and msg_value not in ("accepted",):
            return True
        return False

    async def send_request(
        self,
        cmd: str,
        params: dict[str, Any] | None = None,
        *,
        uuid: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        发送请求并等待最终 answer。

        说明：
        - ack 不被当作最终业务状态；只要是 type != answer/result/response，都会被忽略为中间状态
        - 下位机要求把超时时间单独放在结构体字段 mws，不塞进 params
        """
        if params is None:
            params = {}
        if uuid is None:
            uuid = str(uuid.uuid4())
        if timeout is None:
            timeout = self.timeout

        payload = json.dumps({"cmd": cmd, "params": dict(params), "uuid": uuid, "mws": timeout}) + "\n"

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[uuid] = fut

        try:
            async with self._write_lock:
                print("[UDS SEND]", payload.strip())
                self.writer.write(payload.encode("utf-8"))
                await self.writer.drain()

            msg = await asyncio.wait_for(fut, timeout=timeout)
            if msg.get("uuid") is not None and msg.get("uuid") != uuid:
                raise RuntimeError(f"UDS uuid mismatch, expect {uuid}, got {msg.get('uuid')}")
            return msg
        finally:
            self._pending.pop(uuid, None)
            if not fut.done():
                fut.cancel()

    async def send_and_stream(
        self,
        cmd: str,
        params: dict[str, Any] | None = None,
        *,
        uuid: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """兼容旧接口：简化后只等待最终 answer，不再消费 progress。"""
        return await self.send_request(cmd, params, uuid=uuid, timeout=timeout)

    def subscribe_progress(self, uuid: str, queue_maxsize: int = 32) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._subs.setdefault(uuid, []).append(q)
        return q

    def unsubscribe_progress(self, uuid: str, q: asyncio.Queue):
        if uuid in self._subs:
            try:
                self._subs[uuid].remove(q)
            except ValueError:
                pass
            if not self._subs[uuid]:
                self._subs.pop(uuid, None)

    async def close(self):
        self._closed = True
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            self.reader = None
            self.writer = None
