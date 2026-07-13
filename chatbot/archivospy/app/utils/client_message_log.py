"""Non-blocking conversational log of client ↔ chatbot exchanges.

Writes to client_messages_log/client_messages_log.txt (all users) and
client_messages_log/client_messages_log_<usuario>.txt per wa_id.
"""

from __future__ import annotations

import atexit
import logging
import queue
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

logger = logging.getLogger(__name__)

from app.config import REPO_ROOT

LOG_DIR = REPO_ROOT / "client_messages_log"
GLOBAL_LOG_PATH = LOG_DIR / "client_messages_log.txt"

_QueueItem = Union["_LogRecord", object]
_QUEUE: queue.Queue[_QueueItem] = queue.Queue(maxsize=8000)
_SHUTDOWN = object()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()

_BATCH_RECORDS = 32
_FLUSH_INTERVAL_SEC = 0.4

Reply = Union[str, List[str]]


@dataclass(frozen=True)
class _LogRecord:
    paths: tuple[Path, ...]
    payload: bytes


def _safe_user_key(wa_id: str) -> str:
    key = re.sub(r"[^\w]+", "_", (wa_id or "").strip()).strip("_")
    return (key[:96] or "unknown")


def _user_log_path(wa_id: str) -> Path:
    return LOG_DIR / f"client_messages_log_{_safe_user_key(wa_id)}.txt"


_BLOCK_OPEN = "################################################################\n"
_BLOCK_CLOSE = "#################################################################\n"
_ROLE_SEPARATOR = "-------------------------------\n"


def _format_role_block(role: str, message: str) -> str:
    lines = message.split("\n")
    if len(lines) == 1:
        return f"{role}: {lines[0]}\n"
    return f"{role}: {lines[0]}\n" + "\n".join(lines[1:]) + "\n"


def _format_exchange(client_message: str, bot_message: str) -> str:
    client_line = (client_message or "").strip() or "(vacío)"
    bot_line = (bot_message or "").strip() or "(sin respuesta)"
    return (
        f"{_BLOCK_OPEN}"
        f"\n"
        f"{_format_role_block('Cliente', client_line)}"
        f"\n"
        f"\n"
        f"{_ROLE_SEPARATOR}"
        f"\n"
        f"{_format_role_block('Chatbot', bot_line)}"
        f"\n"
        f"{_BLOCK_CLOSE}"
    )


def _format_bot_reply(reply: Reply) -> str:
    if isinstance(reply, list):
        parts = [str(part).strip() for part in reply if str(part).strip()]
        return "\n".join(parts)
    return str(reply or "").strip()


def _flush_batch(records: list[_LogRecord]) -> None:
    if not records:
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception("Failed creating log directory %s", LOG_DIR)
        return

    by_path: dict[Path, list[bytes]] = defaultdict(list)
    for record in records:
        for path in record.paths:
            by_path[path].append(record.payload)

    for path, chunks in by_path.items():
        try:
            with open(path, "ab") as handle:
                handle.writelines(chunks)
        except OSError:
            logger.exception("Failed writing %s", path)


def _worker_main() -> None:
    batch: list[_LogRecord] = []
    while True:
        try:
            item = _QUEUE.get(timeout=_FLUSH_INTERVAL_SEC)
        except queue.Empty:
            if batch:
                _flush_batch(batch)
                batch = []
            continue
        if item is _SHUTDOWN:
            if batch:
                _flush_batch(batch)
            break
        if isinstance(item, _LogRecord):
            batch.append(item)
            if len(batch) >= _BATCH_RECORDS:
                _flush_batch(batch)
                batch = []


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
        thread = threading.Thread(
            target=_worker_main,
            name="client-message-log",
            daemon=True,
        )
        thread.start()
        _worker = thread


def _shutdown_worker() -> None:
    try:
        _QUEUE.put_nowait(_SHUTDOWN)
    except queue.Full:
        pass


atexit.register(_shutdown_worker)


def schedule_client_message_log(
    *,
    wa_id: str,
    client_message: str,
    bot_message: Reply = "",
) -> None:
    """Enqueue one exchange (client + bot); returns immediately."""
    text = _format_exchange(client_message, _format_bot_reply(bot_message))
    paths = (GLOBAL_LOG_PATH, _user_log_path(wa_id))
    try:
        payload = text.encode("utf-8")
    except UnicodeEncodeError:
        return
    record = _LogRecord(paths=paths, payload=payload)
    _ensure_worker()
    try:
        _QUEUE.put_nowait(record)
    except queue.Full:
        logger.warning("client_messages_log queue full; dropping event wa_id=%s", wa_id)
