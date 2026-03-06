# Émetteur Mac → ESP32 (panel HUB75 64×64)

## Principe

L'ESP32 (sketch `udp_receiver`) écoute des frames UDP sur le port **5005**.
L'émetteur Mac génère des images 64×64 et les envoie en UDP.

## Trouver l'IP de l'ESP32

Brancher l'ESP32 et ouvrir le moniteur série :
```bash
~/.platformio/penv/bin/pio device monitor
```
L'IP s'affiche au démarrage : `IP: 192.168.x.x  port UDP: 5005`

## Format d'un paquet UDP

```
[4 octets] numéro de frame (big-endian, peut rester à 0)
[12288 octets] pixels RGB bruts, ligne par ligne, de haut en bas

Ordre des pixels :
  pixel (x=0, y=0), (x=1, y=0), ..., (x=63, y=0),   ← ligne 0
  pixel (x=0, y=1), ..., (x=63, y=63)                 ← ligne 63

Chaque pixel = 3 octets : R, G, B (0-255)
Taille totale : 4 + 64 × 64 × 3 = 12292 octets
```

## Exemple Python minimal

```python
import socket
import struct
import time

ESP32_IP   = "192.168.x.x"   # à remplacer par l'IP affichée au démarrage
ESP32_PORT = 5005
PANEL_W, PANEL_H = 64, 64

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def send_frame(pixels_rgb: bytes, frame_number: int = 0):
    """pixels_rgb : bytes de longueur 12288 (RGB brut ligne par ligne)"""
    header = struct.pack(">I", frame_number)
    sock.sendto(header + pixels_rgb, (ESP32_IP, ESP32_PORT))

# Exemple : remplir l'écran en rouge
frame_number = 0
while True:
    pixels = bytes([255, 0, 0] * PANEL_W * PANEL_H)  # tout rouge
    send_frame(pixels, frame_number)
    frame_number += 1
    time.sleep(1 / 30)  # 30 fps
```

## Exemple avec Pygame (animations)

```python
import socket, struct, time
import pygame

ESP32_IP   = "192.168.x.x"
ESP32_PORT = 5005
PANEL_W, PANEL_H = 64, 64
FPS = 30

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

pygame.init()
# Surface de travail à la résolution du panel
surface = pygame.Surface((PANEL_W, PANEL_H))
clock = pygame.time.Clock()

def send_surface(surf: pygame.Surface, frame_number: int):
    # pygame stocke en RGBA, on extrait RGB ligne par ligne
    raw = pygame.image.tostring(surf, "RGB")
    header = struct.pack(">I", frame_number)
    sock.sendto(header + raw, (ESP32_IP, ESP32_PORT))

frame_number = 0
t = 0.0

while True:
    # --- Dessine ton animation ici ---
    surface.fill((0, 0, 0))
    hue_offset = int(t * 60) % 360
    for x in range(PANEL_W):
        hue = (x * 360 // PANEL_W + hue_offset) % 360
        color = pygame.Color(0)
        color.hsva = (hue, 100, 100, 100)
        pygame.draw.line(surface, color, (x, 0), (x, PANEL_H - 1))
    # ---------------------------------

    send_surface(surface, frame_number)
    frame_number += 1
    t += 1 / FPS
    clock.tick(FPS)
```

Lancer avec :
```bash
pip install pygame
python emetteur.py
```

## Notes

- Le panel s'actualise dès réception d'un paquet complet (≥ 12292 octets).
- Les paquets trop courts sont ignorés silencieusement par l'ESP32.
- Pas de contrôle de flux : si l'ESP32 est occupé à afficher, les paquets suivants
  sont simplement perdus (acceptable pour de l'animation temps réel).
- À 30 fps, le débit est d'environ 3 Mo/s, très en dessous de la capacité du Wi-Fi.
