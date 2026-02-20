"""Check if cached fingerprints are valid."""
import sys
sys.path.insert(0, "/Users/fred/Code/Jukebox")
import numpy as np

cache_path = "/Users/fred/.jukebox/cue_cache/853c763cfa2ec0646bf41dd43ab0d4db5b8bb0ccdf3ff4b8990cab47d4413123_fingerprints.npz"

data = np.load(cache_path)
hashes = data["hashes"]
time_offsets = data["time_offsets"]
freq_bins = data["freq_bins"]

print(f"Cached fingerprints: {len(hashes)}")
print(f"Hash range: {hashes.min()} - {hashes.max()}")
print(f"Time range: {time_offsets.min()}ms - {time_offsets.max()}ms ({time_offsets.max()/60000:.1f} min)")
print(f"Freq bin range: {freq_bins.min()} - {freq_bins.max()}")
print(f"Unique hashes: {len(np.unique(hashes))}")
print(f"Sample hashes: {hashes[:10]}")

# Check hash distribution
print(f"\nHash distribution:")
print(f"  < 1B: {np.sum(hashes < 1_000_000_000)}")
print(f"  1B-2B: {np.sum((hashes >= 1_000_000_000) & (hashes < 2_000_000_000))}")
print(f"  > 2B: {np.sum(hashes >= 2_000_000_000)}")
