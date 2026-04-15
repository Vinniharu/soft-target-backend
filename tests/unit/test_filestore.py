"""Filestore path resolution and escape prevention."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.storage.filestore import FileStore, PathEscapeError


async def test_write_and_read_bytes(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    relpath = store.report_relpath(uuid.uuid4(), 1)
    await store.write_bytes(relpath, b"pdf-bytes")
    assert await store.exists(relpath)
    chunks: list[bytes] = []
    async for chunk in store.stream(relpath):
        chunks.append(chunk)
    assert b"".join(chunks) == b"pdf-bytes"


async def test_rejects_path_escape(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    with pytest.raises(PathEscapeError):
        store.absolute("../../../etc/passwd")


async def test_report_relpath_shape() -> None:
    rid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert (
        FileStore.report_relpath(rid, 7)
        == "reports/12345678-1234-5678-1234-567812345678.v7.pdf"
    )
