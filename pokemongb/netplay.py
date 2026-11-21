"""One other window shares inputs, or two Game Boys or GBAs share a link cable.

The host listens on port 5555. The other side joins with that computer's
address. The same game stays in step, and the joiner is player 2. Two Game
Boy games, or two Game Boy Advance games, keep their own controls and trade
bytes over the cable.
"""

from __future__ import annotations

import hashlib
import socket
import struct
import threading
import time

PACKET = struct.Struct("!II4hBB")
HELLO = struct.Struct("!8s8s")
HEAD = struct.Struct("!BH")
BEACON = struct.Struct("!4sHB48s")
BEACON_MAGIC = b"PGB1"
LOBBY_PORT = 5556
KIND_INPUT = 1
KIND_CHAT = 2
KIND_PING = 3
KIND_PONG = 4
KIND_SYNC = 5
KIND_STATE = 6
KIND_ALL = 7
NET_ACTIONS = (
    "up",
    "down",
    "left",
    "right",
    "a",
    "b",
    "y",
    "x",
    "start",
    "select",
    "l",
    "r",
    "zl",
    "zr",
    "mic",
    "swap",
    "rstick_up",
    "rstick_down",
    "rstick_left",
    "rstick_right",
)


class _Peer:
    def __init__(self, sock: socket.socket, seat: int, spectator: bool) -> None:
        self.sock = sock
        self.seat = seat
        self.spectator = spectator
        self.inbox: dict[int, bytes] = {}
        self.alive = True


def _full_packet(payload: bytes) -> bytes:
    if len(payload) == PACKET.size:
        return payload
    return b"\0\0\0\0" + payload


def _pack_seats(seats: dict[int, bytes]) -> bytes:
    out = bytearray()
    for seat, packet in sorted(seats.items()):
        out.append(seat & 0xFF)
        out += _full_packet(packet)
    return bytes(out)


def _unpack_seats(blob: bytes) -> dict[int, bytes]:
    seats: dict[int, bytes] = {}
    step = 1 + PACKET.size
    for offset in range(0, len(blob) - step + 1, step):
        seat = blob[offset]
        seats[seat] = blob[offset + 1:offset + step]
    return seats


