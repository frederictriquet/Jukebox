"""Test the new per-segment matching approach."""
import sys
import logging
sys.path.insert(0, "/Users/fred/Code/Jukebox")

logging.basicConfig(level=logging.INFO)

from shazamix.database import FingerprintDB
from shazamix.fingerprint import Fingerprinter, Fingerprint
from shazamix.matcher import Matcher

DB_PATH = "/Users/fred/.jukebox/jukebox.db"
MIX_PATH = "/Users/fred/Music/000 My mixes/lgd live.mp3"

db = FingerprintDB(DB_PATH)
fp = Fingerprinter()
matcher = Matcher(db, fp)

def progress(current, total, message):
    if current >= 0:
        print(f"  [{current}/{total}] {message}")
    else:
        print(f"  {message}")

print("Running analyze_mix with per-segment matching...")
matches, segment_fps = matcher.analyze_mix(
    MIX_PATH,
    segment_duration_sec=60.0,
    overlap_sec=15.0,
    progress_callback=progress,
    max_workers=4,
)

print(f"\n=== Results ===")
print(f"Segments: {len(segment_fps)}")
print(f"Total fps: {sum(len(s) for s in segment_fps)}")
print(f"Tracks found: {len(matches)}")
for m in matches:
    mins = m.query_start_ms // 60000
    secs = (m.query_start_ms % 60000) // 1000
    print(f"  [{mins:02d}:{secs:02d}] {m.artist} - {m.title} "
          f"(conf={m.confidence:.0%}, count={m.match_count}, dur={m.duration_ms/1000:.0f}s)")
