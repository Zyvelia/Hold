"""Picture adjustments that sit on top of the Sharp, Smooth, and Scanlines list."""

from __future__ import annotations

_MATRICES = {
    "protanopia": (
        (0.567, 0.433, 0.0),
        (0.558, 0.442, 0.0),
        (0.0, 0.242, 0.758),
    ),
    "deuteranopia": (
        (0.625, 0.375, 0.0),
        (0.700, 0.300, 0.0),
        (0.0, 0.300, 0.700),
    ),
    "tritanopia": (
        (0.950, 0.050, 0.0),
        (0.0, 0.433, 0.567),
        (0.0, 0.475, 0.525),
    ),
}


def _clamp(value: float) -> int:
    if value < 0:
        return 0
    if value > 255:
        return 255
    return int(value)


def adjust(
    frame: bytes,
    brightness: int = 0,
    contrast: int = 0,
    color: int = 0,
    palette: str = "",
) -> bytes:
    """Brightness, contrast, color, and a color-blind palette. Bytes are B,G,R,X."""
    if not frame or (brightness == 0 and contrast == 0 and color == 0 and not palette):
        return frame
    matrix = _MATRICES.get(palette)
    sat = 1 + max(-50, min(50, color)) / 50
    contrast_f = 1 + max(-50, min(50, contrast)) / 50
    add = max(-50, min(50, brightness)) * 2
    src = frame
    out = bytearray(len(src) - (len(src) % 4))
    for index in range(0, len(out), 4):
        blue = src[index]
        green = src[index + 1]
        red = src[index + 2]
        if matrix is not None:
            red, green, blue = (
                red * matrix[0][0] + green * matrix[0][1] + blue * matrix[0][2],
                red * matrix[1][0] + green * matrix[1][1] + blue * matrix[1][2],
                red * matrix[2][0] + green * matrix[2][1] + blue * matrix[2][2],
            )
        gray = (red + green + blue) / 3
        red = gray + (red - gray) * sat
        green = gray + (green - gray) * sat
        blue = gray + (blue - gray) * sat
        red = (red - 128) * contrast_f + 128 + add
        green = (green - 128) * contrast_f + 128 + add
        blue = (blue - 128) * contrast_f + 128 + add
        out[index] = _clamp(blue)
        out[index + 1] = _clamp(green)
        out[index + 2] = _clamp(red)
        out[index + 3] = src[index + 3]
    return bytes(out)


def blend(previous: bytes | None, current: bytes) -> bytes:
    """Average two pictures so flickering transparency holds still."""
    if not previous or len(previous) != len(current) or len(current) < 4:
        return current
    out = bytearray(len(current) - (len(current) % 4))
    for index in range(0, len(out), 4):
        out[index] = (previous[index] + current[index]) // 2
        out[index + 1] = (previous[index + 1] + current[index + 1]) // 2
        out[index + 2] = (previous[index + 2] + current[index + 2]) // 2
        out[index + 3] = current[index + 3]
    return bytes(out)


def integer_box(width: int, height: int, limit_w: int, limit_h: int) -> tuple[int, int]:
    """The largest whole-pixel size that still fits."""
    if width <= 0 or height <= 0:
        return max(1, width), max(1, height)
    scale = max(1, min(max(1, limit_w) // width, max(1, limit_h) // height))
    return width * scale, height * scale


def screens_top_large(frame: bytes, width: int, height: int) -> tuple[bytes, int, int]:
    """Draw the top of a stacked pair twice as large as the bottom."""
    if width <= 0 or height < 2 or height % 2:
        return frame, width, height
    raw = bytes(frame)
    stride = width * 4
    if len(raw) < stride * height:
        return frame, width, height
    half = height // 2
    out_w = width * 2
    out_h = half * 3
    out = bytearray(out_w * out_h * 4)
    for y in range(half):
        row = raw[y * stride:(y + 1) * stride]
        for dy in range(2):
            dest = ((y * 2 + dy) * out_w) * 4
            for x in range(width):
                pix = row[x * 4:(x + 1) * 4]
                at = dest + x * 8
                out[at:at + 4] = pix
                out[at + 4:at + 8] = pix
    bottom_y = half * 2
    x0 = width // 2
    for y in range(half):
        row = raw[(y + half) * stride:(y + half + 1) * stride]
        dest = ((bottom_y + y) * out_w + x0) * 4
        out[dest:dest + stride] = row
    return bytes(out), out_w, out_h
