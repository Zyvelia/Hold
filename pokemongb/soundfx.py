"""Small sound adjustments in front of the volume slider."""

from __future__ import annotations

import array
import struct


def scale_pcm(data: bytes, gain: float) -> bytes:
    if not data or gain == 1:
        return data
    count = len(data) // 2
    samples = array.array("h")
    samples.frombytes(data[: count * 2])
    scaled = array.array(
        "h",
        (max(-32768, min(32767, int(sample * gain))) for sample in samples),
    )
    return scaled.tobytes()


def tone_pcm(data: bytes, mode: str, state: list[float]) -> bytes:
    """A one-pole low or high pass. `state` keeps the last left and right sample."""
    if mode not in ("low", "high") or len(data) < 4:
        return data
    samples = array.array("h")
    samples.frombytes(data[: len(data) // 4 * 4])
    low_l, low_r = state
    mix = 0.15
    out = array.array("h", samples)
    for index in range(0, len(samples), 2):
        left = samples[index]
        right = samples[index + 1]
        low_l += mix * (left - low_l)
        low_r += mix * (right - low_r)
        if mode == "low":
            out[index] = int(low_l)
            out[index + 1] = int(low_r)
        else:
            out[index] = max(-32768, min(32767, int(left - low_l)))
            out[index + 1] = max(-32768, min(32767, int(right - low_r)))
    state[0] = low_l
    state[1] = low_r
    return out.tobytes()


class AudioDelay:
    """Hold or drop samples so the picture or the sound can lead."""

    def __init__(self) -> None:
        self.queue = bytearray()
        self.ms = 0

    def push(self, data: bytes, rate: int = 44100) -> bytes:
        if not data or self.ms == 0:
            return data
        frame = 4
        if self.ms < 0:
            drop = int(rate * frame * -self.ms / 1000)
            drop -= drop % frame
            return data[min(len(data), drop):]
        self.queue.extend(data)
        hold = int(rate * frame * self.ms / 1000)
        hold -= hold % frame
        if len(self.queue) <= hold:
            return b""
        take = len(self.queue) - hold
        take -= take % frame
        out = bytes(self.queue[:take])
        del self.queue[:take]
        return out


def wav_header(data_bytes: int, rate: int = 44100) -> bytes:
    payload = max(0, data_bytes)
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + payload,
        b"WAVE",
        b"fmt ",
        16,
        1,
        2,
        rate,
        rate * 4,
        4,
        16,
        b"data",
        payload,
    )


def peak_level(data: bytes) -> int:
    if len(data) < 2:
        return 0
    samples = array.array("h")
    samples.frombytes(data[: len(data) // 2 * 2])
    loudest = 0
    for sample in samples:
        loud = sample if sample >= 0 else -sample
        if loud > loudest:
            loudest = loud
    return loudest
