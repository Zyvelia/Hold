"""A Vulkan device the Switch core can draw into.

The core renders a picture on the GPU. This host copies that picture back
so the window can show it. No Nintendo system files are involved.
"""

from __future__ import annotations

import ctypes

VK_SUCCESS = 0
VK_API_1_1 = (1 << 22) | (1 << 12)
VK_QUEUE_GRAPHICS = 0x1
VK_QUEUE_COMPUTE = 0x2
VK_QUEUE_FAMILY_IGNORED = 0xFFFFFFFF
VK_FENCE_SIGNALED = 0x1
VK_STRUCTURE_APPLICATION = 0
VK_STRUCTURE_INSTANCE = 1
VK_STRUCTURE_DEVICE_QUEUE = 2
VK_STRUCTURE_DEVICE = 3
VK_STRUCTURE_SUBMIT = 4
VK_STRUCTURE_MEMORY_ALLOCATE = 5
VK_STRUCTURE_FENCE = 8
VK_STRUCTURE_BUFFER = 12
VK_STRUCTURE_IMAGE = 14
VK_STRUCTURE_IMAGE_VIEW = 15
VK_STRUCTURE_COMMAND_POOL = 39
VK_STRUCTURE_COMMAND_BUFFER_ALLOCATE = 40
VK_STRUCTURE_COMMAND_BUFFER_BEGIN = 42
VK_STRUCTURE_IMAGE_MEMORY_BARRIER = 45
VK_SHARING_EXCLUSIVE = 0
VK_IMAGE_2D = 1
VK_FORMAT_R8G8B8A8 = 37
VK_FORMAT_R8G8B8A8_SRGB = 43
VK_FORMAT_B8G8R8A8 = 44
VK_FORMAT_B8G8R8A8_SRGB = 50
VK_IMAGE_TILING_OPTIMAL = 0
VK_IMAGE_USAGE_TRANSFER_SRC = 0x1
VK_IMAGE_USAGE_TRANSFER_DST = 0x2
VK_IMAGE_LAYOUT_UNDEFINED = 0
VK_IMAGE_LAYOUT_GENERAL = 1
VK_IMAGE_LAYOUT_SHADER_READ = 5
VK_IMAGE_LAYOUT_TRANSFER_SRC = 6
VK_IMAGE_LAYOUT_TRANSFER_DST = 7
VK_SAMPLE_1 = 1
VK_BUFFER_TRANSFER_SRC = 0x1
VK_BUFFER_TRANSFER_DST = 0x2
VK_MEMORY_HOST_VISIBLE = 0x2
VK_MEMORY_HOST_COHERENT = 0x4
VK_MEMORY_DEVICE_LOCAL = 0x1
VK_COMMAND_POOL_RESET = 0x2
VK_COMMAND_ONE_TIME = 0x1
VK_PIPELINE_TOP = 0x1
VK_PIPELINE_TRANSFER = 0x1000
VK_PIPELINE_ALL = 0x10000
VK_ACCESS_MEMORY_READ = 0x8000
VK_ACCESS_MEMORY_WRITE = 0x10000
VK_ACCESS_TRANSFER_READ = 0x800
VK_ACCESS_TRANSFER_WRITE = 0x1000
VK_IMAGE_ASPECT_COLOR = 0x1
VK_WHOLE_SIZE = 0xFFFFFFFFFFFFFFFF
SYNC_COUNT = 3

_RGBA = {VK_FORMAT_R8G8B8A8, VK_FORMAT_R8G8B8A8_SRGB}


class VulkanError(RuntimeError):
    pass


def available() -> bool:
    try:
        ctypes.WinDLL("vulkan-1.dll")
    except OSError:
        return False
    return True


class _AppInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("pApplicationName", ctypes.c_char_p),
        ("applicationVersion", ctypes.c_uint32),
        ("pEngineName", ctypes.c_char_p),
        ("engineVersion", ctypes.c_uint32),
        ("apiVersion", ctypes.c_uint32),
    ]


class _InstanceInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.c_void_p),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.c_void_p),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.c_void_p),
    ]


class _QueueInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("queueFamilyIndex", ctypes.c_uint32),
        ("queueCount", ctypes.c_uint32),
        ("pQueuePriorities", ctypes.c_void_p),
    ]


class _DeviceInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("queueCreateInfoCount", ctypes.c_uint32),
        ("pQueueCreateInfos", ctypes.c_void_p),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.c_void_p),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.c_void_p),
        ("pEnabledFeatures", ctypes.c_void_p),
    ]


class _QueueFamily(ctypes.Structure):
    _fields_ = [
        ("queueFlags", ctypes.c_uint32),
        ("queueCount", ctypes.c_uint32),
        ("timestampValidBits", ctypes.c_uint32),
        ("granularity", ctypes.c_uint32 * 3),
    ]


class _Extent3(ctypes.Structure):
    _fields_ = [("width", ctypes.c_uint32), ("height", ctypes.c_uint32), ("depth", ctypes.c_uint32)]