class Link:
    def __init__(self) -> None:
        self.role = ""
        self.mode = ""
        self.ready = False
        self.error = ""
        self.frame = 0
        self.delay = 0
        self.password = ""
        self.room = b"\0" * 8
        self.ping_ms = 0
        self.token = b"\0" * 8
        self.kind = b"gb"
        self._sock: socket.socket | None = None
        self._server: socket.socket | None = None
        self._serving = False
        self._alive = False
        self._inbox: dict[int, bytes] = {}
        self.chat: list[str] = []
        self.sync: list[tuple[int, bytes]] = []
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._closed = False
        self._guest_seen = False
        self._epoch = 0
        self.spectate = False
        self.spectating = False
        self.seat = 1
        self.want_state = False
        self.state_blob = b""
        self._state_parts: list[tuple[int, bytes]] = []
        self._peers: list[_Peer] = []
        self.crowd = False
        self.bundle: dict[int, bytes] = {}

    def set_game(self, token: bytes, kind: str) -> None:
        self.token = token[:8].ljust(8, b"\0")
        self.kind = kind.encode("ascii", "replace")[:8].ljust(8, b"\0")

    def host(self, port: int = 5555) -> int:
        self.close()
        self._closed = False
        self.role = "host"
        self.error = ""
        self._guest_seen = False
        self.room = hashlib.blake2s(str(time.time()).encode(), digest_size=8).digest()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", port))
        server.listen(8)
        server.settimeout(0.5)
        self._server = server
        self._serving = True
        threading.Thread(target=self._accept, name="net-host", daemon=True).start()
        return int(server.getsockname()[1])

    def join(self, host: str, port: int, relay: bool = False, spectate: bool = False) -> None:
        self.close()
        self._closed = False
        self.role = "guest"
        self.spectate = spectate
        self.error = ""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        if relay:
            mark = self._read_exact(sock, 2)
            if mark == b"R1":
                self.role = "host"
            elif mark == b"R2":
                self.role = "guest"
            else:
                sock.close()
                self._fail("That address is not a relay.")
                return
        self._shake(sock)

    def exchange(self, payload: bytes, wait: float = 0.12) -> bytes | None:
        """Trade this frame's input. None means the other side has not answered yet."""
        if not self.ready or self._sock is None:
            return None
        frame = self.frame
        delay = 0 if self.mode == "link" else max(0, min(8, int(self.delay)))
        blob = PACKET.pack(frame + delay, *self._fields(payload))
        if not self._send_frame(KIND_INPUT, blob):
            return None
        if delay and frame < delay:
            self.frame = frame + 1
            return pack_input(0, (0, 0, 0, 0), 0xFF, False)
        deadline = threading.Event()
        steps = 1 if wait <= 0 else max(1, int(wait / 0.002))
        for _ in range(steps):
            with self._lock:
                body = self._inbox.pop(frame, None)
            if body is not None:
                self.frame = frame + 1
                return body
            if wait <= 0:
                break
            deadline.wait(0.002)
        return None

    def advance(self) -> None:
        """Count a frame that ran on a predicted button."""
        self.frame += 1

    def take_late(self) -> list[tuple[int, bytes]]:
        """Buttons that arrived after the frame that needed them."""
        with self._lock:
            ready = sorted(frame for frame in self._inbox if frame < self.frame)
            return [(frame, self._inbox.pop(frame)) for frame in ready]

    def publish(self, host_packet: bytes) -> dict[int, bytes]:
        """Give every extra player and spectator the buttons gathered this frame."""
        if len(host_packet) != PACKET.size:
            host_packet = PACKET.pack(max(0, self.frame - 1), *self._fields(host_packet))
        seats = {1: host_packet}
        for peer in list(self._peers):
            if not peer.alive or peer.spectator or not peer.inbox:
                continue
            newest = max(peer.inbox)
            seats[peer.seat] = peer.inbox.pop(newest)
        blob = _pack_seats(seats)
        for peer in list(self._peers):
            if not peer.alive:
                continue
            self._send_on(peer.sock, KIND_INPUT, seats[1])
            self._send_on(peer.sock, KIND_ALL, blob)
        if self._sock is not None and (len(seats) > 2 or any(peer.spectator for peer in self._peers)):
            self._send_on(self._sock, KIND_ALL, blob)
            self.crowd = True
        return seats

    def take_bundle(self) -> dict[int, bytes]:
        with self._lock:
            found = dict(self.bundle)
            self.bundle.clear()
            return found

    def send_state(self, blob: bytes) -> None:
        """Send the host's moment so a joiner continues from that frame."""
        if not blob or len(blob) > 8_000_000:
            self.want_state = False
            return
        total = len(blob)
        offset = 0
        while offset < total:
            chunk = blob[offset:offset + 60000]
            payload = struct.pack("!II", offset, total) + chunk
            self._send_frame(KIND_STATE, payload)
            for peer in list(self._peers):
                if peer.alive:
                    self._send_on(peer.sock, KIND_STATE, payload)
            offset += len(chunk)
        self.want_state = False

    def take_state(self) -> bytes:
        blob = self.state_blob
        self.state_blob = b""
        return blob

    def close(self) -> None:
        self._closed = True
        self._serving = False
        self._alive = False
        self.ready = False
        self.frame = 0
        for sock in (self._sock, self._server):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self._sock = None
        self._server = None
        for peer in self._peers:
            peer.alive = False
            try:
                peer.sock.close()
            except OSError:
                pass
        self._peers.clear()
        with self._lock:
            self._inbox.clear()

    def _accept(self) -> None:
        server = self._server
        if server is None:
            return
        while self._serving:
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._serving = False
            self._shake(conn)
            return

    def _shake(self, sock: socket.socket) -> None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(5)
        try:
            hello_out = (
                b"HI"
                + HELLO.pack(self.token, self.kind)
                + bytes([self.delay & 0xFF])
                + self._pass_bytes()
                + (self.room or b"\0" * 8)
                + bytes([9 if self.spectate else 0])
            )
            sock.sendall(hello_out)
            hello = self._read_exact(sock, len(hello_out))
        except OSError:
            sock.close()
            self._fail("Could not reach the other side.")
            return
        if hello[:2] != b"HI":
            sock.close()
            self._fail("That address is not this emulator.")
            return
        token, kind = HELLO.unpack(hello[2:2 + HELLO.size])
        extra = hello[2 + HELLO.size:]
        their_delay = extra[0]
        their_pass = extra[1:9]
        their_room = extra[9:17]
        their_request = extra[17] if len(extra) > 17 else 0
        primary = self._sock is None
        if their_pass != self._pass_bytes():
            sock.close()
            if primary:
                self._fail("That password is wrong.")
            return
        if self.role == "guest" and their_room != b"\0" * 8:
            self.room = their_room
        elif self.role == "host" and their_room not in (b"\0" * 8, self.room):
            sock.close()
            if primary:
                self._fail("That room is closed.")
            return
        elif (
            self.role == "host"
            and their_room == b"\0" * 8
            and self._guest_seen
            and self._sock is None
        ):
            sock.close()
            if primary:
                self._fail("That room is closed.")
            return
        mine = self.kind.strip(b"\0")
        theirs = kind.strip(b"\0")
        same_game = token == self.token and mine == theirs
        if not primary:
            if not same_game and not (mine == theirs and mine in (b"gb", b"gba")):
                sock.close()
                return
        elif mine == theirs and mine in (b"gb", b"gba"):
            self.mode = "link"
        elif same_game:
            self.mode = "play"
        else:
            sock.close()
            self._fail("Open the same game on both sides.")
            return
        if primary:
            if self.mode == "play":
                self.delay = max(self.delay, min(8, int(their_delay)))
            else:
                self.delay = 0
        assigned = self._assign_seat(sock, their_request, primary)
        if assigned is None:
            return
        sock.settimeout(None)
        if not primary:
            peer = _Peer(sock, assigned, assigned == 9)
            self._peers.append(peer)
            self.want_state = True
            threading.Thread(target=self._read_peer, args=(peer,), name="net-peer", daemon=True).start()
            return
        self.seat = 1 if self.role == "host" else assigned
        self.spectating = assigned == 9
        self._sock = sock
        self._alive = True
        self.ready = True
        self.frame = 0
        if self.role == "host":
            self._guest_seen = True
            self.want_state = True
            threading.Thread(target=self._accept_more, name="net-more", daemon=True).start()
        threading.Thread(target=self._read, name="net-read", daemon=True).start()

    def _assign_seat(self, sock: socket.socket, request: int, primary: bool) -> int | None:
        if self.role != "host":
            try:
                assigned = self._read_exact(sock, 1)[0]
            except OSError:
                sock.close()
                self._fail("Could not reach the other side.")
                return None
            if assigned == 0:
                sock.close()
                self._fail("The room is full.")
                return None
            return assigned
        if request == 9:
            assigned = 9
        elif primary:
            assigned = 2
        else:
            used = {peer.seat for peer in self._peers}
            assigned = next((seat for seat in (3, 4) if seat not in used), 0)
        try:
            sock.sendall(bytes([assigned]))
        except OSError:
            sock.close()
            if primary:
                self._fail("Could not reach the other side.")
            return None
        if assigned == 0:
            sock.close()
            return None
        return assigned

    def _accept_more(self) -> None:
        epoch = self._epoch
        server = self._server
        if server is None:
            return
        while not self._closed and self._epoch == epoch and self._server is server:
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if self._epoch != epoch or self._closed:
                try:
                    conn.close()
                except OSError:
                    pass
                return
            self._shake(conn)

    def _read(self) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            while self._alive:
                kind, body = self._read_message(sock)
                if kind == KIND_INPUT and len(body) == PACKET.size:
                    frame = PACKET.unpack(body)[0]
                    with self._lock:
                        self._inbox[frame] = body
                        if len(self._inbox) > 24:
                            oldest = min(self._inbox)
                            self._inbox.pop(oldest, None)
                elif kind == KIND_CHAT:
                    text = body.decode("utf-8", errors="replace")
                    with self._lock:
                        self.chat.append(text)
                        if len(self.chat) > 40:
                            del self.chat[:-40]
                elif kind == KIND_PING:
                    self._send_frame(KIND_PONG, body)
                elif kind == KIND_PONG and len(body) == 8:
                    sent = struct.unpack("!d", body)[0]
                    self.ping_ms = max(0, int((time.perf_counter() - sent) * 1000))
                elif kind == KIND_SYNC and len(body) == 12:
                    frame, digest = struct.unpack("!I8s", body)
                    with self._lock:
                        self.sync.append((frame, digest))
                        if len(self.sync) > 8:
                            del self.sync[:-8]
                elif kind == KIND_ALL:
                    seats = _unpack_seats(body)
                    with self._lock:
                        self.bundle = seats
                        if len(seats) > 2:
                            self.crowd = True
                elif kind == KIND_STATE:
                    self._take_state_chunk(body)
        except OSError:
            if self._alive:
                self._fail("The other side disconnected.")

    def _read_message(self, sock: socket.socket) -> tuple[int, bytes]:
        kind, size = HEAD.unpack(self._read_exact(sock, HEAD.size))
        if size > 65535:
            raise OSError("too large")
        return int(kind), self._read_exact(sock, int(size))

    def _read_peer(self, peer: _Peer) -> None:
        try:
            while peer.alive and not self._closed:
                kind, body = self._read_message(peer.sock)
                if kind == KIND_INPUT and len(body) == PACKET.size:
                    frame = PACKET.unpack(body)[0]
                    peer.inbox[frame] = body
                    if len(peer.inbox) > 24:
                        peer.inbox.pop(min(peer.inbox), None)
        except OSError:
            peer.alive = False

    def _take_state_chunk(self, body: bytes) -> None:
        if len(body) < 8:
            return
        offset, total = struct.unpack("!II", body[:8])
        if total <= 0 or total > 8_000_000:
            return
        if offset == 0:
            self._state_parts.clear()
        self._state_parts.append((offset, body[8:]))
        have = sum(len(chunk) for _offset, chunk in self._state_parts)
        if have < total:
            return
        blob = b"".join(chunk for _offset, chunk in sorted(self._state_parts))
        self.state_blob = blob[:total]
        self._state_parts.clear()

    def _send_on(self, sock: socket.socket, kind: int, payload: bytes) -> bool:
        if len(payload) > 65535:
            return False
        try:
            with self._send_lock:
                sock.sendall(HEAD.pack(kind, len(payload)) + payload)
            return True
        except OSError:
            return False

    def _send_frame(self, kind: int, payload: bytes) -> bool:
        sock = self._sock
        if sock is None or len(payload) > 65535:
            return False
        try:
            with self._send_lock:
                sock.sendall(HEAD.pack(kind, len(payload)) + payload)
            return True
        except OSError:
            self._fail("The other side disconnected.")
            return False

    def _pass_bytes(self) -> bytes:
        text = (self.password or "").encode()
        if not text:
            return b"\0" * 8
        return hashlib.blake2s(text, digest_size=8).digest()

    def send_chat(self, text: str) -> None:
        clean = text.replace("\n", " ").strip()[:240]
        if clean:
            self._send_frame(KIND_CHAT, clean.encode("utf-8"))

    def take_chat(self) -> list[str]:
        with self._lock:
            items = list(self.chat)
            self.chat.clear()
            return items

    def ping(self) -> None:
        self._send_frame(KIND_PING, struct.pack("!d", time.perf_counter()))

    def send_sync(self, frame: int, digest: bytes) -> None:
        self._send_frame(KIND_SYNC, struct.pack("!I8s", frame & 0xFFFFFFFF, digest[:8].ljust(8, b"\0")))

    def take_sync(self) -> list[tuple[int, bytes]]:
        with self._lock:
            items = list(self.sync)
            self.sync.clear()
            return items

    def _read_exact(self, sock: socket.socket, size: int) -> bytes:
        blob = b""
        while len(blob) < size:
            chunk = sock.recv(size - len(blob))
            if not chunk:
                raise OSError("closed")
            blob += chunk
        return blob

    def _fields(self, payload: bytes) -> tuple:
        return PACKET.unpack(b"\0\0\0\0" + payload)[1:]

    def _fail(self, text: str) -> None:
        self.error = text
        self.ready = False
        was = self._alive
        self._alive = False
        self._epoch += 1
        for peer in self._peers:
            peer.alive = False
            try:
                peer.sock.close()
            except OSError:
                pass
        self._peers.clear()
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        with self._lock:
            self._inbox.clear()
        if self.role == "host" and self._server is not None and not self._closed:
            if was:
                self.error = "The other side disconnected. Waiting for them to come back."
            self._serving = True
            threading.Thread(target=self._accept, name="net-host", daemon=True).start()


