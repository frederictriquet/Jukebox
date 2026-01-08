#!/bin/bash
# Quick setup script for Jukebox with uv

set -e

echo "🎵 Jukebox Setup Script"
echo "======================"
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo "✅ uv installed"
else
    echo "✅ uv already installed"
fi

# Check if VLC is installed
echo ""
echo "🔍 Checking for VLC..."
if command -v vlc &> /dev/null; then
    echo "✅ VLC found"
elif [ -f "/Applications/VLC.app/Contents/MacOS/VLC" ]; then
    echo "✅ VLC found (macOS)"
else
    echo "⚠️  VLC not found!"
    echo "Please install VLC:"
    echo "  - macOS: brew install vlc"
    echo "  - Ubuntu/Debian: sudo apt-get install vlc libvlc-dev"
    echo "  - Arch: sudo pacman -S vlc"
    echo ""
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
uv sync --all-extras

echo ""
echo "✨ Setup complete!"
echo ""
echo "Run the application with:"
echo "  make run"
echo "  or"
echo "  uv run jukebox"
echo ""
