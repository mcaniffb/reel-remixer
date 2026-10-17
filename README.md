# Reel Remixer

Drop in hook, body, and ending clips. Get every combination as a ready-to-post 1080×1920 reel, named so you can tell which pieces are in each one.

## Download

Open https://github.com/mcaniffb/reel-remixer/releases/latest and download:

- **Mac (M1 or newer):** `Reel-Remixer-Mac.zip`
- **Windows:** `Reel-Remixer-Windows.zip`

### First time on a Mac

1. Unzip and drag **Reel Remixer** into your Applications folder.
2. Double-click it. macOS will say it can't verify the developer. Click **Done**.
3. Open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to Reel Remixer.
4. Confirm with your password. From then on it opens normally.

### First time on Windows

1. Unzip the folder somewhere you'll keep it (Documents works).
2. Open the folder and double-click **Reel Remixer.exe**.
3. If a blue "Windows protected your PC" box appears, click **More info → Run anyway**.

Tip: right-click the .exe and choose **Send to → Desktop (create shortcut)**. Keep the .exe inside its folder; it needs the files next to it.

## Using it

1. Drag clips into **Hooks**, **Bodies**, and **Endings** (or use *Add clips…*). You can drop a whole folder. Endings are optional.
2. Drag clips up or down within a column to change their numbering. Select a clip and press Delete to remove it.
3. Choose what to make:
   - **Every combination**: 3 hooks × 3 bodies × 3 endings = 27 reels.
   - **Balanced set**: 9 reels where every hook is paired with every body once, and each hook, body, and ending shows up exactly three times. Needs the same number of clips in each column.
4. Choose framing for any clips that aren't already vertical: fill the screen (crops edges), fit with a blurred background, or fit with black bars.
5. Add a name (like *Paragon Oct*) and click **Make reels**.

Each run lands in its own dated folder with:

- `Paragon Oct H2-B1-E3.mp4` and friends (H = hook, B = body, E = ending, numbered by their order in each column)
- `remix-key.csv`, listing the original file behind every hook, body, and ending in each reel

All clips are converted to 1080×1920 at 30fps with consistent audio, so mixed cameras, frame rates, and clips without sound all join cleanly.

## Releasing a new version (for whoever maintains this)

Every push to `main` builds both apps and publishes them as the newest Release automatically, a few minutes after the push. Share this link with the team; it always points at the current version:

https://github.com/mcaniffb/reel-remixer/releases/latest

## Running from source

```
pip install -r requirements.txt
python run_app.py
```

Command line, no window:

```
python -m remixer.engine hooks/ bodies/ endings/ output/ --balanced --framing blur
```
