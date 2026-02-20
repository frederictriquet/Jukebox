"""Test _match_chunked on cached fingerprints."""
import sys
import logging
sys.path.insert(0, "/Users/fred/Code/Jukebox")

logging.basicConfig(level=logging.INFO)

import numpy as np
from shazamix.database import FingerprintDB
from shazamix.fingerprint import Fingerprinter, Fingerprint
from shazamix.matcher import Matcher

DB_PATH = "/Users/fred/.jukebox/jukebox.db"
CACHE_PATH = "/Users/fred/.jukebox/cue_cache/853c763cfa2ec0646bf41dd43ab0d4db5b8bb0ccdf3ff4b8990cab47d4413123_fingerprints.npz"

# Load cached fps
data = np.load(CACHE_PATH)
fps = [
    Fingerprint(hash=int(data["hashes"][i]), time_offset_ms=int(data["time_offsets"][i]), freq_bin=int(data["freq_bins"][i]))
    for i in range(len(data["hashes"]))
]
print(f"Loaded {len(fps)} cached fingerprints")

db = FingerprintDB(DB_PATH)
matcher = Matcher(db, Fingerprinter())

# Test 1: _match_chunked with 60s chunks
print("\n--- Test 1: _match_chunked (60s chunks) ---")
matches = matcher._match_chunked(fps, chunk_duration_ms=60_000)
print(f"Total matches: {len(matches)}")
for m in matches[:5]:
    print(f"  [{m.query_start_ms/1000:.0f}s] {m.artist} - {m.title} (conf={m.confidence:.2f}, count={m.match_count})")

# Test 2: Take a specific chunk manually (around 5:00)
print("\n--- Test 2: Manual chunk around 5:00 (280-340s) ---")
chunk_fps = [fp for fp in fps if 280_000 <= fp.time_offset_ms < 340_000]
print(f"Chunk has {len(chunk_fps)} fps, {len(set(f.hash for f in chunk_fps))} unique hashes")
if chunk_fps:
    chunk_matches = matcher._match_fingerprints(chunk_fps)
    print(f"Matches: {len(chunk_matches)}")
    for m in chunk_matches[:3]:
        print(f"  {m.artist} - {m.title} (conf={m.confidence:.2f}, count={m.match_count})")

# Test 3: Try a few different time windows
print("\n--- Test 3: Scanning every 2 minutes ---")
for start_min in range(0, 78, 2):
    start_ms = start_min * 60_000
    end_ms = start_ms + 60_000
    window_fps = [fp for fp in fps if start_ms <= fp.time_offset_ms < end_ms]
    if len(window_fps) < 50:
        continue
    unique_h = len(set(f.hash for f in window_fps))
    window_matches = matcher._match_fingerprints(window_fps)
    if window_matches:
        top = window_matches[0]
        print(f"  [{start_min}:00-{start_min+1}:00] {len(window_fps)} fps, {unique_h} hashes -> "
              f"{len(window_matches)} matches | best: {top.artist} - {top.title} "
              f"(count={top.match_count}, conf={top.confidence:.2f})")
