#!/usr/bin/env bash
# Setup Raspberry Pi pour VJ Panel
# Usage: bash vj/rpi/setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== VJ Panel — Setup Raspberry Pi ==="
echo "Répertoire projet : $REPO_ROOT"
echo

# ── 1. Packages système ───────────────────────────────────────────────────────
echo "[1/5] Packages système..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    libportaudio2 portaudio19-dev \
    libasound2-dev \
    libgl1-mesa-glx libgles2-mesa \
    qt6-base-dev libqt6gui6 \
    fonts-dejavu-core \
    git

# ── 2. uv ────────────────────────────────────────────────────────────────────
echo "[2/5] Installation de uv..."
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Recharger le PATH pour la suite du script
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi
echo "  uv $(uv --version)"

# ── 3. Environnement virtuel + dépendances ────────────────────────────────────
echo "[3/5] Création de l'environnement virtuel..."
cd "$REPO_ROOT"
uv sync --extra video

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

# ── Résumé ────────────────────────────────────────────────────────────────────
echo
echo "=== Setup terminé ==="
echo
echo "Lancer l'app :"
echo "  cd $REPO_ROOT"
echo "  uv run python vj/rpi/main.py"
echo "  uv run python vj/rpi/main.py --esp32 ledpanel.local"
echo
echo "Lancer au démarrage (optionnel) :"
echo "  voir vj/rpi/autostart.md"
