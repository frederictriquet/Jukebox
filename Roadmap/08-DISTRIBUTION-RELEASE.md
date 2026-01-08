# Phase 8: Distribution & Release

**Durée**: Semaines 8-10
**Objectif**: Packages finalisés et release 1.0
**Milestone**: `v1.0.0` - Production Ready

---

## Vue d'Ensemble

Cette phase finalise les packages distribuables et prépare la release 1.0.

---

## 8.1 PyInstaller Builds (Jours 1-3)

### 8.1.1 Spec Files
Créer `build/jukebox.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['../jukebox/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('../config', 'config'),
        ('../README.md', '.'),
        ('../LICENSE', '.'),
    ],
    hiddenimports=[
        'PySide6',
        'vlc',
        'mutagen',
        'sqlite3',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='jukebox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='jukebox',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='Jukebox.app',
    icon='assets/icon.icns',
    bundle_identifier='com.yourname.jukebox',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
    },
)
```

### 8.1.2 Build Scripts
Créer `scripts/build.sh`:

```bash
#!/bin/bash
# Build script for all platforms

set -e

echo "Building Jukebox..."

# Clean previous builds
rm -rf dist/ build/

# Build with PyInstaller
poetry run pyinstaller build/jukebox.spec

# Platform-specific post-processing
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Creating DMG for macOS..."
    # Create DMG
    hdiutil create -volname "Jukebox" -srcfolder dist/Jukebox.app -ov -format UDZO dist/Jukebox.dmg

elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Creating tarball for Linux..."
    cd dist
    tar -czf jukebox-linux-x86_64.tar.gz jukebox/
    cd ..

elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    echo "Creating installer for Windows..."
    # Use NSIS or Inno Setup for Windows installer
fi

echo "Build complete!"
ls -lh dist/
```

---

## 8.2 Raspberry Pi Package (Jour 3)

### 8.2.1 Installation Script
Créer `scripts/install_pi.sh`:

```bash
#!/bin/bash
# Installation script for Raspberry Pi

set -e

echo "Installing Jukebox on Raspberry Pi..."

# Check if running on Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo; then
    echo "Warning: This script is optimized for Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system packages..."
sudo apt-get update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y \
    python3.11 \
    python3-pip \
    python3-venv \
    libvlc-dev \
    vlc \
    portaudio19-dev \
    libsndfile1 \
    libatlas-base-dev \
    python3-pyqt6 \
    python3-pyqt6.qtmultimedia

# Create installation directory
INSTALL_DIR="$HOME/jukebox"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Create virtual environment
echo "Creating virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Install Jukebox
echo "Installing Jukebox..."
pip install --upgrade pip
pip install jukebox-audio  # Or from source

# Create desktop entry
echo "Creating desktop entry..."
cat > ~/.local/share/applications/jukebox.desktop << EOF
[Desktop Entry]
Name=Jukebox
Comment=Audio jukebox application
Exec=$INSTALL_DIR/venv/bin/python -m jukebox.main
Icon=$INSTALL_DIR/assets/icon.png
Terminal=false
Type=Application
Categories=AudioVideo;Audio;
EOF

# Create launch script
cat > "$INSTALL_DIR/jukebox.sh" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
source venv/bin/activate
python -m jukebox.main
EOF
chmod +x "$INSTALL_DIR/jukebox.sh"

echo "Installation complete!"
echo "Launch Jukebox from the application menu or run: $INSTALL_DIR/jukebox.sh"
```

---

## 8.3 Documentation Complète (Jours 4-5)

### 8.3.1 README.md final
```markdown
# Jukebox

[![CI](https://github.com/yourusername/jukebox/workflows/CI/badge.svg)](https://github.com/yourusername/jukebox/actions)
[![Version](https://img.shields.io/github/v/release/yourusername/jukebox)](https://github.com/yourusername/jukebox/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A modular audio jukebox application for Mac, Linux, and Raspberry Pi.

## ✨ Features

- 🎵 Multi-format audio playback (MP3, FLAC, AIFF, WAV)
- 🔍 Lightning-fast full-text search
- 📊 Waveform visualization
- 🎨 Dark/Light themes
- 🔌 Plugin architecture
- 🎯 Smart recommendations
- 🗂️ Automatic file organization
- 📱 Raspberry Pi optimized

## 📦 Installation

### macOS

Download the latest `.dmg` from [Releases](https://github.com/yourusername/jukebox/releases).

### Linux

```bash
wget https://github.com/yourusername/jukebox/releases/latest/download/jukebox-linux-x86_64.tar.gz
tar -xzf jukebox-linux-x86_64.tar.gz
cd jukebox
./jukebox
```

### Raspberry Pi

```bash
curl -sSL https://raw.githubusercontent.com/yourusername/jukebox/main/scripts/install_pi.sh | bash
```

### From Source

```bash
git clone https://github.com/yourusername/jukebox.git
cd jukebox
poetry install
poetry run jukebox
```

## 🚀 Quick Start

1. Launch Jukebox
2. Click "Add Files..." or scan a directory
3. Search and play your music
4. Explore plugins in the Tools menu

## 📖 Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Plugin Development](docs/PLUGIN_DEVELOPMENT.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

## 📄 License

MIT License - see [LICENSE](LICENSE)

## 🙏 Acknowledgments

Built with:
- [PySide6](https://doc.qt.io/qtforpython-6/)
- [python-vlc](https://github.com/oaubert/python-vlc)
- [mutagen](https://github.com/quodlibet/mutagen)
```

