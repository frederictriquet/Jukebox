"""Diagnostic: test analyze_mix flow step by step on a real mix."""
import sys
import logging
sys.path.insert(0, "/Users/fred/Code/Jukebox")

logging.basicConfig(level=logging.WARNING)

from shazamix.database import FingerprintDB
from shazamix.fingerprint import Fingerprinter, Fingerprint
from shazamix.matcher import Matcher
import numpy as np

DB_PATH = "/Users/fred/.jukebox/jukebox.db"

# Find a mix file
import glob
mix_files = glob.glob("/Users/fred/Music/**/*.mp3", recursive=True)
# Filter for likely mixes (larger files)
import os
large_files = [(f, os.path.getsize(f)) for f in mix_files if os.path.getsize(f) > 50_000_000]
large_files.sort(key=lambda x: -x[1])

if not large_files:
    print("No large audio files found for testing")
    sys.exit(1)

MIX_PATH = large_files[0][0]
print(f"Using mix: {MIX_PATH} ({large_files[0][1] / 1_000_000:.0f} MB)")

db = FingerprintDB(DB_PATH)
fp = Fingerprinter()
matcher = Matcher(db, fp)

# Load first 60s of the mix
import librosa
print("Loading first 60s of mix...")
y, sr = librosa.load(MIX_PATH, sr=fp.sample_rate, mono=True, duration=60.0)
print(f"Loaded {len(y)} samples at {sr} Hz ({len(y)/sr:.1f}s)")

# Extract fingerprints (like identify_track does)
print("Extracting fingerprints...")
raw_fps = fp.extract_fingerprints_from_array(y)
print(f"Extracted {len(raw_fps)} fingerprints")
print(f"Unique hashes: {len(set(f.hash for f in raw_fps))}")

# Test 1: Match directly (like identify_track)
print("\n--- Test 1: Direct match (like identify_track) ---")
matches = matcher._match_fingerprints(raw_fps)
print(f"Matches: {len(matches)}")
for m in matches[:3]:
    print(f"  {m.artist} - {m.title} (conf={m.confidence:.2f}, count={m.match_count})")

# Test 2: With time offset adjustment (like analyze_mix)
print("\n--- Test 2: With time offset (segment_start_ms=0) ---")
adjusted_fps = [
    Fingerprint(hash=f.hash, time_offset_ms=f.time_offset_ms + 0, freq_bin=f.freq_bin)
    for f in raw_fps
]
matches2 = matcher._match_fingerprints(adjusted_fps)
print(f"Matches: {len(matches2)}")
for m in matches2[:3]:
    print(f"  {m.artist} - {m.title} (conf={m.confidence:.2f}, count={m.match_count})")

# Test 3: Via _match_chunked
print("\n--- Test 3: Via _match_chunked ---")
matches3 = matcher._match_chunked(raw_fps)
print(f"Matches: {len(matches3)}")
for m in matches3[:3]:
    print(f"  {m.artist} - {m.title} (conf={m.confidence:.2f}, count={m.match_count})")

# Test 4: Segment at 5 minutes into the mix
print("\n--- Test 4: Segment at 5:00 in mix ---")
y_full, sr = librosa.load(MIX_PATH, sr=fp.sample_rate, mono=True, offset=300.0, duration=60.0)
print(f"Loaded {len(y_full)/sr:.1f}s from 5:00")
fps_5min = fp.extract_fingerprints_from_array(y_full)
print(f"Extracted {len(fps_5min)} fps, {len(set(f.hash for f in fps_5min))} unique hashes")

# Match without adjusting time offsets (should work, like identify_track)
matches4a = matcher._match_fingerprints(fps_5min)
print(f"Direct match: {len(matches4a)} matches")
for m in matches4a[:3]:
    print(f"  {m.artist} - {m.title} (conf={m.confidence:.2f}, count={m.match_count})")

# Match with absolute time offset (like analyze_mix does)
offset_ms = 300_000  # 5 minutes
fps_5min_abs = [
    Fingerprint(hash=f.hash, time_offset_ms=f.time_offset_ms + offset_ms, freq_bin=f.freq_bin)
    for f in fps_5min
]
matches4b = matcher._match_fingerprints(fps_5min_abs)
print(f"With absolute offset: {len(matches4b)} matches")
for m in matches4b[:3]:
    print(f"  {m.artist} - {m.title} (conf={m.confidence:.2f}, count={m.match_count})")
