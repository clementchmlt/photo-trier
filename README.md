# Photo Trier

Minimalist desktop app to quickly sort photos and videos with keyboard
shortcuts on macOS. Personal tool, built for an AZERTY Mac keyboard — the
interface labels are in French.

## Features

- Automatically detects files to sort in the `à trier/` ("to sort") folder
- Maps subfolders to AZERTY Mac keys
- Moves the current media file to the right folder with a single keystroke
- Locks the last used folder for sorting a run of similar photos
- Plays videos inline in the app
- Sound off by default, can be toggled on
- Progress bar while sorting
- Persists key → folder associations between runs

## Dependencies

- Python 3.11+
- [Pillow](https://python-pillow.org/)
- `ffmpeg`
- `ffplay`
- `ffprobe`

On macOS with Homebrew:

```bash
brew install ffmpeg
python3 -m pip install -r requirements.txt
```

## Running the app

```bash
python3 trier.py
```

On first launch, the app automatically creates the `à trier/` folder if it
doesn't exist yet.

## Usage

1. Drop the photos and videos to sort into `à trier/`
2. Create the destination subfolders inside `à trier/`
3. Launch the app
4. Use the shortcuts shown in the left-hand column

### Shortcuts

- `& é " ' ( § è ! ç à )`: send the current media to the associated folder
- `Space`: repeat the last folder
- `Tab`: lock or unlock the last used folder
- `M`: toggle sound for the current video
- `N`: create a new subfolder
- `Right arrow` or `Enter`: skip to the next media file
- `Delete`: undo the last move
- `Esc`: reload folders and media

## Supported formats

The app sorts common image and video formats, including:

- Images: `jpg`, `jpeg`, `png`, `gif`, `bmp`, `tiff`, `webp`, `heic`, `heif`, `avif`
- Videos: `mp4`, `mov`, `m4v`, `avi`, `mkv`, `webm`, `mpeg`, `mpg`, `mts`, `m2ts`, `3gp`

Sorting is based on the file extension. Previews depend on Pillow for images
and `ffmpeg` for videos.

## Notes

- The `à trier/` folder is excluded from Git to avoid publishing personal
  media.
- Key bindings are saved to `.photo_trier_keys.json`, also excluded from Git.
- Built for local personal use; it doesn't depend on any remote service.

## License

Personal side project, shared as-is under the [MIT License](LICENSE).