class _ImageInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("imageType", ctypes.c_uint32),
        ("format", ctypes.c_uint32),
        ("extent", _Extent3),
        ("mipLevels", ctypes.c_uint32),
        ("arrayLayers", ctypes.c_uint32),
        ("samples", ctypes.c_uint32),
        ("tiling", ctypes.c_uint32),
        ("usage", ctypes.c_uint32),
        ("sharingMode", ctypes.c_uint32),
        ("queueFamilyIndexCount", ctypes.c_uint32),
        ("pQueueFamilyIndices", ctypes.c_void_p),
        ("initialLayout", ctypes.c_uint32),
    ]


class _BufferInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("size", ctypes.c_uint64),
        ("usage", ctypes.c_uint32),
        ("sharingMode", ctypes.c_uint32),
        ("queueFamilyIndexCount", ctypes.c_uint32),
        ("pQueueFamilyIndices", ctypes.c_void_p),
    ]


class _MemoryRequirements(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint64),
        ("alignment", ctypes.c_uint64),
        ("memoryTypeBits", ctypes.c_uint32),
    ]


class _MemoryAllocate(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("allocationSize", ctypes.c_uint64),
        ("memoryTypeIndex", ctypes.c_uint32),
    ]


class _MemType(ctypes.Structure):
    _fields_ = [("propertyFlags", ctypes.c_uint32), ("heapIndex", ctypes.c_uint32)]


class _MemHeap(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint64), ("flags", ctypes.c_uint32), ("_pad", ctypes.c_uint32)]


class _MemoryProperties(ctypes.Structure):
    _fields_ = [
        ("memoryTypeCount", ctypes.c_uint32),
        ("memoryTypes", _MemType * 32),
        ("memoryHeapCount", ctypes.c_uint32),
        ("memoryHeaps", _MemHeap * 16),
    ]


class _PoolInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("queueFamilyIndex", ctypes.c_uint32),
    ]


class _AllocateCmd(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("commandPool", ctypes.c_void_p),
        ("level", ctypes.c_uint32),
        ("commandBufferCount", ctypes.c_uint32),
    ]


class _BeginInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pInheritanceInfo", ctypes.c_void_p),
    ]


class _Subresource(ctypes.Structure):
    _fields_ = [
        ("aspectMask", ctypes.c_uint32),
        ("mipLevel", ctypes.c_uint32),
        ("baseArrayLayer", ctypes.c_uint32),
        ("layerCount", ctypes.c_uint32),
    ]


class _Offset3(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32), ("z", ctypes.c_int32)]


class _Copy(ctypes.Structure):
    _fields_ = [
        ("bufferOffset", ctypes.c_uint64),
        ("bufferRowLength", ctypes.c_uint32),
        ("bufferImageHeight", ctypes.c_uint32),
        ("imageSubresource", _Subresource),
        ("imageOffset", _Offset3),
        ("imageExtent", _Extent3),
    ]


class _Range(ctypes.Structure):
    _fields_ = [
        ("aspectMask", ctypes.c_uint32),
        ("baseMipLevel", ctypes.c_uint32),
        ("levelCount", ctypes.c_uint32),
        ("baseArrayLayer", ctypes.c_uint32),
        ("layerCount", ctypes.c_uint32),
    ]


class _Barrier(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("srcAccessMask", ctypes.c_uint32),
        ("dstAccessMask", ctypes.c_uint32),
        ("oldLayout", ctypes.c_uint32),
        ("newLayout", ctypes.c_uint32),
        ("srcQueueFamilyIndex", ctypes.c_uint32),
        ("dstQueueFamilyIndex", ctypes.c_uint32),
        ("image", ctypes.c_void_p),
        ("subresourceRange", _Range),
    ]


class _Submit(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("waitSemaphoreCount", ctypes.c_uint32),
        ("pWaitSemaphores", ctypes.c_void_p),
        ("pWaitDstStageMask", ctypes.c_void_p),
        ("commandBufferCount", ctypes.c_uint32),
        ("pCommandBuffers", ctypes.c_void_p),
        ("signalSemaphoreCount", ctypes.c_uint32),
        ("pSignalSemaphores", ctypes.c_void_p),
    ]


class _FenceInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
    ]


class _ImageViewInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("image", ctypes.c_void_p),
        ("viewType", ctypes.c_uint32),
        ("format", ctypes.c_uint32),
        ("components", ctypes.c_uint32 * 4),
        ("subresourceRange", _Range),
    ]


class VulkanContext(ctypes.Structure):
    _fields_ = [
        ("gpu", ctypes.c_void_p),
        ("device", ctypes.c_void_p),
        ("queue", ctypes.c_void_p),
        ("queue_family_index", ctypes.c_uint32),
        ("presentation_queue", ctypes.c_void_p),
        ("presentation_queue_family_index", ctypes.c_uint32),
    ]


class VulkanInterface(ctypes.Structure):
    _fields_ = [
        ("interface_type", ctypes.c_int),
        ("interface_version", ctypes.c_uint),
        ("handle", ctypes.c_void_p),
        ("instance", ctypes.c_void_p),
        ("gpu", ctypes.c_void_p),
        ("device", ctypes.c_void_p),
        ("get_device_proc_addr", ctypes.c_void_p),
        ("get_instance_proc_addr", ctypes.c_void_p),
        ("queue", ctypes.c_void_p),
        ("queue_index", ctypes.c_uint),
        ("set_image", ctypes.c_void_p),
        ("get_sync_index", ctypes.c_void_p),
        ("get_sync_index_mask", ctypes.c_void_p),
        ("set_command_buffers", ctypes.c_void_p),
        ("wait_sync_index", ctypes.c_void_p),
        ("lock_queue", ctypes.c_void_p),
        ("unlock_queue", ctypes.c_void_p),
        ("set_signal_semaphore", ctypes.c_void_p),
    ]


