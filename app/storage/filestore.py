"""Local disk file storage for generated PDFs.

All paths are relative to ``STORAGE_DIR`` and the store refuses to
resolve any path that would escape it. PDFs are written under
``reports/<report-uuid>.v<version>.pdf`` and never overwritten — edits
always produce a new version.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles
import aiofiles.os


class FileStoreError(Exception):
    """Base class for filestore errors."""


class PathEscapeError(FileStoreError):
    """Raised when a relative path resolves outside STORAGE_DIR."""


class FileStore:
    def __init__(self, storage_dir: Path) -> None:
        self._root = storage_dir.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, relative_path: str) -> Path:
        target = (self._root / relative_path).resolve()
        try:
            target.relative_to(self._root)
        except ValueError as exc:
            raise PathEscapeError(
                "resolved path escapes storage root"
            ) from exc
        return target

    @staticmethod
    def report_relpath(report_id: uuid.UUID, version: int) -> str:
        return f"reports/{report_id}.v{version}.pdf"

    async def write_bytes(self, relative_path: str, data: bytes) -> Path:
        target = self._resolve(relative_path)
        await aiofiles.os.makedirs(target.parent, exist_ok=True)
        async with aiofiles.open(target, "wb") as fh:
            await fh.write(data)
        return target

    def absolute(self, relative_path: str) -> Path:
        return self._resolve(relative_path)

    async def exists(self, relative_path: str) -> bool:
        try:
            target = self._resolve(relative_path)
        except PathEscapeError:
            return False
        return await aiofiles.os.path.exists(target)

    async def stream(
        self,
        relative_path: str,
        *,
        chunk_size: int = 64 * 1024,
    ) -> AsyncIterator[bytes]:
        target = self._resolve(relative_path)
        async with aiofiles.open(target, "rb") as fh:
            while True:
                chunk = await fh.read(chunk_size)
                if not chunk:
                    break
                yield chunk
