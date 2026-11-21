"""Load a libretro core and run one frame at a time.

The core is a normal DLL. This host gives it directories, a pixel format,
button state, and a place to put the picture and the sound.
"""

from __future__ import annotations

import array
import ctypes
from ctypes import wintypes
from pathlib import Path

from pokemongb.gamepad import set_rumble
from pokemongb.gl import GlError
from pokemongb.gl import Host as GlHost
from pokemongb.vulkan import Host as VulkanHost
from pokemongb.vulkan import VulkanError

RETRO_DEVICE_JOYPAD = 1
RETRO_DEVICE_MOUSE = 2
RETRO_DEVICE_ANALOG = 5
RETRO_DEVICE_POINTER = 6
RETRO_DEVICE_ID_MOUSE_LEFT = 2
RETRO_DEVICE_ID_ANALOG_X = 0
RETRO_DEVICE_ID_ANALOG_Y = 1
RETRO_DEVICE_INDEX_ANALOG_LEFT = 0
RETRO_DEVICE_INDEX_ANALOG_RIGHT = 1
RETRO_DEVICE_ID_POINTER_X = 0
RETRO_DEVICE_ID_POINTER_Y = 1
RETRO_DEVICE_ID_POINTER_PRESSED = 2
RETRO_DEVICE_ID_JOYPAD_B = 0
RETRO_DEVICE_ID_JOYPAD_SELECT = 2
RETRO_DEVICE_ID_JOYPAD_START = 3
RETRO_DEVICE_ID_JOYPAD_UP = 4
RETRO_DEVICE_ID_JOYPAD_DOWN = 5
RETRO_DEVICE_ID_JOYPAD_LEFT = 6
RETRO_DEVICE_ID_JOYPAD_RIGHT = 7
RETRO_DEVICE_ID_JOYPAD_A = 8
RETRO_DEVICE_ID_JOYPAD_L = 10
RETRO_DEVICE_ID_JOYPAD_R = 11
RETRO_DEVICE_ID_JOYPAD_L2 = 12
RETRO_DEVICE_ID_JOYPAD_R2 = 13

PIXEL_0RGB1555 = 0
PIXEL_XRGB8888 = 1
PIXEL_RGB565 = 2

ENV_SET_ROTATION = 1
ENV_GET_OVERSCAN = 2
ENV_GET_CAN_DUPE = 3
ENV_SET_MESSAGE = 6
ENV_SHUTDOWN = 7
ENV_SET_PERFORMANCE_LEVEL = 8
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_SET_INPUT_DESCRIPTORS = 11
ENV_SET_KEYBOARD_CALLBACK = 12
ENV_SET_DISK_CONTROL_INTERFACE = 13
ENV_SET_HW_RENDER = 14
ENV_GET_HW_RENDER_INTERFACE = 41
ENV_SET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE = 43
ENV_GET_PREFERRED_HW_RENDER = 56
ENV_GET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE_SUPPORT = 73
HW_OPENGL = 1
HW_OPENGL_CORE = 3
HW_VULKAN = 6
HW_FRAME = (1 << 64) - 1
ENV_GET_VARIABLE = 15
ENV_SET_VARIABLES = 16
ENV_GET_VARIABLE_UPDATE = 17
ENV_SET_SUPPORT_NO_GAME = 18
ENV_GET_LIBRETRO_PATH = 19
ENV_SET_FRAME_TIME_CALLBACK = 21
ENV_SET_AUDIO_CALLBACK = 22
ENV_GET_RUMBLE_INTERFACE = 23
ENV_GET_INPUT_DEVICE_CAPABILITIES = 24
ENV_GET_LOG_INTERFACE = 27
ENV_GET_CONTENT_DIRECTORY = 30
ENV_GET_SAVE_DIRECTORY = 31
ENV_SET_SYSTEM_AV_INFO = 32
ENV_SET_SUBSYSTEM_INFO = 34
ENV_SET_CONTROLLER_INFO = 35
ENV_SET_MEMORY_MAPS = 36
ENV_SET_GEOMETRY = 37
ENV_GET_USERNAME = 38
ENV_GET_LANGUAGE = 39
ENV_GET_CURRENT_SOFTWARE_FRAMEBUFFER = 40
ENV_SET_SUPPORT_ACHIEVEMENTS = 42
ENV_SET_SERIALIZATION_QUIRKS = 44
ENV_SET_SERIALIZATION_QUIRKS_2 = 87
ENV_GET_VFS_INTERFACE = 45
ENV_GET_AUDIO_VIDEO_ENABLE = 47
ENV_GET_FASTFORWARDING = 49
ENV_GET_TARGET_REFRESH_RATE = 50
ENV_GET_INPUT_BITMASKS = 51
ENV_GET_CORE_OPTIONS_VERSION = 52
ENV_SET_CORE_OPTIONS = 53
ENV_SET_CORE_OPTIONS_INTL = 54
ENV_GET_MESSAGE_INTERFACE_VERSION = 59
ENV_GET_INPUT_MAX_USERS = 61
ENV_SET_MINIMUM_AUDIO_LATENCY = 63
ENV_GET_SAVESTATE_CONTEXT = 72
ENV_GET_JIT_CAPABLE = 74

