#!/usr/bin/env python3
"""Loopback relay from 127.0.0.1:18803 to the operator-console container.

Compose may not publish host ports (protected-port policy), so Tailscale Serve
reaches the console through this host relay. The upstream address is resolved
from the Compose project/service labels on every new connection, so a
recreated container with a new address is picked up without a restart.
"""
import os
import socket
import subprocess
import threading

LISTEN_HOST = os.environ.get("CONSOLE_RELAY_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("CONSOLE_RELAY_LISTEN_PORT", "18803"))
PROJECT = os.environ.get("CONSOLE_RELAY_COMPOSE_PROJECT", "linkautowork-prod")
SERVICE = os.environ.get("CONSOLE_RELAY_COMPOSE_SERVICE", "operator-console")
NETWORK = os.environ.get("CONSOLE_RELAY_NETWORK", "linkautowork_autowork-edge")
TARGET_PORT = int(os.environ.get("CONSOLE_RELAY_TARGET_PORT", "8080"))


def resolve_target():
    ids = subprocess.run(
        ["docker", "ps", "-q",
         "--filter", f"label=com.docker.compose.project={PROJECT}",
         "--filter", f"label=com.docker.compose.service={SERVICE}"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.split()
    if not ids:
        raise RuntimeError(f"no running {PROJECT}/{SERVICE} container")
    address = subprocess.run(
        ["docker", "inspect", "-f",
         f'{{{{with index .NetworkSettings.Networks "{NETWORK}"}}}}{{{{.IPAddress}}}}{{{{end}}}}', ids[0]],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if not address:
        raise RuntimeError(f"{SERVICE} has no address on {NETWORK}")
    return address, TARGET_PORT


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client):
    try:
        upstream = socket.create_connection(resolve_target(), timeout=10)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        client.close()
        return
    upstream.settimeout(None)
    threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
    pipe(upstream, client)
    client.close()
    upstream.close()


def main():
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(64)
    while True:
        client, _addr = server.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