def pack_input(bits: int, analog: tuple[int, int, int, int], sb: int, active: bool) -> bytes:
    body = PACKET.pack(0, bits & 0xFFFFFFFF, *analog, sb & 0xFF, 1 if active else 0)
    return body[4:]


def unpack_input(body: bytes) -> tuple[int, tuple[int, int, int, int], int, bool]:
    _frame, bits, lx, ly, rx, ry, sb, flags = PACKET.unpack(body if len(body) == PACKET.size else b"\0\0\0\0" + body)
    return bits, (lx, ly, rx, ry), sb, bool(flags)


def pack_beacon(port: int, title: str, password: bool, relay: bool) -> bytes:
    flags = (1 if password else 0) | (2 if relay else 0)
    name = title.encode("utf-8", errors="replace")[:48].ljust(48, b"\0")
    return BEACON.pack(BEACON_MAGIC, port & 0xFFFF, flags, name)


def parse_beacon(blob: bytes) -> dict | None:
    if len(blob) != BEACON.size:
        return None
    magic, port, flags, name = BEACON.unpack(blob)
    if magic != BEACON_MAGIC:
        return None
    title = name.split(b"\0", 1)[0].decode("utf-8", errors="replace") or "Game"
    return {
        "port": int(port),
        "title": title,
        "password": bool(flags & 1),
        "relay": bool(flags & 2),
    }


