"""Apply an IPS or BPS patch to ROM bytes. The file on disk is left alone."""

from __future__ import annotations

import zlib


def apply_patch(rom: bytes, patch: bytes) -> bytes:
    if patch.startswith(b"PATCH"):
        return apply_ips(rom, patch)
    if patch.startswith(b"BPS1"):
        return apply_bps(rom, patch)
    raise ValueError("That file is not an IPS or BPS patch.")


def apply_ips(rom: bytes, patch: bytes) -> bytes:
    if not patch.startswith(b"PATCH"):
        raise ValueError("That file is not an IPS patch.")
    out = bytearray(rom)
    pos = 5
    while pos + 3 <= len(patch):
        marker = patch[pos:pos + 3]
        pos += 3
        if marker == b"EOF":
            return bytes(out)
        offset = int.from_bytes(marker, "big")
        if pos + 2 > len(patch):
            raise ValueError("That IPS patch is cut off.")
        size = int.from_bytes(patch[pos:pos + 2], "big")
        pos += 2
        if size == 0:
            if pos + 3 > len(patch):
                raise ValueError("That IPS patch is cut off.")
            run = int.from_bytes(patch[pos:pos + 2], "big")
            value = patch[pos + 2]
            pos += 3
            _place(out, offset, bytes([value]) * run)
        else:
            if pos + size > len(patch):
                raise ValueError("That IPS patch is cut off.")
            _place(out, offset, patch[pos:pos + size])
            pos += size
    return bytes(out)


def _place(out: bytearray, offset: int, data: bytes) -> None:
    end = offset + len(data)
    if end > len(out):
        out.extend(b"\x00" * (end - len(out)))
    out[offset:end] = data


def _bps_number(patch: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 1
    while pos < len(patch):
        byte = patch[pos]
        pos += 1
        value += (byte & 0x7F) * shift
        if byte & 0x80:
            return value, pos
        shift <<= 7
        value += shift
    raise ValueError("That BPS patch is cut off.")


def _bps_signed(number: int) -> int:
    sign = -1 if number & 1 else 1
    return sign * (number >> 1)


def apply_bps(rom: bytes, patch: bytes) -> bytes:
    if not patch.startswith(b"BPS1") or len(patch) < 16:
        raise ValueError("That file is not a BPS patch.")
    stored = int.from_bytes(patch[-4:], "little")
    if (zlib.crc32(patch[:-4]) & 0xFFFFFFFF) != stored:
        raise ValueError("That BPS patch is damaged.")
    pos = 4
    source_size, pos = _bps_number(patch, pos)
    target_size, pos = _bps_number(patch, pos)
    meta_size, pos = _bps_number(patch, pos)
    if pos + meta_size > len(patch):
        raise ValueError("That BPS patch is cut off.")
    pos += meta_size
    if source_size != len(rom):
        raise ValueError("That patch is for a different ROM.")
    output = bytearray()
    source_at = 0
    target_at = 0
    while len(output) < target_size:
        data, pos = _bps_number(patch, pos)
        command = data & 3
        length = (data >> 2) + 1
        if command == 0:
            start = len(output)
            chunk = rom[start:start + length]
            if len(chunk) != length:
                raise ValueError("That patch is for a different ROM.")
            output += chunk
        elif command == 1:
            if pos + length > len(patch):
                raise ValueError("That BPS patch is cut off.")
            output += patch[pos:pos + length]
            pos += length
        elif command == 2:
            offset, pos = _bps_number(patch, pos)
            source_at += _bps_signed(offset)
            chunk = rom[source_at:source_at + length]
            if source_at < 0 or len(chunk) != length:
                raise ValueError("That BPS patch is damaged.")
            output += chunk
            source_at += length
        else:
            offset, pos = _bps_number(patch, pos)
            target_at += _bps_signed(offset)
            if target_at < 0:
                raise ValueError("That BPS patch is damaged.")
            for _ in range(length):
                if target_at >= len(output):
                    raise ValueError("That BPS patch is damaged.")
                output.append(output[target_at])
                target_at += 1
    if len(output) != target_size or pos + 8 > len(patch) - 4:
        raise ValueError("That BPS patch did not cover the ROM.")
    source_crc = int.from_bytes(patch[pos:pos + 4], "little")
    target_crc = int.from_bytes(patch[pos + 4:pos + 8], "little")
    if (zlib.crc32(rom) & 0xFFFFFFFF) != source_crc:
        raise ValueError("That patch is for a different ROM.")
    if (zlib.crc32(output) & 0xFFFFFFFF) != target_crc:
        raise ValueError("That BPS patch did not apply cleanly.")
    return bytes(output)