### 8.3.2 CHANGELOG.md
```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-XX-XX

### Added
- Initial release
- Audio playback (MP3, FLAC, AIFF, WAV)
- SQLite database with FTS5 search
- Plugin architecture
- Waveform visualization
- Smart recommendations
- File organization tools
- Duplicate finder
- Dark/Light themes
- Raspberry Pi support
- Cross-platform builds (Mac, Linux, Windows)

### Features
- Full-text search
- Playlists
- Play history
- Keyboard shortcuts
- Jukebox/Curating modes

### Plugins
- Search
- History tracking
- Statistics
- Waveform visualizer
- Recommendations
- Duplicate finder
- File curator

## [0.9.0-rc] - 2026-XX-XX

### Added
- 3D waveform visualization
- Performance optimizations for Raspberry Pi
- Complete keyboard shortcuts
- Mode switching (Jukebox/Curating)

## [0.5.0-beta] - 2026-XX-XX

### Added
- Plugin system
- Essential modules
- Database with FTS5

## [0.3.0-beta] - 2026-XX-XX

### Added
- Core features
- File scanning
- Metadata extraction

## [0.2.0-alpha] - 2026-XX-XX

### Added
- CI/CD pipeline
- Testing infrastructure

## [0.1.0-alpha] - 2026-XX-XX

### Added
- Basic MVP
- Audio playback
- Simple UI
```

---

## 8.4 Tests Finaux (Jours 6-7)

### 8.4.1 Test Plan
```markdown
# Release Test Plan

## Manual Testing

### Installation
- [ ] macOS .dmg installs correctly
- [ ] Linux tarball extracts and runs
- [ ] Windows installer works
- [ ] Raspberry Pi script installs successfully

### Core Features
- [ ] Audio playback (all formats)
- [ ] Search works
- [ ] Playlists functional
- [ ] All plugins load

### Platform-Specific
- [ ] macOS native look
- [ ] Linux theming works
- [ ] Pi performance acceptable
- [ ] Windows installer/uninstaller

### Regression
- [ ] All automated tests pass
- [ ] No memory leaks
- [ ] No crashes in normal use
- [ ] Performance benchmarks met
```

---

## 8.5 Release Process (Jours 8-10)

### 8.5.1 Pre-release Checklist
```markdown
## Pre-Release Checklist

### Code
- [ ] All tests passing
- [ ] Coverage > 70%
- [ ] No critical bugs
- [ ] Version bumped
- [ ] CHANGELOG updated

### Documentation
- [ ] README complete
- [ ] User guide updated
- [ ] API docs generated
- [ ] Screenshots current

### Builds
- [ ] macOS .dmg built and tested
- [ ] Linux tarball built and tested
- [ ] Windows installer built and tested
- [ ] Pi script tested on actual Pi

### Legal
- [ ] LICENSE file included
- [ ] Third-party licenses acknowledged
- [ ] Copyright notices updated

### Marketing
- [ ] Release notes written
- [ ] Announcement prepared
- [ ] Social media posts ready
```

### 8.5.2 Release Script
Créer `scripts/release.sh`:

```bash
#!/bin/bash
# Release script

set -e

VERSION=$1

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    exit 1
fi

echo "Releasing version $VERSION..."

# Run tests
echo "Running tests..."
make ci

# Update version
echo "Updating version..."
poetry version "$VERSION"

# Update CHANGELOG
echo "Update CHANGELOG.md with release date"
read -p "Press enter when done..."

# Commit and tag
git add pyproject.toml CHANGELOG.md
git commit -m "Release v$VERSION"
git tag -a "v$VERSION" -m "Version $VERSION"

# Build packages
echo "Building packages..."
./scripts/build.sh

# Push
echo "Pushing to GitHub..."
git push origin main
git push origin "v$VERSION"

echo "Release v$VERSION complete!"
echo "Go to GitHub to create the release and upload artifacts."
```

---

## 8.6 Post-Release (Jour 10)

### 8.6.1 Monitoring
- Setup crash reporting
- Monitor GitHub issues
- Check download statistics
- Gather user feedback

### 8.6.2 Next Steps
- Plan v1.1.0 features
- Address critical bugs
- Improve documentation based on feedback

---

## Checklist Phase 8

### Builds (Jours 1-3)
- [ ] PyInstaller specs finalized
- [ ] macOS .dmg created
- [ ] Linux tarball created
- [ ] Windows installer created
- [ ] Pi script tested

### Documentation (Jours 4-5)
- [ ] README complete
- [ ] User guide written
- [ ] CHANGELOG updated
- [ ] Screenshots added
- [ ] Plugin dev guide

### Testing (Jours 6-7)
- [ ] Manual test plan executed
- [ ] All platforms tested
- [ ] Performance validated
- [ ] No critical bugs

### Release (Jours 8-10)
- [ ] Version tagged
- [ ] GitHub release created
- [ ] Artifacts uploaded
- [ ] Announcement published

---

## 🎉 Release Complete!

**v1.0.0 Production Ready**

---

**Durée estimée**: 10 jours
**Effort**: ~60-70 heures
**Complexité**: Moyenne
