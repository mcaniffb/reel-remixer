import sys

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        # Used by the automated build to confirm the bundled ffmpeg works.
        import subprocess
        from remixer import engine
        exe = engine.ffmpeg_path()
        out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        ok = "libx264" in out
        print(f"ffmpeg: {exe}\nlibx264: {'yes' if ok else 'MISSING'}")
        sys.exit(0 if ok else 1)
    from remixer.app import main
    main()
