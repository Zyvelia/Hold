"""Check private WFC listeners and the read-only GTS handshake."""

import argparse
import http.client
import re
import socket
import sys

GTS_HOST = "gamestats2.gs.nintendowifi.net"
CONNECT_HOST = "conntest.nintendowifi.net"


def fetch(server, port, host, path):
    connection = http.client.HTTPConnection(server, port, timeout=5)
    try:
        connection.request("GET", path, headers={"Host": host})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read(64)
    finally:
        connection.close()


def check_connection(server, port):
    if fetch(server, port, CONNECT_HOST, "/") != b"ok":
        raise RuntimeError("Unexpected connection test response.")


def check_gts(server, port, generation, pid):
    token = fetch(server, port, GTS_HOST, f"/{generation}/worldexchange/info.asp?pid={pid}")
    if not re.fullmatch(rb"[A-Za-z0-9]{32}", token):
        raise RuntimeError("The GTS endpoint didn't return a handshake token.")


def check_friend_codes(server):
    with socket.create_connection((server, 29900), timeout=5) as connection:
        data = b""
        while b"\\final\\" not in data and len(data) < 1024:
            part = connection.recv(1024 - len(data))
            if not part:
                break
            data += part
        if not data.startswith(b"\\lc\\1\\") or b"\\challenge\\" not in data:
            raise RuntimeError("The profile server didn't send a login challenge.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=80, type=int)
    parser.add_argument("--pid", type=int, help="Test GameSpy profile ID for the GTS checks")
    args = parser.parse_args()
    checks = [
        ("Connection test", lambda: check_connection(args.host, args.port)),
        ("Friend-code login listener", lambda: check_friend_codes(args.host)),
    ]
    if args.pid is not None:
        if not 1 <= args.pid <= 0xFFFFFFFF:
            parser.error("--pid must be a positive 32-bit profile ID.")
        for generation, name in (("pokemondpds", "Gen IV"), ("syachi2ds", "Gen V")):
            checks.append((f"{name} GTS", lambda gen=generation: check_gts(args.host, args.port, gen, args.pid)))
    else:
        print("Add --pid with a test profile ID to check the two GTS endpoints.")
    failed = False
    for name, check in checks:
        try:
            check()
        except (OSError, RuntimeError, http.client.HTTPException) as exc:
            print(f"FAIL {name}: {exc}", file=sys.stderr)
            failed = True
        else:
            print(f"OK   {name}")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
