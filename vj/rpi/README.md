# Projet : Panneau LED Audio-Réactif

## Objectif

Créer un visualiseur audio sur panel LED, piloté par un ESP32-S3 captant le son ambiant via un micro I2S. Évolutif vers un pilotage par Raspberry Pi via Wi-Fi (Phase 2).

---

## Matériel

| Composant | Modèle exact | État |
|---|---|---|
| Microcontrôleur | **ESP32-S3-DevKitC-1 N16R8** (16 Mo Flash, 8 Mo PSRAM) | ✅ Possédé |
| Micro I2S | **INMP441** (module breakout) | ✅ Possédé |
| Câbles | Dupont mâle-femelle et femelle-femelle | ✅ Possédé |
| Panel LED | **HUB75E 64×64 P3** (192×192mm) — ex: Waveshare RGB-Matrix-P3-64x64 | ❌ À acheter |
| Alimentation | **Mean Well LRS-35-5** (5V 7A, bornier à vis) | ❌ À acheter |
| Raspberry Pi | **Raspberry Pi 4 Model B Rev 1.1** — 4 Go RAM | ✅ Possédé |
| Écran Pi | **CX101PI-C_V2** — portable monitor 10.1" 1920×1200 | ✅ Possédé |

**Note :** les pin headers doivent être soudés sur l'ESP32 et le micro INMP441 (barrettes mâles 2.54mm) pour brancher les câbles dupont.

---

## Raspberry Pi — Configuration système

### OS installé

**Raspberry Pi OS Trixie 64-bit Desktop** (Debian 13), installé via Raspberry Pi Imager.

- Utilise **X11/openbox** (pas labwc/Wayland — incompatible avec FKMS et le moniteur)
- Utilisateur : `fred`

### Configuration critique : /boot/firmware/config.txt

Le moniteur CX101PI-C_V2 n'est pas détecté par le driver KMS standard. La modification suivante est **indispensable** :

```
# MODIFICATION CRITIQUE pour le moniteur CX101PI-C_V2
# Remplacer :   dtoverlay=vc4-kms-v3d
# Par :         dtoverlay=vc4-fkms-v3d
# Sans cette modification, l'écran reste noir après le boot
# (le driver KMS ne détecte pas l'EDID du moniteur)
dtoverlay=vc4-fkms-v3d
```

Autres paramètres HDMI ajoutés dans la section `[all]` :

```
[all]
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=87
hdmi_cvt=1920 1200 60 5 0 0 0
hdmi_drive=2
disable_overscan=1
```

### Configuration : /boot/firmware/cmdline.txt

Ajout en fin de ligne (une seule ligne, pas de retour) :

```
video=HDMI-A-1:1920x1200@60D
```

Le `D` final force le mode même si l'écran se déclare "disconnected".

### Notes importantes sur le Pi

- **EEPROM bootloader** : version 2025/11/05 (à jour)
- **Trixie fonctionne** à condition d'utiliser `vc4-fkms-v3d` (le driver KMS standard ne détecte pas le moniteur CX101PI)
- **Ne pas utiliser labwc/Wayland** : incompatible avec le driver FKMS + ce moniteur
- **Jack audio 3.5mm du Pi = sortie uniquement**, pas d'entrée possible
- Pour l'entrée audio en Phase 2 : utiliser un dongle USB audio, ou capter le flux audio en logiciel (Spotify/Bluetooth via PulseAudio/PipeWire)

---

## Câblage : Micro INMP441 → ESP32-S3

| Pin INMP441 | GPIO ESP32-S3 |
|---|---|
| WS | GPIO 15 |
| SCK | GPIO 16 |
| SD | GPIO 17 |
| L/R | GND |
| VDD | 3.3V |
| GND | GND |

---

## Câblage : Panel HUB75E → ESP32-S3 (pour quand le panel arrive)

### Données couleur

| Signal HUB75E | GPIO |
|---|---|
| R1 | 42 |
| G1 | 41 |
| B1 | 40 |
| R2 | 38 |
| G2 | 39 |
| B2 | 37 |

### Adresses

| Signal HUB75E | GPIO |
|---|---|
| LA (A) | 45 |
| LB (B) | 36 |
| LC (C) | 48 |
| LD (D) | 35 |
| LE (E) | 21 |

### Contrôle

| Signal HUB75E | GPIO |
|---|---|
| CLK | 2 |
| LAT | 47 |
| CE (= OE) | 14 |
| GND | GND commun |

**Note sur le connecteur du panel :** CE = OE (même signal, nom différent selon fabricant). Le pin "N" sur le connecteur est non connecté (ignorer).

---

## Alimentation (quand le panel est branché)

```
Alimentation 5V (Mean Well LRS-35-5)
  +5V → Panel VCC + ESP32 pin 5V
  GND → Panel GND + ESP32 GND (masse commune obligatoire)
```

- Ne jamais alimenter le panel via l'ESP32
- En dev sans panel, l'USB-C suffit pour l'ESP32

---

## Environnement logiciel ESP32

- **IDE :** Arduino IDE ou PlatformIO (VS Code)
- **Carte :** ESP32-S3 Dev Module
- **Package board :** `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
- **Bibliothèques :**
  - `ESP32-HUB75-MatrixPanel-I2S-DMA` — pilote panel HUB75
  - `arduinoFFT` — analyse fréquentielle

---

## Code déjà développé / testé

### 1. Test micro (moniteur série)

Sketch qui lit le micro INMP441 et affiche le volume en barres dans le moniteur série (115200 baud). Permet de valider le câblage du micro indépendamment du panel.

### 2. Serveur web avec spectrogramme

Sketch qui crée un point d'accès Wi-Fi ("ESP32-Audio", mdp "12345678") et sert une page web avec un spectrogramme FFT 16 bandes en temps réel. Accessible sur `http://192.168.4.1` depuis un téléphone connecté au Wi-Fi de l'ESP32.

- L'ESP32 expose un endpoint `/fft` qui retourne un JSON avec les 16 bandes
- La page web interroge `/fft` toutes les 50ms et affiche des barres animées
- Valide tout le pipeline : micro → I2S → FFT → visualisation

### 3. Spectrogramme sur panel HUB75 (prêt, pas encore testé)

Sketch complet fourni dans le guide .docx : lit le micro, FFT, affiche 64 barres colorées (arc-en-ciel) sur le panel 64×64. À tester quand le panel arrive.

---

## Plan d'évolution

### Phase 1 (actuelle) — ESP32-S3 autonome
ESP32 capte le son via INMP441, fait la FFT, pilote le panel HUB75 directement.

### Phase 2 — Raspberry Pi comme cerveau audio
- Brancher le Pi sur la sortie audio de la sono (line-in via dongle USB / Bluetooth / Spotify)
- Installer **LedFx** sur le Pi
- Le Pi envoie les frames à l'ESP32 via Wi-Fi en **E1.31/sACN** ou **Art-Net**
- Flasher **WLED** sur l'ESP32 (sait recevoir du E1.31 nativement)
- Même hardware, seul le firmware de l'ESP32 change

### Phase 3 — Mise à l'échelle
Ajouter d'autres panels HUB75 + d'autres ESP32 récepteurs, pilotés par le même Pi.

---

## Ressources utiles

- Bibliothèque HUB75 : `https://github.com/mrfaptastic/ESP32-HUB75-MatrixPanel-DMA`
- WLED (Phase 2) : `https://kno.wled.ge/`
- LedFx (Phase 2) : `https://www.ledfx.app/`