EXPERIMENTAL = 0x10000
MEMORY_SAVE_RAM = 0
MEMORY_SYSTEM_RAM = 2


def _read_u32(address: int, offset: int) -> int:
    return ctypes.cast(address + offset, ctypes.POINTER(ctypes.c_uint32)).contents.value


def _read_u64(address: int, offset: int) -> int:
    return ctypes.cast(address + offset, ctypes.POINTER(ctypes.c_uint64)).contents.value


def _write_u64(address: int, offset: int, value: int) -> None:
    ctypes.cast(address + offset, ctypes.POINTER(ctypes.c_uint64)).contents.value = value


def _color_lut(kind: str) -> array.array:
    table = array.array("I", [0]) * 65536
    for pixel in range(65536):
        if kind == "565":
            blue = (pixel & 0x1F) * 255 // 31
            green = ((pixel >> 5) & 0x3F) * 255 // 63
            red = ((pixel >> 11) & 0x1F) * 255 // 31
        else:
            blue = (pixel & 0x1F) * 255 // 31
            green = ((pixel >> 5) & 0x1F) * 255 // 31
            red = ((pixel >> 10) & 0x1F) * 255 // 31
        table[pixel] = 0xFF000000 | (red << 16) | (green << 8) | blue
    return table


_LUT565 = _color_lut("565")
_LUT1555 = _color_lut("1555")

ENV_T = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_void_p)
VIDEO_T = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t)
AUDIO_SAMPLE_T = ctypes.CFUNCTYPE(None, ctypes.c_int16, ctypes.c_int16)
AUDIO_BATCH_T = ctypes.CFUNCTYPE(ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t)
INPUT_POLL_T = ctypes.CFUNCTYPE(None)
INPUT_STATE_T = ctypes.CFUNCTYPE(ctypes.c_int16, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)
LOG_T = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)


RUMBLE_T = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint16)


class retro_log_callback(ctypes.Structure):
    _fields_ = [("log", LOG_T)]


class retro_rumble_interface(ctypes.Structure):
    _fields_ = [("set_rumble_state", RUMBLE_T)]


class retro_memory_descriptor(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint64),
        ("ptr", ctypes.c_void_p),
        ("offset", ctypes.c_size_t),
        ("start", ctypes.c_size_t),
        ("select", ctypes.c_size_t),
        ("disconnect", ctypes.c_size_t),
        ("len", ctypes.c_size_t),
        ("addrspace", ctypes.c_char_p),
    ]


class retro_memory_map(ctypes.Structure):
    _fields_ = [
        ("descriptors", ctypes.POINTER(retro_memory_descriptor)),
        ("num_descriptors", ctypes.c_uint),
    ]


def rumble_motors(strong: int, weak: int, effect: int, strength: int) -> tuple[int, int]:
    """Effect 0 is the heavy motor. Effect 1 is the light motor."""
    level = max(0, min(65535, int(strength)))
    if int(effect) == 0:
        return level, max(0, min(65535, int(weak)))
    return max(0, min(65535, int(strong))), level


def find_gba_io(ranges: list[tuple[int, int, int, int]]) -> int:
    """Pointer to the GBA IO window at 0x04000000, or 0 when it is not mapped."""
    target = 0x04000120
    for start, _select, length, ptr in ranges:
        if not ptr or length < 0x12A:
            continue
        if start == 0x04000000:
            return int(ptr)
        gap = 0x04000000 - start
        if 0 < gap < length and length <= 0x10000 and start + length > target:
            return int(ptr) + gap
    return 0


def exchange_gba_link(base: int, remote: int) -> int:
    """When a transfer is waiting, store the other machine's halfword.

    Returns the local halfword, or -1 when nothing was waiting.
    """
    if not base:
        return -1
    control = ctypes.c_uint16.from_address(base + 0x128).value
    if not (control & 0x80):
        return -1
    outgoing = ctypes.c_uint16.from_address(base + 0x120).value
    ctypes.c_uint16.from_address(base + 0x122).value = remote & 0xFFFF
    ctypes.c_uint16.from_address(base + 0x128).value = control & ~0x80
    return outgoing


class retro_system_info(ctypes.Structure):
    _fields_ = [
        ("library_name", ctypes.c_char_p),
        ("library_version", ctypes.c_char_p),
        ("valid_extensions", ctypes.c_char_p),
        ("need_fullpath", ctypes.c_bool),
        ("block_extract", ctypes.c_bool),
    ]


