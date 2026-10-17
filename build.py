"""Builds the app for whatever OS this runs on: python build.py

Mac  -> dist/Reel-Remixer-Mac.zip     (Apple Silicon, M1 and later)
Win  -> dist/Reel-Remixer-Windows.zip
"""
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "Reel Remixer"
DIST = ROOT / "dist"


def main() -> None:
    sep = ";" if sys.platform == "win32" else ":"
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", NAME,
        "--icon", str(ROOT / "assets" / "icon.png"),
        "--add-data", f"{ROOT / 'assets'}{sep}assets",
        "--collect-binaries", "imageio_ffmpeg",
        "--collect-data", "imageio_ffmpeg",
        # Trim Qt modules the app never uses to keep the download small.
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "tkinter",
    ]
    if sys.platform == "darwin":
        args += ["--target-arch", "arm64",
                 "--osx-bundle-identifier", "com.laulimadigital.reelremixer"]
    args.append(str(ROOT / "run_app.py"))
    subprocess.run(args, check=True, cwd=ROOT)

    if sys.platform == "darwin":
        out = DIST / "Reel-Remixer-Mac.zip"
        # ditto keeps the .app bundle's permissions and signatures intact.
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(DIST / f"{NAME}.app"), str(out)], check=True)
    else:
        label = "Windows" if sys.platform == "win32" else platform.system()
        out = DIST / f"Reel-Remixer-{label}"
        shutil.make_archive(str(out), "zip", DIST, NAME)
        out = out.with_suffix(".zip")
    print(f"Built {out}")


if __name__ == "__main__":
    main()
