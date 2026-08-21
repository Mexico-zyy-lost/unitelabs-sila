import asyncio
import json
import uuid
from typing import Dict, Any, List, Optional


class UdsClient:
    """Unix Domain Socket 异步客户端，对接C++网关

    特性：
      - 单一长连接（open_unix_connection）
      - 背景reader loop，所有收到的消息按 req_id 路由
      - pending futures（单次 answer）和订阅队列（progress/ack/answer）共存
      - send_and_stream 提供一键下发并把下位机的 progress/ack/answer 分发到 status/intermediate
    """

    def __init__(self, sock_path: str):
        self.sock_path = sock_path
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._write_lock = asyncio.Lock()
        self.timeout = 10.0

        # req_id -> Future (等待单次 answer)
        self._pending: Dict[str, asyncio.Future] = {}
        # req_id -> list[asyncio.Queue] (订阅者接收 progress/ack/answer)
        self._subs: Dict[str, List[asyncio.Queue]] = {}

        self._reader_task: Optional[asyncio.Task] = None
        self._closed = False

    async def connect(self):
        """连接并启动 reader loop"""
        self.reader, self.writer = await asyncio.open_unix_connection(self.sock_path)
        # start background reader task
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
                except Exception as e:
                    print("Invalid JSON from UDS:", e, raw)
                    continue

                req_id = msg.get("req_id")
                # fulfill pending future (first answer-like message)
                if req_id and req_id in self._pending:
                    fut = self._pending.get(req_id)
                    if fut and not fut.done():
                        # Heuristic: if message looks like final/answer, set_result
                        if self._is_final_message(msg):
                            fut.set_result(msg)
                        else:
                            # keep waiting for final; but still notify subscribers
                            pass

                # dispatch to subscribers
                if req_id and req_id in self._subs:
                    for q in list(self._subs.get(req_id, [])):
                        try:
                            q.put_nowait(msg)
                        except asyncio.QueueFull:
                            # drop if subscriber too slow
                            pass
        except Exception as e:
            # notify pending futures
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(e)
            self._pending.clear()
            # notify subscribers with error message
            for req_id, queues in list(self._subs.items()):
                for q in queues:
                    try:
                        q.put_nowait({"req_id": req_id, "type": "error", "error": str(e)})
                    except Exception:
                        pass
            print("UDS read loop terminated:", e)

    def _is_final_message(self, msg: Dict[str, Any]) -> bool:
        # Heuristics to decide whether a message is a final answer/result
        t = msg.get("type")
        if t in ("answer", "response", "result"):
            return True
        if msg.get("final") is True:
            return True
        if "code" in msg:
            # message with code is likely the response
            return True
        # also if payload/result contains 'completed' flags
        res = msg.get("result") or msg.get("payload")
        if isinstance(res, dict) and res.get("status") in ("finished", "done", "ok"):
            return True
        return False

    async def send_request(self, cmd: str, params: Dict[str, Any], req_id: Optional[str] = None) -> Dict[str, Any]:
        """发送单次请求并等待最终回复（兼容旧代码）。

        通过在 _pending 注册 future 并由 reader loop 在收到 final message 时 fulfill，避免直接从 reader 竞争读取。
        """
        if req_id is None:
            req_id = str(uuid.uuid4())

        # prepare pending future BEFORE sending to avoid race where reply arrives quickly
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut

        payload = json.dumps({"cmd": cmd, "params": params, "req_id": req_id}) + "\n"
        try:
            async with self._write_lock:
                print("[UDS SEND]", payload.strip())
                self.writer.write(payload.encode("utf-8"))
                await self.writer.drain()

            # wait for reader loop to set the future when final message arrives
            msg = await asyncio.wait_for(fut, timeout=self.timeout)
            return msg
        finally:
            # cleanup pending if still present
            self._pending.pop(req_id, None)
            if not fut.done():
                fut.cancel()

    async def send_and_stream(
        self,
        cmd: str,
        params: Dict[str, Any],
        status: Optional[Any] = None,
        intermediate: Optional[Any] = None,
        req_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """发送命令并把下位机对该 req_id 的 progress/ack/answer 流式分发给 status/intermediate。

        返回最终的 answer/result 消息（或抛出异常）。
        """
        if req_id is None:
            req_id = str(uuid.uuid4())
        if timeout is None:
            timeout = self.timeout

        # subscribe to receive progress/ack/answer
        q = self.subscribe_progress(req_id)

        # send request without blocking for immediate answer (reader loop will handle replies)
        async with self._write_lock:
            payload = json.dumps({"cmd": cmd, "params": params, "req_id": req_id, "type": "request"}) + "\n"
            print("[UDS SEND]", payload.strip())
            self.writer.write(payload.encode("utf-8"))
            await self.writer.drain()

        final_msg: Optional[Dict[str, Any]] = None
        try:
            # loop until final message received or timeout / cancellation
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Timed out waiting for progress/answer for req_id={req_id}")

                # deliver human-friendly progress updates if available
                # progress may be in msg['progress'] or msg['payload']/msg['result']
                percent = None
                payload = msg.get("payload") or msg.get("result") or {}
                if isinstance(payload, dict):
                    if "progress" in payload:
                        percent = payload.get("progress")
                    elif "percent" in payload:
                        percent = payload.get("percent")
                    elif "status_percent" in payload:
                        percent = payload.get("status_percent")

                # If top-level progress field exists
                if percent is None:
                    percent = msg.get("progress") or msg.get("percent")

                if percent is not None and status is not None:
                    # normalize to 0.0-1.0
                    try:
                        p = float(percent)
                        if p > 1.0:
                            p = p / 100.0
                        status.update(progress=max(0.0, min(1.0, p)))
                    except Exception:
                        pass

                # deliver messages to intermediate if text present
                text = None
                if isinstance(payload, dict):
                    text = payload.get("message") or payload.get("msg") or payload.get("status_message")
                text = text or msg.get("message") or msg.get("msg")
                if text and intermediate is not None:
                    try:
                        intermediate.send(str(text))
                    except Exception:
                        pass

                # check if final
                if self._is_final_message(msg):
                    final_msg = msg
                    break

            if final_msg is None:
                raise RuntimeError("send_and_stream exited without final message")

            return final_msg
        finally:
            # cleanup: unsubscribe queue
            try:
                self.unsubscribe_progress(req_id, q)
            except Exception:
                pass

    def subscribe_progress(self, req_id: str, queue_maxsize: int = 32) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._subs.setdefault(req_id, []).append(q)
        return q

    def unsubscribe_progress(self, req_id: str, q: asyncio.Queue):
        if req_id in self._subs:
            try:
                self._subs[req_id].remove(q)
            except ValueError:
                pass
            if not self._subs[req_id]:
                self._subs.pop(req_id, None)

    async def close(self):
        self._closed = True
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
        if self._reader_task is not None:
            # let it unwind
            await asyncio.sleep(0.01)
