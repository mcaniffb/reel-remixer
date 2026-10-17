"""Reel Remixer engine.

Normalizes each source clip once (vertical 1080x1920, 30fps, matched audio),
then stitches hook + body + ending combinations without re-encoding.
"""
from __future__ import annotations

import csv
import itertools
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".m2ts", ".3gp"}

WIDTH, HEIGHT, FPS = 1080, 1920, 30

FRAMING_FILL = "fill"   # scale up and crop edges (fills the whole screen)
FRAMING_BLUR = "blur"   # fit inside, blurred copy behind it
FRAMING_BARS = "bars"   # fit inside, black bars

MODE_ALL = "all"
MODE_BALANCED = "balanced"

# Hide the console window that would otherwise flash up on Windows.
_POPEN_FLAGS = 0x08000000 if sys.platform == "win32" else 0


class Cancelled(Exception):
    pass


class RemixError(Exception):
    pass


def ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        if found:
            return found
        raise RemixError("Couldn't find ffmpeg. Reinstall the app or install ffmpeg.")


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


@dataclass
class ClipInfo:
    duration: float
    has_audio: bool


def probe(path: Path) -> ClipInfo:
    """Read duration and audio presence from ffmpeg's own output (no ffprobe needed)."""
    proc = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, errors="replace", creationflags=_POPEN_FLAGS,
    )
    out = proc.stderr
    if "Video:" not in out:
        raise RemixError(f"“{path.name}” doesn't look like a video file.")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    duration = 0.0
    if m:
        h, mi, s = m.groups()
        duration = int(h) * 3600 + int(mi) * 60 + float(s)
    return ClipInfo(duration=duration, has_audio="Audio:" in out)


def plan_combos(n_hooks: int, n_bodies: int, n_endings: int, mode: str) -> list[tuple[int, int, Optional[int]]]:
    """Return (hook, body, ending) index triples. Ending is None when there are no endings."""
    if n_hooks < 1 or n_bodies < 1:
        return []
    endings = list(range(n_endings)) if n_endings else [None]

    if mode == MODE_BALANCED and balanced_available(n_hooks, n_bodies, n_endings):
        n = n_hooks
        # Latin square: every hook meets every body once, and each
        # hook, body and ending shows up exactly n times.
        return sorted((h, b, (h + b) % n) for h in range(n) for b in range(n))

    return [(h, b, e) for h, b, e in itertools.product(range(n_hooks), range(n_bodies), endings)]


def balanced_available(n_hooks: int, n_bodies: int, n_endings: int) -> bool:
    return n_hooks == n_bodies == n_endings and n_hooks >= 2


def combo_name(prefix: str, h: int, b: int, e: Optional[int]) -> str:
    code = f"H{h + 1}-B{b + 1}" + (f"-E{e + 1}" if e is not None else "")
    prefix = re.sub(r'[\\/:*?"<>|]+', "", prefix).strip()
    return f"{prefix} {code}" if prefix else code


def _video_filter(framing: str) -> str:
    fit = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease"
    if framing == FRAMING_FILL:
        core = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}"
    elif framing == FRAMING_BARS:
        core = f"{fit},pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black"
    else:  # blur
        return (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
            f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.08[bgb];"
            f"[fg]{fit}[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,fps={FPS},setsar=1,format=yuv420p[v]"
        )
    return f"[0:v]{core},fps={FPS},setsar=1,format=yuv420p[v]"


ProgressFn = Callable[[float, str], None]  # (fraction 0..1, message)


