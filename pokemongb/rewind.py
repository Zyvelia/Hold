"""A short ring of save states so a held key can step the game backward."""

from __future__ import annotations

from collections import deque


class Rewind:
    def __init__(self, max_bytes: int = 48 * 1024 * 1024, max_count: int = 300):
        self.max_bytes = max_bytes
        self.max_count = max_count
        self._frames: deque[bytes] = deque()
        self.bytes = 0
        self.stride = 1
        self._since = 0
        self.configured = False
        self.disabled = False

    def clear(self) -> None:
        self._frames.clear()
        self.bytes = 0
        self.stride = 1
        self._since = 0
        self.configured = False
        self.disabled = False

    def configure(self, sample: bytes) -> None:
        """Choose how often to keep a state from the size of one sample."""
        self.configured = True
        size = len(sample)
        if size <= 0 or size > self.max_bytes:
            self.disabled = True
            return
        if size > 2_000_000:
            self.stride = 8
        elif size > 400_000:
            self.stride = 3
        else:
            self.stride = 1

    def push(self, blob: bytes) -> None:
        if self.disabled or not blob:
            return
        self._since += 1
        if self._since < self.stride:
            return
        self._since = 0
        self._frames.append(blob)
        self.bytes += len(blob)
        while self._frames and (len(self._frames) > self.max_count or self.bytes > self.max_bytes):
            old = self._frames.popleft()
            self.bytes -= len(old)

    def pop(self) -> bytes | None:
        if not self._frames:
            return None
        blob = self._frames.pop()
        self.bytes -= len(blob)
        self._since = 0
        return blob
