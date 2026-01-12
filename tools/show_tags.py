#!/usr/bin/env python3
"""Display ID3/audio tags from any audio file."""

import sys
from pathlib import Path


def show_tags(filepath: str) -> None:
    """Display all tags from an audio file.

    Args:
        filepath: Path to audio file
    """
    path = Path(filepath)

    if not path.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    try:
        from mutagen import File

        audio = File(filepath)

        if audio is None:
            print(f"Error: Unsupported file format: {filepath}")
            sys.exit(1)

        print(f"\n{'='*60}")
        print(f"File: {path.name}")
        print(f"Path: {path}")
        print(f"{'='*60}\n")

        # Audio info
        if hasattr(audio, "info"):
            print("Audio Info:")
            print(f"  Length: {audio.info.length:.2f} seconds")
            if hasattr(audio.info, "bitrate"):
                print(f"  Bitrate: {audio.info.bitrate // 1000} kbps")
            if hasattr(audio.info, "sample_rate"):
                print(f"  Sample Rate: {audio.info.sample_rate} Hz")
            if hasattr(audio.info, "channels"):
                print(f"  Channels: {audio.info.channels}")
            print()

        # Tags - whitelist approach: only show known text tags
        if audio.tags:
            print("Tags:")

            # ID3v2 text frames and common Vorbis/FLAC tags
            ALLOWED_TAGS = {
                "TIT2",
                "TPE1",
                "TALB",
                "TPE2",
                "TCON",
                "TDRC",
                "TYER",
                "TRCK",
                "TPOS",
                "TCOM",
                "TPUB",
                "TSRC",
                "TENC",
                "TCOP",
                "TBPM",
                "TKEY",
                "TSST",
                "COMM",
                "TXXX",
                "USLT",
                "TIT1",
                "TIT3",
                "TOAL",
                "TOFN",
                "TOLY",
                "TOWN",
                "TRSN",
                "ALBUM",
                "ARTIST",
                "TITLE",
                "ALBUMARTIST",
                "GENRE",
                "DATE",
                "COMMENT",
                "COMPOSER",
                "PUBLISHER",
                "TRACKNUMBER",
                "DISCNUMBER",
                "BPM",
                "KEY",
            }

            # Translation map for ID3v2 codes to readable names
            TAG_NAMES = {
                "TIT2": "Title",
                "TPE1": "Artist",
                "TALB": "Album",
                "TPE2": "Album Artist",
                "TCON": "Genre",
                "TDRC": "Date",
                "TYER": "Year",
                "TRCK": "Track Number",
                "TPOS": "Disc Number",
                "TCOM": "Composer",
                "TPUB": "Publisher",
                "TBPM": "BPM",
                "TKEY": "Key",
                "COMM": "Comment",
                "TIT1": "Content Group",
                "TIT3": "Subtitle",
                "TSST": "Set Subtitle",
            }

            displayed_count = 0
            skipped_count = 0

            for key in sorted(audio.tags.keys()):
                # Extract tag prefix
                key_prefix = key.split(":")[0].upper() if ":" in key else key.upper()

                # Check if it's an allowed text tag
                if key_prefix in ALLOWED_TAGS or key.upper() in ALLOWED_TAGS:
                    value = audio.tags[key]

                    # Convert to string
                    if isinstance(value, list):
                        value_str = ", ".join(str(v) for v in value)
                    else:
                        value_str = str(value)

                    # Truncate if too long
                    if len(value_str) > 100:
                        value_str = value_str[:97] + "..."

                    # Get readable name if available
                    tag_name = TAG_NAMES.get(key_prefix, key)
                    print(f"  {tag_name} ({key}): {value_str}")
                    displayed_count += 1
                else:
                    skipped_count += 1

            if skipped_count > 0:
                print(f"\n  ({skipped_count} binary/proprietary tags skipped)")

        else:
            print("No tags found in file")

        print(f"\n{'='*60}\n")

    except Exception as e:
        print(f"Error reading file: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python show_tags.py <audio_file>")
        print("\nExample:")
        print("  python show_tags.py song.mp3")
        print("  python show_tags.py track.flac")
        sys.exit(1)

    show_tags(sys.argv[1])


if __name__ == "__main__":
    main()