@dataclass
class Job:
    hooks: list[Path]
    bodies: list[Path]
    endings: list[Path]
    out_dir: Path
    mode: str = MODE_ALL
    framing: str = FRAMING_FILL
    prefix: str = ""
    quality_crf: int = 18
    _cancel: bool = field(default=False, repr=False)
    _proc: Optional[subprocess.Popen] = field(default=None, repr=False)

    def cancel(self) -> None:
        self._cancel = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    # ------------------------------------------------------------------ helpers
    def _check(self) -> None:
        if self._cancel:
            raise Cancelled()

    def _run(self, args: list[str], duration: float = 0.0,
             on_frac: Optional[Callable[[float], None]] = None) -> int:
        """Run ffmpeg; returns the last reported video frame count."""
        self._check()
        frames = 0
        cmd = [ffmpeg_path(), "-hide_banner", "-y", "-nostdin", "-progress", "pipe:1", "-nostats", *args]
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace", creationflags=_POPEN_FLAGS,
        )
        # Drain stderr in the background so ffmpeg never blocks on a full pipe.
        err_lines: list[str] = []
        import threading
        t = threading.Thread(target=lambda: err_lines.extend(self._proc.stderr), daemon=True)
        t.start()
        for line in self._proc.stdout:
            if line.startswith("frame="):
                try:
                    frames = int(line.split("=", 1)[1])
                except ValueError:
                    pass
            if on_frac and duration > 0 and line.startswith("out_time_us="):
                try:
                    us = int(line.split("=", 1)[1])
                    on_frac(min(1.0, us / 1e6 / duration))
                except ValueError:
                    pass
        code = self._proc.wait()
        t.join(timeout=2)
        self._proc = None
        self._check()
        if code != 0:
            tail = "".join(err_lines[-8:]).strip()
            raise RemixError(f"ffmpeg failed:\n{tail}")
        return frames

    def _normalize(self, src: Path, video_dst: Path, audio_dst: Path,
                   info: ClipInfo, on_frac) -> None:
        # Pass 1: video only, re-framed to vertical at a fixed frame rate.
        frames = self._run([
            "-i", str(src), "-filter_complex", _video_filter(self.framing), "-map", "[v]", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(self.quality_crf),
            "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-g", str(FPS * 2), "-video_track_timescale", "15360",
            "-map_metadata", "-1", str(video_dst),
        ], info.duration, on_frac)
        if frames <= 0:
            raise RemixError(f"Couldn't read any video frames from “{src.name}”.")

        # Pass 2: audio as raw PCM, trimmed or padded to the exact video length,
        # so cuts between segments are seamless with no drift.
        samples = round(frames / FPS * 48000)
        src_audio = ["-i", str(src), "-map", "0:a:0"] if info.has_audio else \
                    ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        self._run([*src_audio, "-af",
                   f"aresample=48000:async=1:first_pts=0,apad,atrim=end_sample={samples}",
                   "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(audio_dst)])

    def _concat(self, parts: list[tuple[Path, Path]], dst: Path, work: Path) -> None:
        lst = work / "concat.txt"
        with lst.open("w", encoding="utf-8") as f:
            for video, _ in parts:
                f.write("file '" + str(video).replace("'", "'\\''") + "'\n")
        audio_in: list[str] = []
        for _, audio in parts:
            audio_in += ["-i", str(audio)]
        n = len(parts)
        joined = "".join(f"[{i + 1}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
        # Video is copied untouched; only the (tiny) audio track is encoded.
        self._run(["-f", "concat", "-safe", "0", "-i", str(lst), *audio_in,
                   "-filter_complex", joined, "-map", "0:v", "-map", "[a]",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                   "-movflags", "+faststart", str(dst)])

    # --------------------------------------------------------------------- run
    def run(self, progress: ProgressFn = lambda f, m: None) -> list[Path]:
        if not self.hooks or not self.bodies:
            raise RemixError("Add at least one hook and one body clip.")
        combos = plan_combos(len(self.hooks), len(self.bodies), len(self.endings), self.mode)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        sources = [("hook", i, p) for i, p in enumerate(self.hooks)] + \
                  [("body", i, p) for i, p in enumerate(self.bodies)] + \
                  [("ending", i, p) for i, p in enumerate(self.endings)]

        progress(0.0, "Checking clips…")
        infos = {}
        for kind, i, p in sources:
            self._check()
            if not p.exists():
                raise RemixError(f"Can't find “{p.name}”. Was it moved?")
            infos[(kind, i)] = probe(p)

        total_src = sum(max(i.duration, 0.1) for i in infos.values())
        # Normalizing is ~95% of the work; stitching is the rest.
        NORM_SHARE = 0.95
        done_src = 0.0
        work = Path(tempfile.mkdtemp(prefix="reelremixer-"))
        try:
            normed: dict[tuple[str, int], tuple[Path, Path]] = {}
            for n, (kind, i, p) in enumerate(sources, 1):
                info = infos[(kind, i)]
                label = {"hook": "hook", "body": "body", "ending": "ending"}[kind]
                msg = f"Preparing {label} {i + 1} ({n}/{len(sources)}): {p.name}"
                dst = (work / f"{kind}{i}.mp4", work / f"{kind}{i}.wav")
                base = done_src
                self._normalize(p, dst[0], dst[1], info,
                                lambda fr, base=base, d=max(info.duration, 0.1), msg=msg:
                                progress(NORM_SHARE * (base + fr * d) / total_src, msg))
                normed[(kind, i)] = dst
                done_src += max(info.duration, 0.1)

            outputs: list[Path] = []
            rows = []
            for n, (h, b, e) in enumerate(combos, 1):
                name = combo_name(self.prefix, h, b, e)
                progress(NORM_SHARE + (1 - NORM_SHARE) * (n - 1) / len(combos),
                         f"Stitching {name} ({n}/{len(combos)})")
                parts = [normed[("hook", h)], normed[("body", b)]]
                if e is not None:
                    parts.append(normed[("ending", e)])
                dst = self.out_dir / f"{name}.mp4"
                self._concat(parts, dst, work)
                outputs.append(dst)
                dur = sum(infos[k].duration for k in
                          [("hook", h), ("body", b)] + ([("ending", e)] if e is not None else []))
                rows.append([dst.name, self.hooks[h].name, self.bodies[b].name,
                             self.endings[e].name if e is not None else "", f"{dur:.1f}"])

            with (self.out_dir / "remix-key.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Reel", "Hook", "Body", "Ending", "Length (sec)"])
                w.writerows(rows)

            progress(1.0, f"Done. {len(outputs)} reels saved.")
            return outputs
        finally:
            shutil.rmtree(work, ignore_errors=True)


def main(argv: Optional[list[str]] = None) -> int:
    """Command-line use: remixer.engine HOOKS_DIR BODIES_DIR [ENDINGS_DIR] OUT_DIR [--balanced] [--framing fill|blur|bars]"""
    import argparse
    ap = argparse.ArgumentParser(description="Combine hook, body and ending clips into every reel variation.")
    ap.add_argument("hooks"); ap.add_argument("bodies"); ap.add_argument("endings"); ap.add_argument("out")
    ap.add_argument("--balanced", action="store_true")
    ap.add_argument("--framing", default=FRAMING_FILL, choices=[FRAMING_FILL, FRAMING_BLUR, FRAMING_BARS])
    ap.add_argument("--prefix", default="")
    a = ap.parse_args(argv)

    def files(d):
        return sorted(p for p in Path(d).iterdir() if is_video(p))

    job = Job(files(a.hooks), files(a.bodies), files(a.endings), Path(a.out),
              mode=MODE_BALANCED if a.balanced else MODE_ALL, framing=a.framing, prefix=a.prefix)
    last = [-1]

    def show(f, m):
        pct = int(f * 100)
        if pct != last[0]:
            last[0] = pct
            print(f"{pct:3d}%  {m}", flush=True)
    job.run(show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
