#!/bin/bash
# Build melonDS (a second, stricter emulator) for headless boot tests: verify/urbz_melon.py.
# Linux only (Ubuntu 24.04 packages). Puts the program in verify/melonds/melonDS (git-ignored).
# Takes about 5 minutes. melonDS runs DS games without BIOS files (built-in replacements).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
TAG=${MELONDS_TAG:-1.1}
apt-get update -qq
apt-get install -y -qq cmake ninja-build pkg-config qt6-base-dev qt6-base-private-dev qt6-multimedia-dev \
    qt6-svg-dev libsdl2-dev libarchive-dev libenet-dev libslirp-dev libzstd-dev libfaad-dev \
    extra-cmake-modules libgl-dev xvfb xdotool openbox imagemagick >/dev/null
SRC="$HERE/melonds/src"
if [ ! -d "$SRC" ]; then git clone -q https://github.com/melonDS-emu/melonDS.git "$SRC"; fi
git -C "$SRC" checkout -q "$TAG"
cmake -S "$SRC" -B "$SRC/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DUSE_QT6=ON >/dev/null
cmake --build "$SRC/build" -j"$(nproc)" >/dev/null
cp "$SRC/build/melonDS" "$HERE/melonds/melonDS"
echo "melonDS $TAG ready: $HERE/melonds/melonDS"