class Beacon:
    """Tell the local network that this computer is hosting or relaying."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, port: int, title: str, password: bool, relay: bool) -> None:
        self.stop()
        self._stop.clear()
        blob = pack_beacon(port, title, password, relay)

        def run() -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                while not self._stop.is_set():
                    for dest in (("255.255.255.255", LOBBY_PORT), ("127.0.0.1", LOBBY_PORT)):
                        try:
                            sock.sendto(blob, dest)
                        except OSError:
                            pass
                    if self._stop.wait(1.0):
                        break
            finally:
                sock.close()

        self._thread = threading.Thread(target=run, name="net-beacon", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def discover(seconds: float = 0.8) -> list[dict]:
    """Hosts and relays announcing themselves on this network."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", LOBBY_PORT))
    except OSError:
        sock.close()
        return []
    sock.settimeout(0.2)
    found: dict[tuple, dict] = {}
    deadline = time.perf_counter() + seconds
    try:
        while time.perf_counter() < deadline:
            try:
                blob, addr = sock.recvfrom(256)
            except TimeoutError:
                continue
            except OSError:
                break
            parsed = parse_beacon(blob)
            if parsed is None:
                continue
            parsed["host"] = addr[0]
            found[(addr[0], parsed["port"], parsed["relay"])] = parsed
    finally:
        sock.close()
    return list(found.values())