class retro_message(ctypes.Structure):
    _fields_ = [
        ("msg", ctypes.c_char_p),
        ("frames", ctypes.c_uint),
    ]


class retro_game_info(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_char_p),
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
        ("meta", ctypes.c_char_p),
    ]


class retro_game_geometry(ctypes.Structure):
    _fields_ = [
        ("base_width", ctypes.c_uint),
        ("base_height", ctypes.c_uint),
        ("max_width", ctypes.c_uint),
        ("max_height", ctypes.c_uint),
        ("aspect_ratio", ctypes.c_float),
    ]


class retro_system_timing(ctypes.Structure):
    _fields_ = [
        ("fps", ctypes.c_double),
        ("sample_rate", ctypes.c_double),
    ]


class retro_system_av_info(ctypes.Structure):
    _fields_ = [
        ("geometry", retro_game_geometry),
        ("timing", retro_system_timing),
    ]


class retro_hw_negotiation(ctypes.Structure):
    _fields_ = [
        ("interface_type", ctypes.c_int),
        ("interface_version", ctypes.c_uint),
        ("get_application_info", ctypes.c_void_p),
        ("create_device", ctypes.c_void_p),
        ("destroy_device", ctypes.c_void_p),
        ("create_instance", ctypes.c_void_p),
        ("create_device2", ctypes.c_void_p),
    ]


class retro_variable(ctypes.Structure):
    _fields_ = [
        ("key", ctypes.c_char_p),
        ("value", ctypes.c_char_p),
    ]


class retro_message(ctypes.Structure):
    _fields_ = [
        ("msg", ctypes.c_char_p),
        ("frames", ctypes.c_uint),
    ]


class CoreError(RuntimeError):
    pass


