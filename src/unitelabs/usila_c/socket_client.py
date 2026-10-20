import asyncio
import errno
import json
import uuid as uuid_module
from typing import Any


class UdsClient:
    """
    Unix Domain Socket 异步客户端，对接 C++ 网关。

    设计原则：
    - 只保持一条长连接。网关不接受第二个客户端，再 connect 会把前一条连接拆掉，
      表现为 Transport endpoint is not connected
    - 多个命令可以同时在途：写完即释放写锁，各自按 uuid 等最终 answer
    - ack 以 msg == "accepted" 表示已接收，不作为最终业务结论
    - answer 以 msg == "done" 表示执行完成，才作为最终状态
    - 其它回复直接透传，不额外包装
    - 超时时间通过每个 command 的结构体字段 mws 下发给下位机
    - 等待超时时返回 code == -1 的业务错误回复
    """

    def __init__(self, sock_path: str, timeout: float = 10.0):
        self.sock_path = sock_path
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self._conn_lock = asyncio.Lock()
        self.timeout = timeout

        self._pending: dict[str, asyncio.Future] = {}
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._reader_task: asyncio.Task | None = None
        self._closed = False
        self._stopping = False

    def _transport_alive(self) -> bool:
        writer = self.writer
        task = self._reader_task
        return (
            not self._closed
            and self.reader is not None
            and writer is not None
            and not writer.is_closing()
            and task is not None
            and not task.done()
        )

    async def connect(self):
        """连接并启动后台 reader loop。已经连上则直接返回。"""
        await self._ensure_conn()

    async def _ensure_conn(self):
        async with self._conn_lock:
            if self._closed:
                raise ConnectionError("UDS client is closed")
            if self._transport_alive():
                return
            await self._close_transport()
            self.reader, self.writer = await asyncio.open_unix_connection(self.sock_path)
            self._reader_task = asyncio.create_task(self._read_loop())

    def _fail_pending(self, exc: BaseException):
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()

    async def _close_transport(self):
        """关掉当前 socket。调用方需已持有 _conn_lock，或处于进程退出。"""
        self._stopping = True
        # 读循环会被这次关闭打断。先失败在途请求，避免一直等到超时。
        self._fail_pending(ConnectionError("UDS connection reset"))
        writer = self.writer
        task = self._reader_task
        self.reader = None
        self.writer = None
        self._reader_task = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._stopping = False

    async def _read_loop(self):
        try:
            while not self._closed and not self._stopping:
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._stopping or self._closed:
                return
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

    @staticmethod
    def _is_disconnect(exc: BaseException) -> bool:
        if isinstance(exc, (ConnectionError, BrokenPipeError, ConnectionResetError)):
            return True
        if isinstance(exc, OSError) and exc.errno in (errno.ENOTCONN, errno.EPIPE, errno.ECONNRESET, errno.EBADF):
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
        - 写锁只包住本次写出。等待 answer 期间其它命令仍可下发
        - ack 不被当作最终业务状态
        - 下位机要求把超时时间单独放在结构体字段 mws，不塞进 params
        - 写出时若发现连接已断，丢弃这条 socket 并重连重发一次
        """
        if params is None:
            params = {}
        if uuid is None:
            uuid = str(uuid_module.uuid4())
        if timeout is None:
            timeout = self.timeout

        payload = json.dumps({"cmd": cmd, "params": dict(params), "uuid": uuid, "mws": timeout}) + "\n"
        sent = False
        for attempt in (1, 2):
            await self._ensure_conn()
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            self._pending[uuid] = fut
            try:
                try:
                    async with self._write_lock:
                        print("[UDS SEND]", payload.strip())
                        writer = self.writer
                        if writer is None:
                            raise ConnectionError("UDS connection is not open")
                        writer.write(payload.encode("utf-8"))
                        await writer.drain()
                    sent = True
                except Exception as exc:
                    if sent or attempt == 2 or not self._is_disconnect(exc):
                        raise
                    async with self._conn_lock:
                        await self._close_transport()
                    continue

                try:
                    msg = await asyncio.wait_for(fut, timeout=timeout)
                except asyncio.TimeoutError:
                    return {
                        "uuid": uuid,
                        "code": -1,
                        "msg": "timeout",
                        "error": f"UDS request timed out after {timeout} seconds",
                    }
                if msg.get("uuid") is not None and msg.get("uuid") != uuid:
                    raise RuntimeError(f"UDS uuid mismatch, expect {uuid}, got {msg.get('uuid')}")
                return msg
            finally:
                self._pending.pop(uuid, None)
                if not fut.done():
                    fut.cancel()
                elif not fut.cancelled():
                    # 连接被拆掉时异常已经投递到 future。取走它，避免 "exception was never retrieved"。
                    fut.exception()

        raise ConnectionError("UDS connection is not open")

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
        pending = list(self._pending.values())
        self._pending.clear()
        for fut in pending:
            if not fut.done():
                fut.set_exception(ConnectionError("UDS client is closed"))
        async with self._conn_lock:
            await self._close_transport()
