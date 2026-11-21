"""PlayStation DualShock 4 and DualSense pads, read as HID reports.

Xbox pads stay on XInput. A PlayStation pad is added beside them when Windows
exposes the Sony device directly.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from ctypes import wintypes

from pokemongb.gamepad import RawPad

SONY = 0x054C
DUALSENSE = {0x0CE6, 0x0DF2}

_latest: list[RawPad] = []
_devices: list[tuple[str, bool]] = []
_lock = threading.Lock()
_started = False


def _stick(value: int) -> int:
    from pokemongb.gamepad import deadzone_percent

    shifted = value - 128
    zone = int(max(0, min(100, int(deadzone_percent))) * 128 / 100)
    if abs(shifted) < zone:
        return 0
    return max(-32768, min(32767, shifted * 256))


def _hat(buttons: set[str], hat: int) -> None:
    if hat in (0, 1, 7):
        buttons.add("dup")
    if hat in (1, 2, 3):
        buttons.add("dright")
    if hat in (3, 4, 5):
        buttons.add("ddown")
    if hat in (5, 6, 7):
        buttons.add("dleft")


def parse_sony(data: bytes, dualsense: bool) -> RawPad | None:
    """Turn one Sony input report into the same buttons an Xbox pad uses."""
    if not data:
        return None
    report = data[0]
    if report == 0x01:
        offset = 1
    elif report == 0x11 and not dualsense:
        offset = 3
    elif report == 0x31 and dualsense:
        offset = 2
    else:
        return None
    need = offset + (10 if dualsense else 6)
    if len(data) < need:
        return None
    buttons: set[str] = set()
    if dualsense:
        buttons0 = data[offset + 7]
        buttons1 = data[offset + 8]
        if data[offset + 4] > 30:
            buttons.add("lt")
        if data[offset + 5] > 30:
            buttons.add("rt")
    else:
        buttons0 = data[offset + 4]
        buttons1 = data[offset + 5]
    _hat(buttons, buttons0 & 0x0F)
    if buttons0 & 0x10:
        buttons.add("west")
    if buttons0 & 0x20:
        buttons.add("south")
    if buttons0 & 0x40:
        buttons.add("east")
    if buttons0 & 0x80:
        buttons.add("north")
    if buttons1 & 0x01:
        buttons.add("lb")
    if buttons1 & 0x02:
        buttons.add("rb")
    if buttons1 & 0x04:
        buttons.add("lt")
    if buttons1 & 0x08:
        buttons.add("rt")
    if buttons1 & 0x10:
        buttons.add("back")
    if buttons1 & 0x20:
        buttons.add("start")
    if buttons1 & 0x40:
        buttons.add("l3")
    if buttons1 & 0x80:
        buttons.add("r3")
    return RawPad(
        frozenset(buttons),
        _stick(data[offset]),
        _stick(data[offset + 1]),
        _stick(data[offset + 2]),
        _stick(data[offset + 3]),
        True,
    )


def sony_rumble_report(dualsense: bool, strong: int, weak: int) -> bytes:
    """USB output report. Heavy motor is the left one, light motor is the right one."""
    heavy = max(0, min(255, (int(strong) * 255) // 65535))
    light = max(0, min(255, (int(weak) * 255) // 65535))
    if dualsense:
        report = bytearray(48)
        report[0] = 0x02
        report[1] = 0x01
        report[3] = light
        report[4] = heavy
        return bytes(report)
    report = bytearray(32)
    report[0] = 0x05
    report[1] = 0xFF
    report[4] = light
    report[5] = heavy
    return bytes(report)


def rumble_index(index: int, strong: int, weak: int) -> None:
    """Rumble one PlayStation pad. Index 0 is the first Sony pad, after any Xbox pads."""
    with _lock:
        devices = list(_devices)
    if index < 0 or index >= len(devices):
        return
    path, dualsense = devices[index]
    payload = sony_rumble_report(dualsense, strong, weak)
    _write_output(path, payload)


def sony_pads() -> list[RawPad]:
    _ensure()
    with _lock:
        return list(_latest)


def _ensure() -> None:
    global _started
    if _started or sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    _started = True
    threading.Thread(target=_watch, name="sony-pad", daemon=True).start()


def _watch() -> None:
    while True:
        try:
            pads = _read_once()
        except (OSError, ValueError, OverflowError, ctypes.ArgumentError):
            # A disconnected/broken HID device must not kill controller polling.
            pads = []
        with _lock:
            _latest.clear()
            _latest.extend(pads)
        threading.Event().wait(0.008)


def _read_once() -> list[RawPad]:
    try:
        return _enumerate()
    except OSError:
        return []


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _InterfaceData(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", _GUID), ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]


class _Attributes(ctypes.Structure):
    _fields_ = [
        ("Size", ctypes.c_ulong),
        ("VendorID", ctypes.c_ushort),
        ("ProductID", ctypes.c_ushort),
        ("VersionNumber", ctypes.c_ushort),
    ]


def _enumerate() -> list[RawPad]:
    hid = ctypes.WinDLL("hid")
    setup = ctypes.WinDLL("setupapi")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel.ReadFile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel.ReadFile.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    # Windows SetupAPI returns opaque HDEVINFO handles. All functions that
    # receive these MUST declare pointer-sized arguments on 64-bit Windows;
    # otherwise ctypes defaults to c_int and can overflow/truncate the handle.
    setup.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(_GUID), wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
    ]
    setup.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setup.SetupDiEnumDeviceInterfaces.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_GUID),
        wintypes.DWORD, ctypes.POINTER(_InterfaceData),
    ]
    setup.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_InterfaceData), ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    setup.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
    setup.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
    hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(_GUID)]
    hid.HidD_GetHidGuid.restype = None
    hid.HidD_GetAttributes.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Attributes)]
    hid.HidD_GetAttributes.restype = wintypes.BOOL
    guid = _GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    listing = setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)
    invalid = ctypes.c_void_p(-1).value
    if not listing or listing == invalid:
        return []
    found: list[RawPad] = []
    devices: list[tuple[str, bool]] = []
    try:
        index = 0
        while True:
            data = _InterfaceData()
            data.cbSize = ctypes.sizeof(data)
            if not setup.SetupDiEnumDeviceInterfaces(listing, None, ctypes.byref(guid), index, ctypes.byref(data)):
                break
            index += 1
            needed = wintypes.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(listing, ctypes.byref(data), None, 0, ctypes.byref(needed), None)
            if needed.value < 8:
                continue
            detail = ctypes.create_string_buffer(needed.value)
            ctypes.cast(detail, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if not setup.SetupDiGetDeviceInterfaceDetailW(
                listing, ctypes.byref(data), detail, needed.value, None, None
            ):
                continue
            path = ctypes.wstring_at(ctypes.addressof(detail) + 4)
            device = kernel.CreateFileW(path, 0x80000000, 3, None, 3, 0, None)
            if not device or device == invalid:
                continue
            try:
                attrs = _Attributes()
                attrs.Size = ctypes.sizeof(attrs)
                if not hid.HidD_GetAttributes(device, ctypes.byref(attrs)):
                    continue
                if attrs.VendorID != SONY:
                    continue
                buf = ctypes.create_string_buffer(64)
                read = wintypes.DWORD()
                if not kernel.ReadFile(device, buf, 64, ctypes.byref(read), None) or not read.value:
                    continue
                dualsense = attrs.ProductID in DUALSENSE
                pad = parse_sony(bytes(buf[: read.value]), dualsense)
                if pad is not None:
                    found.append(pad)
                    devices.append((path, dualsense))
            finally:
                kernel.CloseHandle(device)
    finally:
        setup.SetupDiDestroyDeviceInfoList(listing)
    with _lock:
        _devices.clear()
        _devices.extend(devices)
    return found


def _write_output(path: str, payload: bytes) -> None:
    if sys.platform != "win32":
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    hid = ctypes.WinDLL("hid")
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    hid.HidD_SetOutputReport.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG]
    hid.HidD_SetOutputReport.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    device = kernel.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
    if not device or device == invalid:
        return
    try:
        buf = ctypes.create_string_buffer(payload)
        hid.HidD_SetOutputReport(device, buf, len(payload))
    finally:
        kernel.CloseHandle(device)
