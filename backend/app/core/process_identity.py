from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    worker_id: str
    hostname: str
    process_id: int
    instance_id: str


_INSTANCE_ID = uuid4().hex
_HOSTNAME = socket.gethostname()
_PROCESS_ID = os.getpid()
_WORKER_ID = f"{_HOSTNAME}:{_PROCESS_ID}:{_INSTANCE_ID}"


def get_process_identity() -> ProcessIdentity:
    return ProcessIdentity(
        worker_id=_WORKER_ID,
        hostname=_HOSTNAME,
        process_id=_PROCESS_ID,
        instance_id=_INSTANCE_ID,
    )