def _check(result: int, what: str) -> None:
    if result != VK_SUCCESS:
        raise VulkanError(f"Vulkan {what} failed ({result}).")


def _proc(address, restype, *argtypes):
    if not address:
        raise VulkanError("A Vulkan entry point is missing.")
    function = ctypes.CFUNCTYPE(restype, *argtypes)(address)
    return function


class Host:
    """One Vulkan device and a CPU copy of the latest frame."""

    def __init__(self) -> None:
        self.instance = None
        self.device = None
        self.gpu = None
        self.queue = None
        self.queue_index = 0
        self.sync_index = 0
        self._frames = 0
        self._loader = None
        self._get_instance_proc = None
        self._fns: dict = {}
        self._kept: list = []
        self._owns_device = False
        self._pool = None
        self._cmd = None
        self._fences: list = []
        self._iface = VulkanInterface()
        self._handle_box = ctypes.c_int(1)
        self._lock = __import__("threading").Lock()
        self._image = None
        self._layout = VK_IMAGE_LAYOUT_GENERAL
        self._format = VK_FORMAT_B8G8R8A8
        self._waits: list[int] = []
        self._signal = None
        self._cmds: list[int] = []
        self._src_family = VK_QUEUE_FAMILY_IGNORED
        self._read_buffer = None
        self._read_memory = None
        self._read_size = 0
        self._negotiate_get_app = None
        self._negotiate_create_device = None
        self._negotiate_destroy = None
        self._negotiate_create_instance = None
        self._negotiate_create_device2 = None
        self._negotiate_version = 0
        self._wrapper_instance = None
        self._wrapper_device = None
        self.frame = None

    def remember_negotiation(self, version: int, get_app, create_device, destroy, create_instance, create_device2) -> None:
        self._negotiate_version = version
        self._negotiate_get_app = get_app
        self._negotiate_create_device = create_device
        self._negotiate_destroy = destroy
        self._negotiate_create_instance = create_instance if version >= 2 else None
        self._negotiate_create_device2 = create_device2 if version >= 2 else None

    def start(self) -> None:
        if self.device:
            return
        self._load_loader()
        self._wrapper_instance = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(self._on_create_instance)
        self._wrapper_device = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(self._on_create_device)
        self._kept.extend((self._wrapper_instance, self._wrapper_device))
        if self._negotiate_create_instance:
            creator = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )(self._negotiate_create_instance)
            self._kept.append(creator)
            self.instance = creator(
                self._get_instance_proc,
                self._application_info(),
                self._wrapper_instance,
                None,
            )
            if not self.instance:
                raise VulkanError("The core did not create a Vulkan instance.")
        else:
            self._create_instance()
        self._load_instance_functions()
        if self._negotiate_create_device2:
            self._call_create_device2()
        elif self._negotiate_create_device:
            self._call_create_device()
        else:
            self._create_device(self._pick_gpu())
            self._owns_device = True
        self._load_device_functions()
        self._create_sync()
        self._build_interface()

    def close(self, destroy_device_cb=None) -> None:
        if destroy_device_cb:
            ctypes.CFUNCTYPE(None)(destroy_device_cb)()
        if self.device and self._pool and self._fns.get("vkDestroyCommandPool"):
            self._fns["vkDestroyCommandPool"](self.device, self._pool, None)
            self._pool = None
        if self.device and self._read_buffer and self._fns.get("vkDestroyBuffer"):
            self._fns["vkDestroyBuffer"](self.device, self._read_buffer, None)
            self._read_buffer = None
        if self.device and self._read_memory and self._fns.get("vkFreeMemory"):
            self._fns["vkFreeMemory"](self.device, self._read_memory, None)
            self._read_memory = None
        for fence in self._fences:
            if self.device and self._fns.get("vkDestroyFence"):
                self._fns["vkDestroyFence"](self.device, fence, None)
        self._fences.clear()
        if self.device and self._owns_device and self._fns.get("vkDestroyDevice"):
            self._fns["vkDestroyDevice"](self.device, None)
        self.device = None
        if self.instance and self._fns.get("vkDestroyInstance"):
            self._fns["vkDestroyInstance"](self.instance, None)
        self.instance = None

    def begin_frame(self) -> None:
        if self._frames:
            self.sync_index = (self.sync_index + 1) % SYNC_COUNT
        self._frames += 1
        self._cmds = []
        self._waits = []
        self._signal = None

    def set_image(self, image_ptr, semaphore_count: int, semaphores_ptr, src_family: int) -> None:
        # retro_vulkan_image embeds VkImageViewCreateInfo. The image handle
        # sits 24 bytes into that embedded struct, which itself starts at byte 16.
        address = int(image_ptr)
        info = address + 16
        self._layout = _u32(address, 8)
        self._image = _u64(info, 24)
        self._format = _u32(info, 36)
        self._src_family = int(src_family)
        self._waits = []
        if semaphore_count and semaphores_ptr:
            array = ctypes.cast(semaphores_ptr, ctypes.POINTER(ctypes.c_uint64))
            self._waits = [int(array[index]) for index in range(int(semaphore_count))]

    def set_command_buffers(self, count: int, pointer) -> None:
        self._cmds = []
        if count and pointer:
            array = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))
            self._cmds = [array[index] for index in range(int(count))]

    def set_signal(self, semaphore) -> None:
        self._signal = int(semaphore) if semaphore else None

    def wait_sync(self, index: int) -> None:
        if not self._fences:
            return
        fence = self._fences[int(index) % SYNC_COUNT]
        result = self._fns["vkWaitForFences"](self.device, 1, ctypes.byref(ctypes.c_void_p(fence)), 1, VK_WHOLE_SIZE)
        _check(result, "wait")

    def read_frame(self, width: int, height: int):
        if not self._image or width <= 0 or height <= 0:
            return None
        self._ensure_readback(width * height * 4)
        self._record_download(width, height)
        self._submit(self._cmds + [self._cmd])
        self._wait_current()
        raw = self._map_copy(width * height * 4)
        self._image = None
        return _pack_pixels(raw, width, height, self._format)

    def self_test(self) -> bytes:
        """Upload four red pixels and read them back through the same copy path."""
        self._load_loader()
        self._create_instance()
        self._load_instance_functions()
        self._create_device(self._pick_gpu())
        self._owns_device = True
        self._load_device_functions()
        self._create_sync()
        width, height = 2, 2
        red = bytes([255, 0, 0, 255]) * (width * height)
        upload = self._stage_buffer(red, VK_BUFFER_TRANSFER_SRC)
        image, image_memory = self._make_image(width, height)
        self._ensure_readback(len(red))
        self._record_roundtrip(upload[0], image, width, height)
        self._submit([self._cmd])
        self._wait_current()
        raw = self._map_copy(len(red))
        self._fns["vkDestroyBuffer"](self.device, upload[0], None)
        self._fns["vkFreeMemory"](self.device, upload[1], None)
        self._fns["vkDestroyImage"](self.device, image, None)
        self._fns["vkFreeMemory"](self.device, image_memory, None)
        return raw

    def fill_interface(self, destination) -> None:
        ctypes.memmove(destination, ctypes.byref(self._iface), ctypes.sizeof(self._iface))

    def _application_info(self):
        if self._negotiate_get_app:
            getter = ctypes.CFUNCTYPE(ctypes.c_void_p)(self._negotiate_get_app)
            self._kept.append(getter)
            found = getter()
            if found:
                return found
        info = _AppInfo()
        info.sType = VK_STRUCTURE_APPLICATION
        info.pApplicationName = b"Pokemon"
        info.applicationVersion = 1
        info.pEngineName = b"Pokemon"
        info.engineVersion = 1
        info.apiVersion = VK_API_1_1
        self._kept.append(info)
        return ctypes.addressof(info)

    def _on_create_instance(self, _opaque, create_info):
        instance = ctypes.c_void_p()
        result = self._fns["vkCreateInstance"](create_info, None, ctypes.byref(instance))
        if result != VK_SUCCESS:
            return None
        self.instance = instance.value
        return self.instance

    def _on_create_device(self, gpu, _opaque, create_info):
        device = ctypes.c_void_p()
        result = self._fns["vkCreateDevice"](gpu, create_info, None, ctypes.byref(device))
        if result != VK_SUCCESS:
            return None
        self.device = device.value
        self.gpu = gpu
        self._owns_device = True
        return self.device

    def _load_loader(self) -> None:
        try:
            self._loader = ctypes.WinDLL("vulkan-1.dll")
        except OSError as exc:
            raise VulkanError("Vulkan is not available. Switch games draw on the GPU.") from exc
        getter = self._loader.vkGetInstanceProcAddr
        getter.restype = ctypes.c_void_p
        getter.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self._get_instance_proc = ctypes.cast(getter, ctypes.c_void_p).value
        self._fns["vkCreateInstance"] = _proc(
            getter(None, b"vkCreateInstance"),
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        )
        self._kept.append(self._fns["vkCreateInstance"])

    def _create_instance(self) -> None:
        app = self._application_info()
        info = _InstanceInfo()
        info.sType = VK_STRUCTURE_INSTANCE
        info.pApplicationInfo = app if isinstance(app, int) else ctypes.addressof(app)
        instance = ctypes.c_void_p()
        _check(self._fns["vkCreateInstance"](ctypes.byref(info), None, ctypes.byref(instance)), "instance")
        self.instance = instance.value
        self._kept.append(info)

    def _load_instance_functions(self) -> None:
        resolve = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)(self._get_instance_proc)
        self._kept.append(resolve)
        names = {
            "vkDestroyInstance": (None, ctypes.c_void_p, ctypes.c_void_p),
            "vkEnumeratePhysicalDevices": (
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.c_void_p,
            ),
            "vkGetPhysicalDeviceQueueFamilyProperties": (
                None,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.c_void_p,
            ),
            "vkCreateDevice": (
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            ),
            "vkGetPhysicalDeviceMemoryProperties": (None, ctypes.c_void_p, ctypes.c_void_p),
            "vkGetDeviceProcAddr": (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p),
        }
        for name, types in names.items():
            address = resolve(self.instance, name.encode())
            self._fns[name] = _proc(address, types[0], *types[1:])
            self._kept.append(self._fns[name])

    def _pick_gpu(self):
        count = ctypes.c_uint32(0)
        _check(self._fns["vkEnumeratePhysicalDevices"](self.instance, ctypes.byref(count), None), "devices")
        if not count.value:
            raise VulkanError("No Vulkan device is available.")
        devices = (ctypes.c_void_p * count.value)()
        _check(
            self._fns["vkEnumeratePhysicalDevices"](self.instance, ctypes.byref(count), devices),
            "devices",
        )
        return devices[0]

    def _family(self, gpu) -> int:
        count = ctypes.c_uint32(0)
        self._fns["vkGetPhysicalDeviceQueueFamilyProperties"](gpu, ctypes.byref(count), None)
        families = (_QueueFamily * count.value)()
        self._fns["vkGetPhysicalDeviceQueueFamilyProperties"](gpu, ctypes.byref(count), families)
        for index, family in enumerate(families):
            if family.queueFlags & VK_QUEUE_GRAPHICS and family.queueFlags & VK_QUEUE_COMPUTE:
                return index
        for index, family in enumerate(families):
            if family.queueFlags & VK_QUEUE_GRAPHICS:
                return index
        raise VulkanError("The Vulkan device has no graphics queue.")

    def _create_device(self, gpu) -> None:
        self.gpu = gpu
        self.queue_index = self._family(gpu)
        priority = ctypes.c_float(1.0)
        queue = _QueueInfo()
        queue.sType = VK_STRUCTURE_DEVICE_QUEUE
        queue.queueFamilyIndex = self.queue_index
        queue.queueCount = 1
        queue.pQueuePriorities = ctypes.addressof(priority)
        info = _DeviceInfo()
        info.sType = VK_STRUCTURE_DEVICE
        info.queueCreateInfoCount = 1
        info.pQueueCreateInfos = ctypes.addressof(queue)
        device = ctypes.c_void_p()
        _check(self._fns["vkCreateDevice"](gpu, ctypes.byref(info), None, ctypes.byref(device)), "device")
        self.device = device.value
        self._kept.extend((priority, queue, info))

    def _call_create_device2(self) -> None:
        creator = ctypes.CFUNCTYPE(
            ctypes.c_bool,
            ctypes.POINTER(VulkanContext),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(self._negotiate_create_device2)
        self._kept.append(creator)
        context = VulkanContext()
        ok = creator(
            ctypes.byref(context),
            self.instance,
            self._pick_gpu(),
            None,
            self._get_instance_proc,
            self._wrapper_device,
            None,
        )
        if not ok:
            context = VulkanContext()
            ok = creator(
                ctypes.byref(context),
                self.instance,
                None,
                None,
                self._get_instance_proc,
                self._wrapper_device,
                None,
            )
        if not ok or not context.device:
            raise VulkanError("The core did not create a Vulkan device.")
        self.device = context.device
        self.gpu = context.gpu
        self.queue = context.queue
        self.queue_index = int(context.queue_family_index)
        self._owns_device = True

    def _call_create_device(self) -> None:
        creator = ctypes.CFUNCTYPE(
            ctypes.c_bool,
            ctypes.POINTER(VulkanContext),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
        )(self._negotiate_create_device)
        self._kept.append(creator)
        context = VulkanContext()
        ok = creator(
            ctypes.byref(context),
            self.instance,
            self._pick_gpu(),
            None,
            self._get_instance_proc,
            None,
            0,
            None,
            0,
            None,
        )
        if not ok or not context.device:
            raise VulkanError("The core did not create a Vulkan device.")
        self.device = context.device
        self.gpu = context.gpu
        self.queue = context.queue
        self.queue_index = int(context.queue_family_index)
        self._owns_device = True

    def _load_device_functions(self) -> None:
        getter = self._fns["vkGetDeviceProcAddr"]
        wanted = [
            ("vkDestroyDevice", None, ctypes.c_void_p, ctypes.c_void_p),
            ("vkGetDeviceQueue", None, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)),
            ("vkCreateCommandPool", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
            ("vkDestroyCommandPool", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
            ("vkAllocateCommandBuffers", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
            ("vkBeginCommandBuffer", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p),
            ("vkEndCommandBuffer", ctypes.c_int, ctypes.c_void_p),
            ("vkResetCommandBuffer", ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32),
            ("vkCmdPipelineBarrier", None, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p),
            ("vkCmdCopyImageToBuffer", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p),
            ("vkCmdCopyBufferToImage", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p),
            ("vkCreateBuffer", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
            ("vkDestroyBuffer", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
            ("vkGetBufferMemoryRequirements", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
            ("vkAllocateMemory", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
            ("vkFreeMemory", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
            ("vkBindBufferMemory", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64),
            ("vkMapMemory", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)),
            ("vkUnmapMemory", None, ctypes.c_void_p, ctypes.c_void_p),
            ("vkCreateImage", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
            ("vkDestroyImage", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
            ("vkGetImageMemoryRequirements", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
            ("vkBindImageMemory", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64),
            ("vkCreateFence", ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
            ("vkDestroyFence", None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
            ("vkResetFences", ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p),
            ("vkWaitForFences", ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint64),
            ("vkQueueSubmit", ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p),
            ("vkQueueWaitIdle", ctypes.c_int, ctypes.c_void_p),
            ("vkDeviceWaitIdle", ctypes.c_int, ctypes.c_void_p),
        ]
        for name, restype, *argtypes in wanted:
            address = getter(self.device, name.encode())
            self._fns[name] = _proc(address, restype, *argtypes)
            self._kept.append(self._fns[name])
        if self.queue is None:
            queue = ctypes.c_void_p()
            self._fns["vkGetDeviceQueue"](self.device, self.queue_index, 0, ctypes.byref(queue))
            self.queue = queue.value

    def _create_sync(self) -> None:
        pool = _PoolInfo()
        pool.sType = VK_STRUCTURE_COMMAND_POOL
        pool.flags = VK_COMMAND_POOL_RESET
        pool.queueFamilyIndex = self.queue_index
        handle = ctypes.c_void_p()
        _check(self._fns["vkCreateCommandPool"](self.device, ctypes.byref(pool), None, ctypes.byref(handle)), "command pool")
        self._pool = handle.value
        alloc = _AllocateCmd()
        alloc.sType = VK_STRUCTURE_COMMAND_BUFFER_ALLOCATE
        alloc.commandPool = self._pool
        alloc.level = 0
        alloc.commandBufferCount = 1
        cmd = ctypes.c_void_p()
        _check(self._fns["vkAllocateCommandBuffers"](self.device, ctypes.byref(alloc), ctypes.byref(cmd)), "command buffer")
        self._cmd = cmd.value
        self._kept.extend((pool, alloc))
        for _ in range(SYNC_COUNT):
            info = _FenceInfo()
            info.sType = VK_STRUCTURE_FENCE
            info.flags = VK_FENCE_SIGNALED
            fence = ctypes.c_void_p()
            _check(self._fns["vkCreateFence"](self.device, ctypes.byref(info), None, ctypes.byref(fence)), "fence")
            self._fences.append(fence.value)
            self._kept.append(info)

    def _build_interface(self) -> None:
        callbacks = {
            "set_image": ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32)(self._cb_image),
            "get_sync_index": ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)(self._cb_sync),
            "get_sync_index_mask": ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)(self._cb_mask),
            "set_command_buffers": ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)(self._cb_cmds),
            "wait_sync_index": ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self._cb_wait),
            "lock_queue": ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self._cb_lock),
            "unlock_queue": ctypes.CFUNCTYPE(None, ctypes.c_void_p)(self._cb_unlock),
            "set_signal_semaphore": ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint64)(self._cb_signal),
        }
        self._kept.extend(callbacks.values())
        iface = self._iface
        iface.interface_type = 0
        iface.interface_version = 5
        iface.handle = ctypes.addressof(self._handle_box)
        iface.instance = self.instance
        iface.gpu = self.gpu
        iface.device = self.device
        iface.get_device_proc_addr = ctypes.cast(self._fns["vkGetDeviceProcAddr"], ctypes.c_void_p).value
        iface.get_instance_proc_addr = self._get_instance_proc
        iface.queue = self.queue
        iface.queue_index = self.queue_index
        for name, callback in callbacks.items():
            setattr(iface, name, ctypes.cast(callback, ctypes.c_void_p).value)

    def _cb_image(self, _handle, image, count, semaphores, src_family) -> None:
        self.set_image(image, count, semaphores, src_family)

    def _cb_sync(self, _handle) -> int:
        return self.sync_index

    def _cb_mask(self, _handle) -> int:
        return (1 << SYNC_COUNT) - 1

    def _cb_cmds(self, _handle, count, pointer) -> None:
        self.set_command_buffers(count, pointer)

    def _cb_wait(self, _handle) -> None:
        self.wait_sync(self.sync_index)

    def _cb_lock(self, _handle) -> None:
        self._lock.acquire()

    def _cb_unlock(self, _handle) -> None:
        self._lock.release()

    def _cb_signal(self, _handle, semaphore) -> None:
        self.set_signal(semaphore)

    def _memory_type(self, bits: int, flags: int) -> int:
        props = _MemoryProperties()
        self._fns["vkGetPhysicalDeviceMemoryProperties"](self.gpu, ctypes.byref(props))
        fallback = None
        for index in range(int(props.memoryTypeCount)):
            if not bits & (1 << index):
                continue
            fallback = index if fallback is None else fallback
            if (props.memoryTypes[index].propertyFlags & flags) == flags:
                return index
        if fallback is None:
            raise VulkanError("The Vulkan device has no suitable memory.")
        return fallback

    def _bind(self, kind: str, handle, flags: int):
        reqs = _MemoryRequirements()
        if kind == "buffer":
            self._fns["vkGetBufferMemoryRequirements"](self.device, handle, ctypes.byref(reqs))
        else:
            self._fns["vkGetImageMemoryRequirements"](self.device, handle, ctypes.byref(reqs))
        alloc = _MemoryAllocate()
        alloc.sType = VK_STRUCTURE_MEMORY_ALLOCATE
        alloc.allocationSize = reqs.size
        alloc.memoryTypeIndex = self._memory_type(reqs.memoryTypeBits, flags)
        memory = ctypes.c_void_p()
        _check(self._fns["vkAllocateMemory"](self.device, ctypes.byref(alloc), None, ctypes.byref(memory)), "memory")
        if kind == "buffer":
            _check(self._fns["vkBindBufferMemory"](self.device, handle, memory, 0), "bind buffer")
        else:
            _check(self._fns["vkBindImageMemory"](self.device, handle, memory, 0), "bind image")
        self._kept.append(alloc)
        return memory.value

    def _stage_buffer(self, payload: bytes, usage: int):
        info = _BufferInfo()
        info.sType = VK_STRUCTURE_BUFFER
        info.size = len(payload)
        info.usage = usage
        info.sharingMode = VK_SHARING_EXCLUSIVE
        handle = ctypes.c_void_p()
        _check(self._fns["vkCreateBuffer"](self.device, ctypes.byref(info), None, ctypes.byref(handle)), "buffer")
        memory = self._bind("buffer", handle.value, VK_MEMORY_HOST_VISIBLE | VK_MEMORY_HOST_COHERENT)
        pointer = ctypes.c_void_p()
        _check(self._fns["vkMapMemory"](self.device, memory, 0, len(payload), 0, ctypes.byref(pointer)), "map")
        ctypes.memmove(pointer, payload, len(payload))
        self._fns["vkUnmapMemory"](self.device, memory)
        self._kept.append(info)
        return handle.value, memory

    def _make_image(self, width: int, height: int):
        info = _ImageInfo()
        info.sType = VK_STRUCTURE_IMAGE
        info.imageType = VK_IMAGE_2D
        info.format = VK_FORMAT_R8G8B8A8
        info.extent = _Extent3(width, height, 1)
        info.mipLevels = 1
        info.arrayLayers = 1
        info.samples = VK_SAMPLE_1
        info.tiling = VK_IMAGE_TILING_OPTIMAL
        info.usage = VK_IMAGE_USAGE_TRANSFER_SRC | VK_IMAGE_USAGE_TRANSFER_DST
        info.sharingMode = VK_SHARING_EXCLUSIVE
        info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED
        handle = ctypes.c_void_p()
        _check(self._fns["vkCreateImage"](self.device, ctypes.byref(info), None, ctypes.byref(handle)), "image")
        memory = self._bind("image", handle.value, VK_MEMORY_DEVICE_LOCAL)
        self._kept.append(info)
        return handle.value, memory

    def _ensure_readback(self, size: int) -> None:
        if self._read_buffer and self._read_size >= size:
            return
        if self._read_buffer:
            self._fns["vkDestroyBuffer"](self.device, self._read_buffer, None)
            self._fns["vkFreeMemory"](self.device, self._read_memory, None)
        info = _BufferInfo()
        info.sType = VK_STRUCTURE_BUFFER
        info.size = size
        info.usage = VK_BUFFER_TRANSFER_DST
        info.sharingMode = VK_SHARING_EXCLUSIVE
        handle = ctypes.c_void_p()
        _check(self._fns["vkCreateBuffer"](self.device, ctypes.byref(info), None, ctypes.byref(handle)), "readback")
        self._read_buffer = handle.value
        self._read_memory = self._bind("buffer", handle.value, VK_MEMORY_HOST_VISIBLE | VK_MEMORY_HOST_COHERENT)
        self._read_size = size
        self._kept.append(info)

    def _begin_cmd(self):
        _check(self._fns["vkResetCommandBuffer"](self._cmd, 0), "reset command")
        begin = _BeginInfo()
        begin.sType = VK_STRUCTURE_COMMAND_BUFFER_BEGIN
        begin.flags = VK_COMMAND_ONE_TIME
        _check(self._fns["vkBeginCommandBuffer"](self._cmd, ctypes.byref(begin)), "begin command")
        self._kept.append(begin)
        return begin

    def _barrier(self, image, old: int, new: int, src_access: int, dst_access: int, src_stage: int, dst_stage: int) -> None:
        barrier = _Barrier()
        barrier.sType = VK_STRUCTURE_IMAGE_MEMORY_BARRIER
        barrier.srcAccessMask = src_access
        barrier.dstAccessMask = dst_access
        barrier.oldLayout = old
        barrier.newLayout = new
        barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED
        barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED
        barrier.image = image
        barrier.subresourceRange = _Range(VK_IMAGE_ASPECT_COLOR, 0, 1, 0, 1)
        self._fns["vkCmdPipelineBarrier"](
            self._cmd, src_stage, dst_stage, 0, 0, None, 0, None, 1, ctypes.byref(barrier)
        )
        self._kept.append(barrier)

    def _region(self, width: int, height: int) -> _Copy:
        region = _Copy()
        region.imageSubresource = _Subresource(VK_IMAGE_ASPECT_COLOR, 0, 0, 1)
        region.imageExtent = _Extent3(width, height, 1)
        self._kept.append(region)
        return region

    def _record_roundtrip(self, source, image, width: int, height: int) -> None:
        self._begin_cmd()
        self._barrier(image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST, 0, VK_ACCESS_TRANSFER_WRITE, VK_PIPELINE_TOP, VK_PIPELINE_TRANSFER)
        region = self._region(width, height)
        self._fns["vkCmdCopyBufferToImage"](self._cmd, source, image, VK_IMAGE_LAYOUT_TRANSFER_DST, 1, ctypes.byref(region))
        self._barrier(
            image,
            VK_IMAGE_LAYOUT_TRANSFER_DST,
            VK_IMAGE_LAYOUT_TRANSFER_SRC,
            VK_ACCESS_TRANSFER_WRITE,
            VK_ACCESS_TRANSFER_READ,
            VK_PIPELINE_TRANSFER,
            VK_PIPELINE_TRANSFER,
        )
        region = self._region(width, height)
        self._fns["vkCmdCopyImageToBuffer"](self._cmd, image, VK_IMAGE_LAYOUT_TRANSFER_SRC, self._read_buffer, 1, ctypes.byref(region))
        _check(self._fns["vkEndCommandBuffer"](self._cmd), "end command")

    def _record_download(self, width: int, height: int) -> None:
        self._begin_cmd()
        self._barrier(
            self._image,
            self._layout,
            VK_IMAGE_LAYOUT_TRANSFER_SRC,
            VK_ACCESS_MEMORY_READ | VK_ACCESS_MEMORY_WRITE,
            VK_ACCESS_TRANSFER_READ,
            VK_PIPELINE_ALL,
            VK_PIPELINE_TRANSFER,
        )
        region = self._region(width, height)
        self._fns["vkCmdCopyImageToBuffer"](
            self._cmd, self._image, VK_IMAGE_LAYOUT_TRANSFER_SRC, self._read_buffer, 1, ctypes.byref(region)
        )
        self._barrier(
            self._image,
            VK_IMAGE_LAYOUT_TRANSFER_SRC,
            self._layout if self._layout not in (VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_SRC) else VK_IMAGE_LAYOUT_GENERAL,
            VK_ACCESS_TRANSFER_READ,
            VK_ACCESS_MEMORY_READ | VK_ACCESS_MEMORY_WRITE,
            VK_PIPELINE_TRANSFER,
            VK_PIPELINE_ALL,
        )
        _check(self._fns["vkEndCommandBuffer"](self._cmd), "end command")

    def _submit(self, commands: list) -> None:
        buffers = (ctypes.c_void_p * len(commands))(*commands)
        waits = (ctypes.c_uint64 * len(self._waits))(*self._waits) if self._waits else None
        stages = (ctypes.c_uint32 * len(self._waits))(*([VK_PIPELINE_TRANSFER] * len(self._waits))) if self._waits else None
        signals = None
        signal_count = 0
        if self._signal:
            signals = (ctypes.c_uint64 * 1)(self._signal)
            signal_count = 1
        submit = _Submit()
        submit.sType = VK_STRUCTURE_SUBMIT
        submit.waitSemaphoreCount = len(self._waits)
        submit.pWaitSemaphores = ctypes.addressof(waits) if waits is not None else None
        submit.pWaitDstStageMask = ctypes.addressof(stages) if stages is not None else None
        submit.commandBufferCount = len(commands)
        submit.pCommandBuffers = ctypes.addressof(buffers)
        submit.signalSemaphoreCount = signal_count
        submit.pSignalSemaphores = ctypes.addressof(signals) if signals is not None else None
        fence = self._fences[self.sync_index]
        with self._lock:
            _check(self._fns["vkResetFences"](self.device, 1, ctypes.byref(ctypes.c_void_p(fence))), "reset fence")
            _check(self._fns["vkQueueSubmit"](self.queue, 1, ctypes.byref(submit), fence), "submit")
        self._kept.extend((buffers, submit))
        if waits is not None:
            self._kept.append(waits)
        if stages is not None:
            self._kept.append(stages)
        if signals is not None:
            self._kept.append(signals)

    def _wait_current(self) -> None:
        fence = self._fences[self.sync_index]
        _check(
            self._fns["vkWaitForFences"](self.device, 1, ctypes.byref(ctypes.c_void_p(fence)), 1, VK_WHOLE_SIZE),
            "wait",
        )

    def _map_copy(self, size: int) -> bytes:
        pointer = ctypes.c_void_p()
        _check(self._fns["vkMapMemory"](self.device, self._read_memory, 0, size, 0, ctypes.byref(pointer)), "map")
        data = ctypes.string_at(pointer, size)
        self._fns["vkUnmapMemory"](self.device, self._read_memory)
        return data


def _u32(address: int, offset: int) -> int:
    return ctypes.cast(address + offset, ctypes.POINTER(ctypes.c_uint32)).contents.value


def _u64(address: int, offset: int) -> int:
    return ctypes.cast(address + offset, ctypes.POINTER(ctypes.c_uint64)).contents.value


def _pack_pixels(raw: bytes, width: int, height: int, fmt: int) -> tuple[bytes, int, int]:
    count = width * height
    if fmt in _RGBA:
        try:
            import numpy as np

            pixels = np.frombuffer(raw, dtype=np.uint8, count=count * 4).reshape(-1, 4)
            ordered = pixels[:, [2, 1, 0]]
            packed = np.empty((count, 4), dtype=np.uint8)
            packed[:, 0:3] = ordered
            packed[:, 3] = 255
            return packed.tobytes(), width, height
        except Exception:
            pass
    out = bytearray(raw[: count * 4])
    out[3::4] = b"\xff" * count
    return bytes(out), width, height
