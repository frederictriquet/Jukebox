#!/usr/bin/env python3
"""Test d'envoi UDP vers ESP32 panel 64x64.

Usage:
    python vj/test_esp32_send.py 192.168.x.x
"""

import socket
import struct
import sys
import time

ESP32_PORT = 5005
W, H = 64, 64
PAYLOAD_SIZE = W * H * 3   # 12288
CHUNK_SIZE   = 1024
TOTAL_CHUNKS = PAYLOAD_SIZE // CHUNK_SIZE  # 12


def send_frame(sock: socket.socket, ip: str, pixels: bytes, frame_n: int = 0) -> None:
    for i in range(TOTAL_CHUNKS):
        chunk = pixels[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE]
        header = struct.pack(">IHH", frame_n, i, TOTAL_CHUNKS)
        sock.sendto(header + chunk, (ip, ESP32_PORT))


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <ESP32_IP>")
        sys.exit(1)

    ip = sys.argv[1]
    print(f"Target  : {ip}:{ESP32_PORT}")
    print(f"Payload : {PAYLOAD_SIZE} bytes ({W}x{H} RGB), {TOTAL_CHUNKS} chunks de {CHUNK_SIZE} octets")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
    print(f"SO_SNDBUF : {sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)}")

    colors = [
        ("Rouge",  bytes([255, 0, 0]   * W * H)),
        ("Vert",   bytes([0, 255, 0]   * W * H)),
        ("Bleu",   bytes([0, 0, 255]   * W * H)),
        ("Blanc",  bytes([255, 255, 255] * W * H)),
        ("Noir",   bytes([0, 0, 0]     * W * H)),
    ]

    try:
        for frame_n, (name, pixels) in enumerate(colors):
            print(f"  [{frame_n}] Envoi {name}...", end=" ", flush=True)
            send_frame(sock, ip, pixels, frame_n)
            print("OK")
            time.sleep(1.5)
    except OSError as e:
        print(f"ERREUR : {e}")
        print()
        print("Causes possibles :")
        print("  - IP incorrecte ou ESP32 non joignable")
        print("  - SO_SNDBUF insuffisant (voir valeur ci-dessus)")
        print("  - MTU réseau trop petit (essaie avec un câble ou hotspot dédié)")
    finally:
        sock.close()
        print("Socket fermé.")


if __name__ == "__main__":
    main()