class Core:
    """One loaded libretro DLL and the ROM it is playing."""

    def __init__(
        self,
        dll_path: Path,
        system_dir: Path,
        save_dir: Path,
        variables: dict[bytes, bytes] | None = None,
        hardware: str | None = None,
    ):
        self.dll_path = Path(dll_path)
        self.system_dir = Path(system_dir)
        self.save_dir = Path(save_dir)
        self.system_dir.mkdir(parents=True, exist_ok=True)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.buttons = [False] * 16
        self.buttons_p2 = [False] * 16
        self.buttons_p3 = [False] * 16
        self.buttons_p4 = [False] * 16
        self.analog = [0, 0, 0, 0]
        self.analog_p2 = [0, 0, 0, 0]
        self.analog_p3 = [0, 0, 0, 0]
        self.analog_p4 = [0, 0, 0, 0]
        self.pointer_x = 0
        self.pointer_y = 0
        self.pointer_pressed = False
        self._rumble_strong = [0, 0, 0, 0]
        self._rumble_weak = [0, 0, 0, 0]
        self._io_base = 0
        self.messages: list[str] = []
        self.frame = None
        self.frame_size = (0, 0)
        self.audio = bytearray()
        self.sample_rate = 48000.0
        self.fps = 60.0
        self.pixel_format = PIXEL_XRGB8888
        self.variables: dict[bytes, bytes] = dict(variables or {})
        self._variable_ptrs: list[ctypes.c_char_p] = []
        self.game_loaded = False
        self._rom_buffer = None
        self._path_buf = None
        self._dir_system = ctypes.c_char_p(str(self.system_dir).encode("utf-8"))
        self._dir_save = ctypes.c_char_p(str(self.save_dir).encode("utf-8"))
        self._dir_core = ctypes.c_char_p(str(self.dll_path.parent).encode("utf-8"))
        self._username = ctypes.c_char_p(b"Player")
        self._sram_path: Path | None = None
        self._unknown_env: set[int] = set()
        self.hardware = hardware
        if hardware == "vulkan":
            self.gpu = VulkanHost()
        elif hardware == "opengl":
            self.gpu = GlHost()
        else:
            self.gpu = None
        self._hw_reset_ptr = None
        self._hw_destroy_ptr = None
        self._hw_requested = False
        self._hw_reset_done = False
        self._hw_get_fb = ctypes.CFUNCTYPE(ctypes.c_uint64)(lambda: 0)
        self._hw_get_proc = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)(lambda _name: None)

        try:
            self.lib = ctypes.CDLL(str(self.dll_path))
        except OSError as exc:
            raise CoreError(f"Could not load {self.dll_path.name}. {exc}") from exc
        self._bind()
        self._env_cb = ENV_T(self._environment)
        self._video_cb = VIDEO_T(self._video_refresh)
        self._audio_sample_cb = AUDIO_SAMPLE_T(self._audio_sample)
        self._audio_batch_cb = AUDIO_BATCH_T(self._audio_batch)
        self._input_poll_cb = INPUT_POLL_T(self._input_poll)
        self._input_state_cb = INPUT_STATE_T(self._input_state)
        self._log = []
        self._log_cb = LOG_T(self._log_print)
        self._rumble_cb = RUMBLE_T(self._set_rumble)
        self._rumble_iface = None
        self.lib.retro_set_environment(self._env_cb)
        # Mesen builds its emulator object inside retro_init. The picture
        # and button callbacks have to be handed over after that.
        self.lib.retro_init()
        self.lib.retro_set_video_refresh(self._video_cb)
        self.lib.retro_set_audio_sample(self._audio_sample_cb)
        self.lib.retro_set_audio_sample_batch(self._audio_batch_cb)
        self.lib.retro_set_input_poll(self._input_poll_cb)
        self.lib.retro_set_input_state(self._input_state_cb)
        try:
            self._finish_hw()
        except (VulkanError, GlError) as exc:
            raise CoreError(str(exc)) from exc

    def _bind(self) -> None:
        lib = self.lib
        lib.retro_api_version.restype = ctypes.c_uint
        lib.retro_set_environment.argtypes = [ENV_T]
        lib.retro_set_video_refresh.argtypes = [VIDEO_T]
        lib.retro_set_audio_sample.argtypes = [AUDIO_SAMPLE_T]
        lib.retro_set_audio_sample_batch.argtypes = [AUDIO_BATCH_T]
        lib.retro_set_input_poll.argtypes = [INPUT_POLL_T]
        lib.retro_set_input_state.argtypes = [INPUT_STATE_T]
        lib.retro_init.argtypes = []
        lib.retro_deinit.argtypes = []
        lib.retro_get_system_info.argtypes = [ctypes.POINTER(retro_system_info)]
        lib.retro_get_system_av_info.argtypes = [ctypes.POINTER(retro_system_av_info)]
        lib.retro_load_game.argtypes = [ctypes.POINTER(retro_game_info)]
        lib.retro_load_game.restype = ctypes.c_bool
        lib.retro_unload_game.argtypes = []
        lib.retro_run.argtypes = []
        lib.retro_reset.argtypes = []
        lib.retro_get_memory_data.argtypes = [ctypes.c_uint]
        lib.retro_get_memory_data.restype = ctypes.c_void_p
        lib.retro_get_memory_size.argtypes = [ctypes.c_uint]
        lib.retro_get_memory_size.restype = ctypes.c_size_t
        lib.retro_serialize_size.restype = ctypes.c_size_t
        lib.retro_serialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.retro_serialize.restype = ctypes.c_bool
        lib.retro_unserialize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        lib.retro_unserialize.restype = ctypes.c_bool

    def system_info(self) -> retro_system_info:
        info = retro_system_info()
        self.lib.retro_get_system_info(ctypes.byref(info))
        return info

    def load(
        self,
        rom_path: Path,
        save_name: str | None = None,
        content_name: str | None = None,
        *,
        full_path_only: bool = False,
    ) -> None:
        rom_path = Path(rom_path)
        if self.game_loaded:
            self.unload()
        if full_path_only:
            if not rom_path.is_file():
                raise CoreError(f"{rom_path.name} is not a file the core can open.")
            size = rom_path.stat().st_size
            with rom_path.open("rb") as handle:
                head = handle.read(0x1000)
            if not head:
                head = b"\x00"
            self._rom_buffer = (ctypes.c_char * len(head)).from_buffer_copy(head)
            data_ptr = ctypes.cast(self._rom_buffer, ctypes.c_void_p)
        else:
            data = rom_path.read_bytes()
            if not data:
                raise CoreError("That ROM is empty.")
            self._rom_buffer = (ctypes.c_char * len(data)).from_buffer_copy(data)
            size = len(data)
            data_ptr = ctypes.cast(self._rom_buffer, ctypes.c_void_p)
        shown = content_name if content_name else str(rom_path)
        self._path_buf = ctypes.c_char_p(shown.encode("utf-8"))
        info = retro_game_info()
        info.path = self._path_buf
        info.data = data_ptr
        info.size = size
        info.meta = None
        ok = self.lib.retro_load_game(ctypes.byref(info))
        if not ok:
            raise CoreError(f"{self.dll_path.name} did not accept {rom_path.name}.")
        self.game_loaded = True
        av = retro_system_av_info()
        self.lib.retro_get_system_av_info(ctypes.byref(av))
        self.sample_rate = float(av.timing.sample_rate or 48000.0)
        self.fps = float(av.timing.fps or 60.0)
        self.frame_size = (int(av.geometry.base_width), int(av.geometry.base_height))
        self._sram_path = self.save_dir / f"{save_name or rom_path.stem}.srm"
        self._load_sram()
        self.audio.clear()
        self.buttons = [False] * 16
        self.buttons_p2 = [False] * 16
        self.buttons_p3 = [False] * 16
        self.buttons_p4 = [False] * 16
        self.analog = [0, 0, 0, 0]
        self.analog_p2 = [0, 0, 0, 0]
        self.analog_p3 = [0, 0, 0, 0]
        self.analog_p4 = [0, 0, 0, 0]
        self.pointer_pressed = False
        try:
            self._finish_hw()
        except (VulkanError, GlError) as exc:
            raise CoreError(str(exc)) from exc

    def _ensure_device(self) -> None:
        if self.gpu is not None and not self.gpu.device:
            self.gpu.start()

    def _call_hw(self, pointer) -> None:
        if pointer:
            ctypes.CFUNCTYPE(None)(pointer)()

    def _destroy_hw_context(self) -> None:
        if self._hw_reset_done:
            self._call_hw(self._hw_destroy_ptr)
            self._hw_reset_done = False

    def _finish_hw(self, force_reset: bool = False) -> None:
        if not self._hw_requested or self.gpu is None:
            return
        self._ensure_device()
        if not self._hw_reset_ptr:
            return
        if self._hw_reset_done and not force_reset:
            return
        if self._hw_reset_done:
            self._destroy_hw_context()
        self._hw_reset_done = True
        self._call_hw(self._hw_reset_ptr)

    def unload(self) -> None:
        if not self.game_loaded:
            return
        self._store_sram()
        self._destroy_hw_context()
        self.lib.retro_unload_game()
        self.game_loaded = False
        self.frame = None

    def reset(self) -> None:
        if self.game_loaded:
            self.lib.retro_reset()

    def run(self) -> None:
        if self.game_loaded:
            if self.gpu is not None and self.gpu.device:
                self.gpu.begin_frame()
            self.lib.retro_run()

    def set_cheats(self, codes: list[str]) -> None:
        if not self.game_loaded:
            return
        try:
            reset = self.lib.retro_cheat_reset
            apply = self.lib.retro_cheat_set
        except AttributeError:
            return
        reset.argtypes = []
        reset.restype = None
        apply.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_char_p]
        apply.restype = None
        reset()
        self._cheat_keep = []
        for index, code in enumerate(codes):
            kept = ctypes.c_char_p(code.encode("utf-8"))
            self._cheat_keep.append(kept)
            apply(index, True, kept)

    def take_audio(self) -> bytes:
        data = bytes(self.audio)
        self.audio.clear()
        return data

    def store_sram(self) -> None:
        self._store_sram()

    def serialize(self) -> bytes:
        if not self.game_loaded:
            raise CoreError("No game is loaded.")
        size = int(self.lib.retro_serialize_size())
        if size <= 0:
            raise CoreError("This core cannot save a state.")
        buf = ctypes.create_string_buffer(size)
        ok = self.lib.retro_serialize(ctypes.cast(buf, ctypes.c_void_p), size)
        if not ok:
            raise CoreError("The core refused to save a state.")
        return buf.raw

    def unserialize(self, blob: bytes) -> None:
        if not self.game_loaded:
            raise CoreError("No game is loaded.")
        size = int(self.lib.retro_serialize_size())
        if size <= 0 or len(blob) != size:
            raise CoreError("That save state does not match this game.")
        buf = ctypes.create_string_buffer(size)
        ctypes.memmove(buf, blob, size)
        ok = self.lib.retro_unserialize(ctypes.cast(buf, ctypes.c_void_p), size)
        if not ok:
            raise CoreError("The core refused that save state.")

    def close(self) -> None:
        self.unload()
        if self.gpu is not None:
            destroy = self.gpu._negotiate_destroy
            self.gpu.close(destroy)
            self.gpu = None
        try:
            self.lib.retro_deinit()
        except Exception:
            pass

    def _load_sram(self) -> None:
        path = self._sram_path
        if path is None or not path.is_file():
            return
        blob = path.read_bytes()
        size = int(self.lib.retro_get_memory_size(MEMORY_SAVE_RAM))
        ptr = self.lib.retro_get_memory_data(MEMORY_SAVE_RAM)
        if not size or not ptr or not blob:
            return
        count = min(size, len(blob))
        ctypes.memmove(ptr, blob, count)

    def _store_sram(self) -> None:
        path = self._sram_path
        if path is None:
            return
        size = int(self.lib.retro_get_memory_size(MEMORY_SAVE_RAM))
        ptr = self.lib.retro_get_memory_data(MEMORY_SAVE_RAM)
        if not size or not ptr:
            return
        path.write_bytes(ctypes.string_at(ptr, size))

    def system_ram(self) -> dict[int, int]:
        if not self.game_loaded:
            return {}
        try:
            size = int(self.lib.retro_get_memory_size(MEMORY_SYSTEM_RAM))
            ptr = self.lib.retro_get_memory_data(MEMORY_SYSTEM_RAM)
        except (OSError, AttributeError):
            return {}
        if not size or not ptr:
            return {}
        count = min(int(size), 262144)
        blob = ctypes.string_at(ptr, count)
        return {index: byte for index, byte in enumerate(blob)}

    def poke_ram(self, address: int, value: int) -> bool:
        if not self.game_loaded or address < 0:
            return False
        try:
            size = int(self.lib.retro_get_memory_size(MEMORY_SYSTEM_RAM))
            ptr = self.lib.retro_get_memory_data(MEMORY_SYSTEM_RAM)
        except (OSError, AttributeError):
            return False
        if not size or not ptr or address >= int(size):
            return False
        ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint8))[address] = value & 0xFF
        return True

    def gba_link_read(self) -> tuple[int, bool]:
        if not self._io_base:
            return 0, False
        data = ctypes.c_uint16.from_address(self._io_base + 0x120).value
        control = ctypes.c_uint16.from_address(self._io_base + 0x128).value
        return int(data), bool(control & 0x80)

    def gba_link_apply(self, remote: int) -> int:
        return exchange_gba_link(self._io_base, remote)

    def _video_refresh(self, data, width, height, pitch) -> None:
        width = int(width)
        height = int(height)
        pitch = int(pitch)
        if data is not None and int(data) == HW_FRAME and self.gpu is not None:
            try:
                packed = self.gpu.read_frame(width, height)
            except (VulkanError, GlError) as exc:
                self.messages.append(str(exc))
                return
            if packed:
                self.frame = packed
                self.frame_size = (packed[1], packed[2])
            return
        if not data or width <= 0 or height <= 0:
            return
        self.frame_size = (width, height)
        if self.pixel_format == PIXEL_XRGB8888:
            row_bytes = width * 4
            raw = bytearray(width * height * 4)
            for y in range(height):
                raw[y * row_bytes:(y + 1) * row_bytes] = ctypes.string_at(data + y * pitch, row_bytes)
            raw[3::4] = b"\xff" * (width * height)
            self.frame = (bytes(raw), width, height)
            return
        lut = _LUT565 if self.pixel_format == PIXEL_RGB565 else _LUT1555
        out = array.array("I")
        for y in range(height):
            row = ctypes.string_at(data + y * pitch, width * 2)
            pixels = array.array("H")
            pixels.frombytes(row)
            out.extend(lut[pixel] for pixel in pixels)
        self.frame = (out.tobytes(), width, height)

    def _audio_sample(self, left, right) -> None:
        self.audio += int(left).to_bytes(2, "little", signed=True)
        self.audio += int(right).to_bytes(2, "little", signed=True)

    def _audio_batch(self, data, frames) -> int:
        count = int(frames)
        if count <= 0 or not data:
            return 0
        self.audio += ctypes.string_at(data, count * 4)
        return count

    def _input_poll(self) -> None:
        return

    def set_pointer(self, x: float, y: float, pressed: bool) -> None:
        """Absolute touch position in framebuffer pixels."""
        width, height = self.frame_size
        if width <= 0 or height <= 0 or not pressed:
            self.pointer_pressed = False
            return
        nx = int(x * 0x10000 / width) - 0x8000
        ny = int(y * 0x10000 / height) - 0x8000
        self.pointer_x = max(-32768, min(32767, nx))
        self.pointer_y = max(-32768, min(32767, ny))
        self.pointer_pressed = True

    def _input_state(self, port, device, index, ident) -> int:
        port = int(port)
        if port not in (0, 1, 2, 3):
            return 0
        device = int(device)
        ident = int(ident)
        index = int(index)
        buttons = (self.buttons, self.buttons_p2, self.buttons_p3, self.buttons_p4)[port]
        analog = (self.analog, self.analog_p2, self.analog_p3, self.analog_p4)[port]
        if device == RETRO_DEVICE_ANALOG:
            if index not in (RETRO_DEVICE_INDEX_ANALOG_LEFT, RETRO_DEVICE_INDEX_ANALOG_RIGHT):
                return 0
            if ident not in (RETRO_DEVICE_ID_ANALOG_X, RETRO_DEVICE_ID_ANALOG_Y):
                return 0
            return analog[index * 2 + ident]
        if port != 0:
            if device != RETRO_DEVICE_JOYPAD:
                return 0
            if 0 <= ident < len(buttons) and buttons[ident]:
                return 1
            return 0
        if index != 0:
            return 0
        if device == RETRO_DEVICE_MOUSE:
            if ident == RETRO_DEVICE_ID_MOUSE_LEFT:
                return 1 if self.pointer_pressed else 0
            return 0
        if device == RETRO_DEVICE_POINTER:
            if ident == RETRO_DEVICE_ID_POINTER_X:
                return self.pointer_x
            if ident == RETRO_DEVICE_ID_POINTER_Y:
                return self.pointer_y
            if ident == RETRO_DEVICE_ID_POINTER_PRESSED:
                return 1 if self.pointer_pressed else 0
            return 0
        if device != RETRO_DEVICE_JOYPAD:
            return 0
        if 0 <= ident < len(buttons) and buttons[ident]:
            return 1
        return 0

    def _environment(self, cmd, data) -> bool:
        kind = int(cmd) & 0xFFFF
        self._log.append(kind)
        if kind == ENV_GET_CAN_DUPE:
            self._write_bool(data, True)
            return True
        if kind == ENV_SET_PIXEL_FORMAT:
            fmt = ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0]
            if fmt not in (PIXEL_0RGB1555, PIXEL_XRGB8888, PIXEL_RGB565):
                return False
            self.pixel_format = int(fmt)
            return True
        if kind in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_CONTENT_DIRECTORY):
            self._write_string(data, self._dir_system)
            return True
        if kind == ENV_GET_SAVE_DIRECTORY:
            self._write_string(data, self._dir_save)
            return True
        if kind == ENV_GET_LIBRETRO_PATH:
            self._write_string(data, self._dir_core)
            return True
        if kind == ENV_GET_USERNAME:
            self._write_string(data, self._username)
            return True
        if kind == ENV_GET_LANGUAGE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 0
            return True
        if kind == ENV_GET_LOG_INTERFACE:
            callback = retro_log_callback(self._log_cb)
            ctypes.memmove(data, ctypes.byref(callback), ctypes.sizeof(callback))
            return True
        if kind == ENV_GET_VARIABLE:
            return self._get_variable(data)
        if kind == ENV_SET_VARIABLES:
            self._set_variables(data)
            return True
        if kind == ENV_GET_VARIABLE_UPDATE:
            self._write_bool(data, False)
            return True
        if kind == ENV_GET_CORE_OPTIONS_VERSION:
            return False
        if kind == ENV_SET_SUPPORT_NO_GAME:
            return True
        if kind == ENV_GET_INPUT_DEVICE_CAPABILITIES:
            mask = (
                (1 << RETRO_DEVICE_JOYPAD)
                | (1 << RETRO_DEVICE_MOUSE)
                | (1 << RETRO_DEVICE_ANALOG)
                | (1 << RETRO_DEVICE_POINTER)
            )
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint64))[0] = mask
            return True
        if kind == ENV_GET_PREFERRED_HW_RENDER and self.hardware == "vulkan":
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = HW_VULKAN
            return True
        if kind == ENV_GET_PREFERRED_HW_RENDER and self.hardware == "opengl":
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = HW_OPENGL_CORE
            return True
        if kind == ENV_GET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE_SUPPORT and self.hardware == "vulkan":
            header = ctypes.cast(data, ctypes.POINTER(retro_hw_negotiation)).contents
            header.interface_version = 2 if header.interface_type == 0 else 0
            return True
        if kind == ENV_SET_HW_RENDER_CONTEXT_NEGOTIATION_INTERFACE and self.hardware == "vulkan":
            header = ctypes.cast(data, ctypes.POINTER(retro_hw_negotiation)).contents
            self.gpu.remember_negotiation(
                int(header.interface_version),
                header.get_application_info,
                header.create_device,
                header.destroy_device,
                header.create_instance,
                header.create_device2,
            )
            return True
        if kind == ENV_SET_HW_RENDER and self.gpu is not None:
            base = int(data)
            context = _read_u32(base, 0)
            if self.hardware == "vulkan" and context != HW_VULKAN:
                return False
            if self.hardware == "opengl" and context not in (HW_OPENGL, HW_OPENGL_CORE):
                return False
            self._hw_reset_ptr = _read_u64(base, 8) or None
            self._hw_destroy_ptr = _read_u64(base, 48) or None
            if self.hardware == "opengl":
                self.gpu.core_profile = context == HW_OPENGL_CORE
                self.gpu.bottom_left = bool(ctypes.cast(base + 34, ctypes.POINTER(ctypes.c_ubyte))[0])
                self._hw_get_fb = self.gpu._fb_cb
                self._hw_get_proc = self.gpu._proc_cb
            _write_u64(base, 16, ctypes.cast(self._hw_get_fb, ctypes.c_void_p).value or 0)
            _write_u64(base, 24, ctypes.cast(self._hw_get_proc, ctypes.c_void_p).value or 0)
            self._hw_requested = True
            try:
                self._ensure_device()
                if self._hw_reset_ptr and not self._hw_reset_done:
                    self._hw_reset_done = True
                    self._call_hw(self._hw_reset_ptr)
            except (VulkanError, GlError) as exc:
                self.messages.append(str(exc))
                return False
            return True
        if kind == ENV_GET_HW_RENDER_INTERFACE and self.hardware == "vulkan" and self._hw_requested:
            try:
                self._ensure_device()
            except VulkanError as exc:
                self.messages.append(str(exc))
                return False
            self.gpu.fill_interface(data)
            return True
        if kind == ENV_GET_AUDIO_VIDEO_ENABLE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_int))[0] = 1 | 2
            return True
        if kind == ENV_GET_FASTFORWARDING:
            self._write_bool(data, False)
            return True
        if kind == ENV_GET_TARGET_REFRESH_RATE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_float))[0] = 60.0
            return True
        if kind == ENV_GET_INPUT_MAX_USERS:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_uint))[0] = 4
            return True
        if kind == ENV_GET_RUMBLE_INTERFACE:
            iface = retro_rumble_interface(self._rumble_cb)
            self._rumble_iface = iface
            ctypes.memmove(data, ctypes.byref(iface), ctypes.sizeof(iface))
            return True
        if kind == ENV_SET_MEMORY_MAPS:
            self._take_memory_map(data)
            return True
        if kind == ENV_GET_JIT_CAPABLE:
            self._write_bool(data, True)
            return True
        if kind == ENV_SET_GEOMETRY:
            geo = ctypes.cast(data, ctypes.POINTER(retro_game_geometry)).contents
            self.frame_size = (int(geo.base_width), int(geo.base_height))
            return True
        if kind == ENV_SET_SYSTEM_AV_INFO:
            av = ctypes.cast(data, ctypes.POINTER(retro_system_av_info)).contents
            self.frame_size = (int(av.geometry.base_width), int(av.geometry.base_height))
            self.sample_rate = float(av.timing.sample_rate or self.sample_rate)
            self.fps = float(av.timing.fps or self.fps)
            return True
        if kind == ENV_SET_MESSAGE:
            message = ctypes.cast(data, ctypes.POINTER(retro_message)).contents
            if message.msg:
                self.messages.append(message.msg.decode("utf-8", errors="replace"))
            return True
        if kind in (
            ENV_SET_ROTATION,
            ENV_SET_PERFORMANCE_LEVEL,
            ENV_SET_INPUT_DESCRIPTORS,
            ENV_SET_CONTROLLER_INFO,
            ENV_SET_SUBSYSTEM_INFO,
            ENV_SET_SUPPORT_ACHIEVEMENTS,
            ENV_SET_SERIALIZATION_QUIRKS,
            ENV_SET_SERIALIZATION_QUIRKS_2,
            ENV_SHUTDOWN,
        ):
            return True
        self._unknown_env.add(kind)
        return False

    def _set_rumble(self, port, effect, strength) -> bool:
        port = int(port)
        if port < 0 or port > 3:
            return False
        strong, weak = rumble_motors(
            self._rumble_strong[port],
            self._rumble_weak[port],
            int(effect),
            int(strength),
        )
        self._rumble_strong[port] = strong
        self._rumble_weak[port] = weak
        set_rumble(port, strong, weak)
        return True

    def _take_memory_map(self, data) -> None:
        try:
            view = ctypes.cast(data, ctypes.POINTER(retro_memory_map)).contents
            count = int(view.num_descriptors)
            if count <= 0 or not view.descriptors:
                return
            ranges = []
            for index in range(min(count, 128)):
                desc = view.descriptors[index]
                ranges.append((int(desc.start), int(desc.select), int(desc.len), int(desc.ptr or 0)))
            found = find_gba_io(ranges)
            if found:
                self._io_base = found
        except (OSError, ValueError, ctypes.ArgumentError):
            return

    def _log_print(self, level: int, fmt) -> None:
        if level < 1 or not fmt:
            return
        text = fmt.decode("utf-8", errors="replace") if isinstance(fmt, bytes) else str(fmt)
        self.messages.append(text)
        if len(self.messages) > 40:
            del self.messages[:-40]

    def _write_bool(self, data, value: bool) -> None:
        ctypes.cast(data, ctypes.POINTER(ctypes.c_bool))[0] = value

    def _write_string(self, data, value: ctypes.c_char_p) -> None:
        ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p))[0] = value

    def _get_variable(self, data) -> bool:
        var = ctypes.cast(data, ctypes.POINTER(retro_variable)).contents
        if not var.key:
            return False
        key = var.key.split(b";", 1)[0]
        value = self.variables.get(key)
        if value is None:
            return False
        holder = ctypes.c_char_p(value)
        self._variable_ptrs.append(holder)
        var.value = holder
        return True

    def _set_variables(self, data) -> None:
        variables = ctypes.cast(data, ctypes.POINTER(retro_variable))
        index = 0
        while variables[index].key:
            raw_key = variables[index].key
            raw_value = variables[index].value or b""
            if b";" in raw_key:
                key = raw_key.split(b";", 1)[0].strip()
                default = raw_value.split(b"|", 1)[0].strip()
            elif b";" in raw_value:
                key = raw_key
                default = raw_value.split(b";", 1)[1].split(b"|", 1)[0].strip()
            else:
                key = raw_key
                default = raw_value.split(b"|", 1)[0].strip()
            if key not in self.variables and default:
                self.variables[key] = default
            index += 1
            if index > 512:
                break
