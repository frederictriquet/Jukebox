"""Quick diagnostic: test if identify_track works on a known DB track."""
import sys
sys.path.insert(0, "/Users/fred/Code/Jukebox")

from shazamix.database import FingerprintDB
from shazamix.fingerprint import Fingerprinter
from shazamix.matcher import Matcher

DB_PATH = "/Users/fred/.jukebox/jukebox.db"
# Use a track we KNOW is in the DB
TRACK_PATH = "/Users/fred/Music/NORMALIZED/2024-06/Alan Fitzpatrick - Where Haus?.mp3"
TRACK_ID = 2

db = FingerprintDB(DB_PATH)
fp = Fingerprinter()
matcher = Matcher(db, fp)

# 1. Check how many fingerprints this track has in DB
import sqlite3
conn = sqlite3.connect(DB_PATH)
db_fp_count = conn.execute("SELECT COUNT(*) FROM fingerprints WHERE track_id = ?", (TRACK_ID,)).fetchone()[0]
print(f"Track {TRACK_ID} has {db_fp_count} fingerprints in DB")

# 2. Extract fingerprints from the track file
print("Extracting fingerprints from audio file...")
query_fps = fp.extract_fingerprints(TRACK_PATH)
print(f"Extracted {len(query_fps)} fingerprints from file")

# 3. Check hash overlap
query_hashes = set(h.hash for h in query_fps)
db_hashes_for_track = set(
    row[0] for row in conn.execute(
        "SELECT hash FROM fingerprints WHERE track_id = ?", (TRACK_ID,)
    ).fetchall()
)
overlap = query_hashes & db_hashes_for_track
print(f"Query unique hashes: {len(query_hashes)}")
print(f"DB hashes for track {TRACK_ID}: {len(db_hashes_for_track)}")
print(f"Hash overlap: {len(overlap)} ({100*len(overlap)/max(1,len(query_hashes)):.1f}%)")

# 4. Try identify_track
print("\nRunning identify_track...")
matches = matcher.identify_track(TRACK_PATH)
print(f"Matches found: {len(matches)}")
for m in matches[:5]:
    print(f"  track_id={m.track_id} artist={m.artist} title={m.title} "
          f"confidence={m.confidence:.2f} count={m.match_count}")

conn.close()
