"""An OpenGL framebuffer a core can draw into.

GameCube and Wii render on the GPU. This host keeps a hidden window, an
OpenGL 3.3 context, and a color buffer, then copies the picture back for
the window. No Nintendo system files are involved.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

GL_COLOR_BUFFER_BIT = 0x4000
GL_RGBA = 0x1908
GL_BGRA = 0x80E1
GL_UNSIGNED_BYTE = 0x1401
GL_TEXTURE_2D = 0x0DE1
GL_RGBA8 = 0x8058
GL_DEPTH24_STENCIL8 = 0x88F0
GL_FRAMEBUFFER = 0x8D40
GL_COLOR_ATTACHMENT0 = 0x8CE0
GL_DEPTH_STENCIL_ATTACHMENT = 0x821A
GL_RENDERBUFFER = 0x8D41
_PFD_FLAGS = 0x25
_PROFILE_CORE = 0x1
_PROFILE_COMPAT = 0x2


class GlError(Exception):
    pass


_WNDPROC = None


def _window_proc(hwnd, msg, wparam, lparam):
    user = ctypes.WinDLL("user32")
    user.DefWindowProcW.restype = ctypes.c_ssize_t
    user.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    return user.DefWindowProcW(hwnd, msg, wparam, lparam)


def available() -> bool:
    try:
        ctypes.WinDLL("opengl32")
        return True
    except OSError:
        return False


class Host:
    def __init__(self) -> None:
        self.device = None
        self.bottom_left = True
        self.core_profile = True
        self._negotiate_destroy = None
        self._user32 = None
        self._gdi32 = None
        self._gl = None
        self._hwnd = None
        self._dc = None
        self._rc = None
        self._class = "PokemonGBGL"
        self._fbo = 0
        self._color = 0
        self._depth = 0
        self._width = 0
        self._height = 0
        self._fns: dict[str, ctypes.CFUNCTYPE] = {}
        self._fb_cb = ctypes.CFUNCTYPE(ctypes.c_uint64)(self._framebuffer)
        self._proc_cb = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p)(self._proc_address)

    def start(self) -> None:
        if self.device:
            return
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self._gl = ctypes.WinDLL("opengl32", use_last_error=True)
        self._bind_windows()
        self._open_window()
        self._create_context()
        self._load_gl()
        self._resize(1920, 1088)
        self.device = True

    def begin_frame(self) -> None:
        if self.device:
            self._make_current()

    def read_frame(self, width: int, height: int):
        if not self.device or width <= 0 or height <= 0:
            return None
        if width > self._width or height > self._height:
            self._resize(max(width, self._width), max(height, self._height))
        self._make_current()
        self._fns["glBindFramebuffer"](GL_FRAMEBUFFER, self._fbo)
        count = width * height
        raw = (ctypes.c_ubyte * (count * 4))()
        self._fns["glReadPixels"](0, 0, width, height, GL_BGRA, GL_UNSIGNED_BYTE, raw)
        pixels = bytearray(raw)
        if self.bottom_left:
            stride = width * 4
            rows = [pixels[y * stride:(y + 1) * stride] for y in range(height)]
            pixels = b"".join(reversed(rows))
        else:
            pixels = bytes(pixels)
        pixels = bytearray(pixels)
        pixels[3::4] = b"\xff" * count
        return bytes(pixels), width, height

    def self_test(self) -> bytes:
        self.start()
        self._make_current()
        self._fns["glBindFramebuffer"](GL_FRAMEBUFFER, self._fbo)
        clear = self._gl.glClear
        clear.argtypes = [ctypes.c_uint]
        color = self._gl.glClearColor
        color.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
        color(1, 0, 0, 1)
        clear(GL_COLOR_BUFFER_BIT)
        packed = self.read_frame(2, 2)
        if not packed:
            raise GlError("OpenGL did not return a picture.")
        return packed[0][:16]

    def close(self, _destroy=None) -> None:
        if self._fns and self._fbo:
            self._make_current()
            self._fns["glDeleteFramebuffers"](1, ctypes.byref(ctypes.c_uint(self._fbo)))
            self._fns["glDeleteTextures"](1, ctypes.byref(ctypes.c_uint(self._color)))
            self._fns["glDeleteRenderbuffers"](1, ctypes.byref(ctypes.c_uint(self._depth)))
        self._fbo = 0
        if self._gl is not None and self._rc:
            self._gl.wglMakeCurrent(None, None)
            self._gl.wglDeleteContext(self._rc)
        self._rc = None
        if self._user32 is not None and self._hwnd:
            self._user32.ReleaseDC(self._hwnd, self._dc)
            self._user32.DestroyWindow(self._hwnd)
        self._hwnd = None
        self._dc = None
        self.device = None

    def _framebuffer(self) -> int:
        return int(self._fbo)

    def _proc_address(self, name):
        if not name:
            return None
        symbol = name if isinstance(name, bytes) else str(name).encode()
        found = self._gl.wglGetProcAddress(symbol)
        if found:
            return found
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetProcAddress.restype = ctypes.c_void_p
        kernel.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
        return kernel.GetProcAddress(self._gl._handle, symbol)

    def _bind_windows(self) -> None:
        user, gdi, gl = self._user32, self._gdi32, self._gl
        user.CreateWindowExW.restype = wintypes.HWND
        user.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            ctypes.c_void_p,
        ]
        user.GetDC.restype = wintypes.HDC
        user.GetDC.argtypes = [wintypes.HWND]
        user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user.DestroyWindow.argtypes = [wintypes.HWND]
        user.DefWindowProcW.restype = ctypes.c_ssize_t
        user.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        gl.wglCreateContext.restype = ctypes.c_void_p
        gl.wglCreateContext.argtypes = [wintypes.HDC]
        gl.wglMakeCurrent.argtypes = [wintypes.HDC, ctypes.c_void_p]
        gl.wglGetProcAddress.restype = ctypes.c_void_p
        gl.wglGetProcAddress.argtypes = [ctypes.c_char_p]
        gl.wglDeleteContext.argtypes = [ctypes.c_void_p]
        gdi.ChoosePixelFormat.argtypes = [wintypes.HDC, ctypes.c_void_p]
        gdi.SetPixelFormat.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_void_p]

    def _open_window(self) -> None:
        user = self._user32
        global _WNDPROC
        proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )
        if _WNDPROC is None:
            _WNDPROC = proc_type(_window_proc)

        class _Class(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", proc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        instance = ctypes.WinDLL("kernel32").GetModuleHandleW(None)
        info = _Class()
        info.lpfnWndProc = _WNDPROC
        info.hInstance = instance
        info.lpszClassName = self._class
        user.RegisterClassW(ctypes.byref(info))
        self._hwnd = user.CreateWindowExW(
            0, self._class, "gl", 0, 0, 0, 16, 16, None, None, instance, None
        )
        if not self._hwnd:
            raise GlError("OpenGL window was not created.")
        self._dc = user.GetDC(self._hwnd)
        if not self._dc:
            raise GlError("OpenGL window has no drawing surface.")

    def _create_context(self) -> None:
        class _Format(ctypes.Structure):
            _fields_ = [
                ("nSize", wintypes.WORD),
                ("nVersion", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("iPixelType", wintypes.BYTE),
                ("cColorBits", wintypes.BYTE),
                ("cRedBits", wintypes.BYTE),
                ("cRedShift", wintypes.BYTE),
                ("cGreenBits", wintypes.BYTE),
                ("cGreenShift", wintypes.BYTE),
                ("cBlueBits", wintypes.BYTE),
                ("cBlueShift", wintypes.BYTE),
                ("cAlphaBits", wintypes.BYTE),
                ("cAlphaShift", wintypes.BYTE),
                ("cAccumBits", wintypes.BYTE),
                ("cAccumRedBits", wintypes.BYTE),
                ("cAccumGreenBits", wintypes.BYTE),
                ("cAccumBlueBits", wintypes.BYTE),
                ("cAccumAlphaBits", wintypes.BYTE),
                ("cDepthBits", wintypes.BYTE),
                ("cStencilBits", wintypes.BYTE),
                ("cAuxBuffers", wintypes.BYTE),
                ("iLayerType", wintypes.BYTE),
                ("bReserved", wintypes.BYTE),
                ("dwLayerMask", wintypes.DWORD),
                ("dwVisibleMask", wintypes.DWORD),
                ("dwDamageMask", wintypes.DWORD),
            ]

        desc = _Format()
        desc.nSize = ctypes.sizeof(desc)
        desc.nVersion = 1
        desc.dwFlags = _PFD_FLAGS
        desc.cColorBits = 32
        desc.cDepthBits = 24
        desc.cStencilBits = 8
        chosen = self._gdi32.ChoosePixelFormat(self._dc, ctypes.byref(desc))
        if not chosen or not self._gdi32.SetPixelFormat(self._dc, chosen, ctypes.byref(desc)):
            raise GlError("OpenGL pixel format was rejected.")
        legacy = self._gl.wglCreateContext(self._dc)
        if not legacy or not self._gl.wglMakeCurrent(self._dc, legacy):
            raise GlError("OpenGL context was not created.")
        create = self._gl.wglGetProcAddress(b"wglCreateContextAttribsARB")
        if not create:
            self._rc = legacy
            return
        maker = ctypes.WINFUNCTYPE(
            ctypes.c_void_p, wintypes.HDC, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)
        )(create)
        profile = _PROFILE_CORE if self.core_profile else _PROFILE_COMPAT
        attribs = (ctypes.c_int * 7)(0x2091, 3, 0x2092, 3, 0x9126, profile, 0)
        modern = maker(self._dc, None, attribs)
        if not modern:
            self._rc = legacy
            return
        self._gl.wglMakeCurrent(None, None)
        self._gl.wglDeleteContext(legacy)
        if not self._gl.wglMakeCurrent(self._dc, modern):
            raise GlError("OpenGL 3.3 context was not created.")
        self._rc = modern

    def _load_gl(self) -> None:
        specs = {
            "glGenFramebuffers": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            "glBindFramebuffer": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_uint),
            "glGenTextures": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            "glBindTexture": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_uint),
            "glTexImage2D": ctypes.CFUNCTYPE(
                None,
                ctypes.c_uint,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_void_p,
            ),
            "glTexParameteri": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_uint, ctypes.c_int),
            "glFramebufferTexture2D": ctypes.CFUNCTYPE(
                None, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int
            ),
            "glGenRenderbuffers": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            "glBindRenderbuffer": ctypes.CFUNCTYPE(None, ctypes.c_uint, ctypes.c_uint),
            "glRenderbufferStorage": ctypes.CFUNCTYPE(
                None, ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_int
            ),
            "glFramebufferRenderbuffer": ctypes.CFUNCTYPE(
                None, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint
            ),
            "glDeleteFramebuffers": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            "glDeleteTextures": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            "glDeleteRenderbuffers": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)),
            "glReadPixels": ctypes.CFUNCTYPE(
                None,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
                ctypes.c_uint,
                ctypes.c_void_p,
            ),
            "glViewport": ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int),
        }
        for name, prototype in specs.items():
            pointer = self._proc_address(name.encode())
            if not pointer:
                raise GlError(f"OpenGL is missing {name}.")
            self._fns[name] = prototype(pointer)

    def _resize(self, width: int, height: int) -> None:
        self._make_current()
        if self._fbo:
            self._fns["glDeleteFramebuffers"](1, ctypes.byref(ctypes.c_uint(self._fbo)))
            self._fns["glDeleteTextures"](1, ctypes.byref(ctypes.c_uint(self._color)))
            self._fns["glDeleteRenderbuffers"](1, ctypes.byref(ctypes.c_uint(self._depth)))
        fbo = ctypes.c_uint()
        color = ctypes.c_uint()
        depth = ctypes.c_uint()
        self._fns["glGenFramebuffers"](1, ctypes.byref(fbo))
        self._fns["glGenTextures"](1, ctypes.byref(color))
        self._fns["glBindTexture"](GL_TEXTURE_2D, color.value)
        self._fns["glTexImage2D"](GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        self._fns["glTexParameteri"](GL_TEXTURE_2D, 0x2801, 0x2600)
        self._fns["glTexParameteri"](GL_TEXTURE_2D, 0x2800, 0x2600)
        self._fns["glGenRenderbuffers"](1, ctypes.byref(depth))
        self._fns["glBindRenderbuffer"](GL_RENDERBUFFER, depth.value)
        self._fns["glRenderbufferStorage"](GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, width, height)
        self._fns["glBindFramebuffer"](GL_FRAMEBUFFER, fbo.value)
        self._fns["glFramebufferTexture2D"](GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, color.value, 0)
        self._fns["glFramebufferRenderbuffer"](
            GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT, GL_RENDERBUFFER, depth.value
        )
        self._fns["glViewport"](0, 0, width, height)
        self._fbo = int(fbo.value)
        self._color = int(color.value)
        self._depth = int(depth.value)
        self._width = width
        self._height = height

    def _make_current(self) -> None:
        if self._rc and not self._gl.wglMakeCurrent(self._dc, self._rc):
            raise GlError("OpenGL context could not be made current.")