class Relay:
    """Forward bytes between the first two computers that connect."""

    def __init__(self) -> None:
        self.error = ""
        self.ready = False
        self._server: socket.socket | None = None
        self._stop = False
        self._socks: list[socket.socket] = []

    def start(self, port: int = 5555) -> int:
        self.close()
        self._stop = False
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", port))
        server.listen(2)
        server.settimeout(0.5)
        self._server = server
        threading.Thread(target=self._run, name="net-relay", daemon=True).start()
        return int(server.getsockname()[1])

    def close(self) -> None:
        self._stop = True
        self.ready = False
        for sock in list(self._socks):
            try:
                sock.close()
            except OSError:
                pass
        self._socks.clear()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None

    def _run(self) -> None:
        server = self._server
        if server is None:
            return
        pair: list[socket.socket] = []
        while not self._stop and len(pair) < 2:
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            pair.append(conn)
            self._socks.append(conn)
        if len(pair) < 2 or self._stop:
            return
        try:
            pair[0].sendall(b"R1")
            pair[1].sendall(b"R2")
        except OSError:
            self.error = "Could not start the relay."
            return
        self.ready = True
        left = threading.Thread(target=self._copy, args=(pair[0], pair[1]), daemon=True)
        right = threading.Thread(target=self._copy, args=(pair[1], pair[0]), daemon=True)
        left.start()
        right.start()

    def _copy(self, source: socket.socket, dest: socket.socket) -> None:
        try:
            while not self._stop:
                blob = source.recv(4096)
                if not blob:
                    break
                dest.sendall(blob)
        except OSError:
            pass
        self.ready = False
