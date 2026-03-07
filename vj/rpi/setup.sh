#!/usr/bin/env bash
# Setup Raspberry Pi pour VJ Panel
# Usage: bash vj/rpi/setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCH="$(uname -m)"

echo "=== VJ Panel — Setup Raspberry Pi ==="
echo "Répertoire projet : $REPO_ROOT"
echo "Architecture      : $ARCH"
echo

# ── Avertissement ARMv7 ────────────────────────────────────────────────────────
if [ "$ARCH" = "armv7l" ]; then
    echo "⚠️  OS 32-bit détecté (ARMv7)."
    echo "   PySide6 n'a pas de wheel ARMv7 sur PyPI."
    echo "   Il sera installé via apt (python3-pyside6)."
    echo "   Pour une meilleure compatibilité, préférez un OS 64-bit (aarch64)."
    echo "   → https://www.raspberrypi.com/software/ (Raspberry Pi OS 64-bit)"
    echo
    ARMV7=true
else
    ARMV7=false
fi

# ── 1. Packages système ───────────────────────────────────────────────────────
echo "[1/5] Packages système..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    libportaudio2 portaudio19-dev \
    libasound2-dev \
    libgl1 \
    fonts-dejavu-core \
    git

# Sur ARMv7, PySide6 doit venir d'apt (disponible uniquement sur Debian Bookworm / Ubuntu 23.04+)
if [ "$ARMV7" = true ]; then
    echo "  ARMv7 : recherche de python3-pyside6 dans apt..."
    if apt-cache show python3-pyside6.qtwidgets &>/dev/null; then
        sudo apt-get install -y python3-pyside6.qtwidgets python3-pyside6.qtcore python3-pyside6.qtgui
    else
        echo
        echo "╔══════════════════════════════════════════════════════════════════╗"
        echo "║  ERREUR : PySide6 non disponible sur cette plateforme            ║"
        echo "╠══════════════════════════════════════════════════════════════════╣"
        echo "║  PySide6 n'a ni wheel ARMv7 sur PyPI ni paquet apt sur cet OS.  ║"
        echo "║                                                                  ║"
        echo "║  Solution : installer Raspberry Pi OS 64-bit (aarch64)          ║"
        echo "║  → https://www.raspberrypi.com/software/                        ║"
        echo "╚══════════════════════════════════════════════════════════════════╝"
        exit 1
    fi
fi

# ── 2. uv ────────────────────────────────────────────────────────────────────
echo "[2/5] Installation de uv..."
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

_find_uv() {
    if command -v uv &>/dev/null; then
        command -v uv
    elif [ -x "$HOME/.local/bin/uv" ]; then
        echo "$HOME/.local/bin/uv"
    elif [ -x "$HOME/.cargo/bin/uv" ]; then
        echo "$HOME/.cargo/bin/uv"
    fi
}

if [ -z "$(_find_uv)" ]; then
    echo "  uv absent — installation via curl..."
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    else
        echo "  curl échoué — fallback pip3..."
        pip3 install --user uv
    fi
fi

UV_BIN="$(_find_uv)"
if [ -z "$UV_BIN" ]; then
    echo "ERREUR : impossible de trouver uv après installation."
    echo "Essayez manuellement : pip3 install --user uv"
    exit 1
fi

echo "  uv $("$UV_BIN" --version)"
uv() { "$UV_BIN" "$@"; }
export -f uv

# ── 3. Environnement virtuel + dépendances ────────────────────────────────────
echo "[3/5] Création de l'environnement virtuel..."
cd "$REPO_ROOT"
if [ "$ARMV7" = true ]; then
    # PySide6 vient d'apt → on autorise les packages système dans le venv
    uv sync --extra video --python-preference system \
        --no-build-isolation \
        --link-mode=copy \
        2>/dev/null || \
    uv sync --extra video --system-site-packages
else
    uv sync --extra video
fi

# ── 4. Test imports critiques ─────────────────────────────────────────────────
echo "[4/5] Vérification des imports..."
uv run python - <<'EOF'
import importlib, sys

required = {
    "PySide6":      "PySide6",
    "numpy":        "numpy",
    "PIL":          "Pillow",
    "sounddevice":  "sounddevice",
    "noise":        "noise",
}

ok = True
for mod, pkg in required.items():
    try:
        importlib.import_module(mod)
        print(f"  ✓ {pkg}")
    except ImportError:
        print(f"  ✗ {pkg} MANQUANT")
        ok = False

# moderngl optionnel (GPU peut ne pas être dispo sur RPi)
try:
    import moderngl
    print(f"  ✓ moderngl (GPU disponible)")
except ImportError:
    print(f"  ~ moderngl absent — rendu CPU uniquement (normal sur RPi)")

if not ok:
    sys.exit(1)
EOF

# ── 5. mDNS (résolution de ledpanel.local) ────────────────────────────────────
echo "[5/5] Configuration mDNS (avahi)..."
if ! command -v avahi-daemon &>/dev/null; then
    sudo apt-get install -y avahi-daemon libnss-mdns
fi
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon
echo "  mDNS actif — ledpanel.local sera résolu automatiquement"

# ── PATH persistant ───────────────────────────────────────────────────────────
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
for RC in "$HOME/.bashrc" "$HOME/.profile"; do
    if [ -f "$RC" ] && ! grep -qF '.local/bin' "$RC"; then
        echo "$PATH_LINE" >> "$RC"
        echo "  PATH mis à jour dans $RC"
    fi
done

# ── Résumé ────────────────────────────────────────────────────────────────────
echo
echo "=== Setup terminé ==="
echo
echo "Lancer l'app :"
echo "  cd $REPO_ROOT"
echo "  uv run python vj/rpi/main.py"
echo "  uv run python vj/rpi/main.py --esp32 ledpanel.local"
echo
echo "⚠️  Si 'uv' est introuvable, recharge ton shell :"
echo "  source ~/.bashrc"
