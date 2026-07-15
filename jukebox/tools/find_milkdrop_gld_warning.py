"""Diagnostic tool: isolate which MilkDrop preset(s) trigger the macOS GLD
"texture unloadable" driver warning:

    UNSUPPORTED (log once): POSSIBLE ISSUE: unit N GLD_TEXTURE_INDEX_2D is
    unloadable and bound to sampler type (Float) - using zero texture
    because texture unloadable

Each preset is probed in its own subprocess: the driver only logs this
diagnostic once per process ("log once"), so testing multiple presets in a
single process would only ever catch the first offender and hide the rest.
Subprocess isolation also protects the scan from presets that crash the
process outright (reported separately from timeouts and Python errors).

Usage:
    uv run python -m jukebox.tools.find_milkdrop_gld_warning --preset "/path/to/one.milk"
    uv run python -m jukebox.tools.find_milkdrop_gld_warning --dir "/path/to/presets" --limit 200
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from pathlib import Path

GLD_WARNING_MARKER = "GLD_TEXTURE_INDEX_2D is unloadable"

_PROBE_FRAMES = 30
_PROBE_FPS = 30
_PROBE_SR = 44100


def _probe_single_preset(preset_path: str, texture_path: str) -> None:
    """Render a few frames of ONE preset. Meant to run in its own subprocess."""
    import numpy as np

    from plugins.video_exporter.layers.milkdrop_layer import MilkDropLayer

    rng = np.random.default_rng(0)
    audio = rng.uniform(-0.3, 0.3, _PROBE_SR).astype(np.float32)

    layer = MilkDropLayer(
        width=320,
        height=240,
        fps=_PROBE_FPS,
        audio=audio,
        sr=_PROBE_SR,
        duration=_PROBE_FRAMES / _PROBE_FPS,
        preset_path=preset_path,
        texture_path=texture_path,
        preset_duration=100.0,  # no rotation mid-probe
        hard_cut_on_beat=False,
        rng_seed=0,
    )
    layer.prerender_gpu_frames()


class ProbeResult:
    """Outcome of probing one preset in a subprocess.

    `crashed` (returncode < 0, killed by a signal e.g. SIGSEGV) and `errored`
    (returncode > 0, an uncaught Python exception) are kept distinct: a slow
    preset that merely needs a longer --timeout must not be conflated with a
    real native crash.
    """

    def __init__(self, triggered: bool, crashed: bool, errored: bool, output: str) -> None:
        self.triggered = triggered
        self.crashed = crashed
        self.errored = errored
        self.output = output

    @property
    def labels(self) -> list[str]:
        labels = []
        if self.triggered:
            labels.append("WARNING")
        if self.crashed:
            labels.append("CRASHED")
        if self.errored:
            labels.append("ERRORED")
        return labels


def probe_preset_in_subprocess(preset_path: str, texture_path: str, timeout: float) -> ProbeResult:
    """Run _probe_single_preset(preset_path) in a fresh subprocess.

    Raises subprocess.TimeoutExpired if the preset doesn't finish in time —
    the caller decides whether that counts as a timeout or a real failure.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "jukebox.tools.find_milkdrop_gld_warning",
            "--probe",
            preset_path,
            "--texture-path",
            texture_path,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout + result.stderr
    return ProbeResult(
        triggered=GLD_WARNING_MARKER in output,
        crashed=result.returncode < 0,
        errored=result.returncode > 0,
        output=output,
    )


def collect_presets(root: Path, limit: int | None, seed: int) -> list[Path]:
    """Collect .milk files under root, deterministically shuffled, capped at limit."""
    presets = sorted(root.rglob("*.milk"))
    rng = random.Random(seed)
    rng.shuffle(presets)
    if limit is not None:
        presets = presets[:limit]
    return presets


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preset", type=Path, help="Test a single .milk file")
    group.add_argument("--dir", type=Path, help="Scan .milk files under this directory")
    group.add_argument(
        "--probe", type=str, help=argparse.SUPPRESS
    )  # internal subprocess entry point
    parser.add_argument("--texture-path", type=str, default="", help="milkdrop_texture_path to use")
    parser.add_argument("--limit", type=int, default=200, help="Max presets to scan under --dir")
    parser.add_argument("--seed", type=int, default=0, help="Shuffle seed for --dir sampling")
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Per-preset subprocess timeout (s). Too short turns slow-to-compile "
        "presets into false-positive timeouts, indistinguishable from a real hang "
        "unless you compare against a longer --timeout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.probe:
        _probe_single_preset(args.probe, args.texture_path)
        return 0

    presets: list[Path]
    if args.preset:
        presets = [args.preset]
    else:
        presets = collect_presets(args.dir, args.limit, args.seed)
        print(f"Scanning {len(presets)} preset(s) under {args.dir} (seed={args.seed})")

    offenders: list[Path] = []
    crashers: list[Path] = []
    errorers: list[Path] = []
    timeouts: list[Path] = []
    outputs: dict[Path, str] = {}

    for i, preset in enumerate(presets, start=1):
        try:
            result = probe_preset_in_subprocess(
                str(preset), args.texture_path, timeout=args.timeout
            )
        except subprocess.TimeoutExpired:
            print(f"[{i}/{len(presets)}] TIMEOUT: {preset.name}")
            timeouts.append(preset)
            continue

        outputs[preset] = result.output
        if result.triggered:
            offenders.append(preset)
        if result.crashed:
            crashers.append(preset)
        if result.errored:
            errorers.append(preset)
        label = ", ".join(result.labels) if result.labels else "ok"
        print(f"[{i}/{len(presets)}] {label}: {preset.name}")

    print("\n=== Summary ===")
    print(f"Tested: {len(presets)}")
    print(f"Triggered GLD texture warning: {len(offenders)}")
    for p in offenders:
        print(f"  - {p}")
        for line in outputs.get(p, "").splitlines():
            if GLD_WARNING_MARKER in line:
                print(f"      {line.strip()}")
    print(f"Crashed (killed by signal, e.g. native segfault): {len(crashers)}")
    for p in crashers:
        print(f"  - {p}")
    print(f"Errored (non-zero exit, uncaught Python exception): {len(errorers)}")
    for p in errorers:
        print(f"  - {p}")
    print(
        f"Timed out (>{args.timeout:.0f}s — may just be slow, re-check with a longer --timeout): "
        f"{len(timeouts)}"
    )
    for p in timeouts:
        print(f"  - {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
