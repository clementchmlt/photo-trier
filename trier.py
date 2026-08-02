#!/usr/bin/env python3
"""
Photo Trier — sort photos with keyboard shortcuts (AZERTY Mac)
Dependency: pip install Pillow

Run with: python trier.py
"""
from __future__ import annotations

import json
import subprocess
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    from PIL import Image, ImageTk, ExifTags
except ImportError:
    print("Pillow is required: pip install Pillow", file=sys.stderr)
    sys.exit(1)

import tkinter as tk
from tkinter import messagebox, simpledialog

HistoryEntry = tuple[Path, Path, int, str | None, int, str | None]

# ── configuration ────────────────────────────────────────────────────────────
# Number-row keys on an AZERTY Mac keyboard (unshifted)
KEYS  = ["&", "é", '"', "'", "(", "§", "è", "!", "ç", "à", ")"]
INBOX = "à trier"   # source subfolder (created automatically)
KEYMAP_FILE = ".photo_trier_keys.json"

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic",
    ".heif", ".avif", ".jfif", ".ico", ".ppm", ".pgm", ".pbm", ".pnm", ".dib",
    ".icns", ".ras", ".sgi", ".rgb", ".rgba",
}
VIDEO_EXTS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".mpeg",
    ".mpg", ".mts", ".m2ts", ".3gp", ".3g2", ".ogv", ".ts", ".vob", ".mxf",
    ".dv", ".f4v", ".asf", ".rm", ".rmvb",
}
EXTS = IMAGE_EXTS | VIDEO_EXTS

# ── palette ───────────────────────────────────────────────────────────────────
BG       = "#111111"
PANEL    = "#181818"
CARD     = "#222222"
CARD_HL  = "#1a3355"   # highlighted card (last folder used)
BORDER   = "#2d2d2d"
TXT      = "#e2e2e2"
DIM      = "#555555"
BLUE     = "#58a6ff"
GREEN    = "#3fb950"
BADGE    = "#2c2c2c"
BADGE_HL = "#1d4ed8"
GOLD     = "#d4a72c"


# ── utilities ─────────────────────────────────────────────────────────────────
def _auto_rotate(img: Image.Image) -> Image.Image:
    """Fix EXIF orientation."""
    try:
        exif = img._getexif()  # type: ignore[attr-defined]
        if not exif:
            return img
        for tag_id, val in exif.items():
            if ExifTags.TAGS.get(tag_id) == "Orientation":
                ops = {3: 180, 6: 270, 8: 90}
                if val in ops:
                    img = img.rotate(ops[val], expand=True)
                break
    except Exception:
        pass
    return img


def _safe_dest(p: Path) -> Path:
    """Return p, or p_1, p_2 … if the file already exists."""
    if not p.exists():
        return p
    n = 1
    while True:
        q = p.with_stem(f"{p.stem}_{n}")
        if not q.exists():
            return q
        n += 1


def _cache_key(path: Path) -> str:
    """Stable cache key based on the file's path and metadata."""
    stat = path.stat()
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in path.stem)[:40] or "media"
    return f"{safe_name}_{stat.st_size}_{int(stat.st_mtime)}"


# ── application ───────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Photo Trier")
        self.configure(bg=BG)
        self.geometry("1200x740")
        self.minsize(860, 560)

        # ── state ────────────────────────────────────────────────────────────
        self.base    = Path(__file__).parent / INBOX
        self.base.mkdir(exist_ok=True)
        self.keymap_file = Path(__file__).parent / KEYMAP_FILE
        self.video_cache_dir = Path(tempfile.gettempdir()) / "photo_trier_video_previews"
        self.video_cache_dir.mkdir(exist_ok=True)

        self.photos:  list[Path]              = []
        self.idx:     int                     = 0
        self.key_map: dict[str, str]          = {}   # char → folder name
        self.history: list[HistoryEntry]      = []   # full state, used to undo
        self.last:    str | None              = None  # last folder used
        self.streak:  int                     = 0    # consecutive photos sorted into `last`
        self.locked:  str | None              = None  # folder locked for batch sorting

        self._img_ref = None   # keeps the PhotoImage alive (prevents GC)
        self._video_after_id: str | None      = None
        self._video_proc: subprocess.Popen | None = None
        self._audio_proc: subprocess.Popen | None = None
        self._video_frame_lock                = threading.Lock()
        self._video_pending_frame: bytes | None = None
        self._video_frame_size: tuple[int, int] | None = None
        self._video_generation                = 0
        self._current_video_path: Path | None = None
        self._current_video_size: tuple[int, int] | None = None
        self._video_started_at                = 0.0
        self.video_muted                      = True

        # ── build the interface ─────────────────────────────────────────────
        self._build_panel()
        self._build_main()

        # ── global shortcuts ────────────────────────────────────────────────
        self.bind("<KeyPress>",  self._on_key)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.focus_set()

        self._scan()

    # ═══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_panel(self):
        self.panel = tk.Frame(self, bg=PANEL, width=220)
        self.panel.pack(side="left", fill="y")
        self.panel.pack_propagate(False)

        tk.Label(
            self.panel, text="DOSSIERS",
            bg=PANEL, fg=DIM, font=("Helvetica Neue", 9, "bold"),
            anchor="w", padx=16, pady=16,
        ).pack(fill="x")

        self.cards_frame = tk.Frame(self.panel, bg=PANEL)
        self.cards_frame.pack(fill="x", padx=6)

        # separator
        tk.Frame(self.panel, bg=BORDER, height=1).pack(
            fill="x", padx=12, pady=(12, 8))

        # shortcut legend
        for key, label in [("N", "Nouveau dossier"),
                            ("⎵", "Répéter dernier"),
                            ("⇥", "Verrouiller / retirer"),
                            ("M", "Activer / couper son"),
                            ("→", "Passer"),
                            ("⌫", "Annuler"),
                            ("⎋", "Recharger")]:
            row = tk.Frame(self.panel, bg=PANEL)
            row.pack(fill="x", padx=14, pady=2)
            tk.Label(row, text=key, bg=PANEL, fg=DIM,
                     font=("Helvetica Neue", 11), width=4, anchor="w").pack(side="left")
            tk.Label(row, text=label, bg=PANEL, fg=DIM,
                     font=("Helvetica Neue", 10), anchor="w").pack(side="left")

        # push the stats label to the bottom
        tk.Frame(self.panel, bg=PANEL).pack(fill="both", expand=True)

        self.lbl_stats = tk.Label(
            self.panel, text="",
            bg=PANEL, fg=DIM,
            font=("Helvetica Neue", 10),
            padx=16, pady=14, anchor="w", justify="left",
        )
        self.lbl_stats.pack(fill="x")

        self._cards: dict[str, dict] = {}  # folder → widgets

    def _rebuild_cards(self):
        """Recreate the folder cards."""
        for w in self.cards_frame.winfo_children():
            w.destroy()
        self._cards.clear()

        if not self.key_map:
            tk.Label(
                self.cards_frame,
                text="Créez des sous-dossiers\ndans « " + INBOX + " »",
                bg=PANEL, fg=DIM, font=("Helvetica Neue", 10),
                pady=12, justify="center",
            ).pack(fill="x")
            return

        for key in KEYS:
            if key not in self.key_map:
                continue
            folder = self.key_map[key]
            card = tk.Frame(self.cards_frame, bg=CARD, cursor="hand2")
            card.pack(fill="x", pady=2)

            badge = tk.Label(card, text=key, bg=BADGE, fg=TXT,
                             font=("Helvetica Neue", 13, "bold"),
                             width=2, pady=6, padx=8)
            badge.pack(side="left", padx=(6, 4), pady=5)

            name = tk.Label(card, text=folder, bg=CARD, fg=TXT,
                            font=("Helvetica Neue", 12), anchor="w")
            name.pack(side="left", fill="x", expand=True, pady=5)

            streak_lbl = tk.Label(card, text="", bg=CARD, fg=BLUE,
                                  font=("Helvetica Neue", 10, "bold"), padx=8)
            streak_lbl.pack(side="right", pady=5)

            # also clickable (in addition to key shortcuts)
            for w in (card, badge, name, streak_lbl):
                w.bind("<Button-1>", lambda _e, f=folder: self._sort(f))

            self._cards[folder] = dict(
                frame=card, badge=badge, name=name, streak=streak_lbl
            )

    def _refresh_cards(self, active: str | None = None):
        """Update the card highlighting."""
        for folder, ww in self._cards.items():
            hi  = (folder == active)
            bg  = CARD_HL if hi else CARD
            ww["frame"].configure(bg=bg)
            badge_bg = GOLD if folder == self.locked else (BADGE_HL if hi else BADGE)
            ww["badge"].configure(bg=badge_bg)
            ww["name"].configure(bg=bg)
            ww["streak"].configure(
                bg=bg,
                text=("LOCK" if folder == self.locked else "")
                     or (f"×{self.streak}" if hi and self.streak > 1 else ""),
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # PHOTO AREA (right side)
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_main(self):
        right = tk.Frame(self, bg=BG)
        right.pack(side="right", fill="both", expand=True)

        self.canvas = tk.Canvas(right, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self._draw())

        # status bar
        bar = tk.Frame(right, bg=PANEL, height=44)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.lbl_action = tk.Label(
            bar, text="", bg=PANEL, fg=BLUE,
            font=("Helvetica Neue", 11), padx=14)
        self.lbl_action.pack(side="left", fill="y")

        self.lbl_filename = tk.Label(
            bar, text="", bg=PANEL, fg=DIM,
            font=("Helvetica Neue", 10), padx=6)
        self.lbl_filename.pack(side="left", fill="y")

        self.progress_canvas = tk.Canvas(
            bar, bg=PANEL, highlightthickness=0, width=220, height=12
        )
        self.progress_canvas.pack(side="right", fill="y", pady=16)

        self.lbl_progress = tk.Label(
            bar, text="", bg=PANEL, fg=TXT,
            font=("Helvetica Neue", 11, "bold"), padx=14)
        self.lbl_progress.pack(side="right", fill="y")

    def _load_saved_bindings(self) -> dict[str, str]:
        """Load the persisted folder -> key bindings."""
        if not self.keymap_file.exists():
            return {}
        try:
            data = json.loads(self.keymap_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        cleaned: dict[str, str] = {}
        used_keys: set[str] = set()
        for folder, key in data.items():
            if not isinstance(folder, str) or not isinstance(key, str):
                continue
            if key not in KEYS or key in used_keys:
                continue
            cleaned[folder] = key
            used_keys.add(key)
        return cleaned

    def _save_bindings(self, folder_to_key: dict[str, str]):
        """Persist the folder -> key bindings."""
        payload = {folder: folder_to_key[folder] for folder in sorted(folder_to_key)}
        self.keymap_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _assign_keys(self, dirs: list[str]) -> dict[str, str]:
        """Keep existing key bindings and only assign a key to new folders."""
        saved = self._load_saved_bindings()
        folder_to_key = {
            folder: key
            for folder, key in saved.items()
            if folder in dirs
        }
        used_keys = set(folder_to_key.values())
        free_keys = [key for key in KEYS if key not in used_keys]
        for folder in dirs:
            if folder in folder_to_key:
                continue
            if not free_keys:
                break
            folder_to_key[folder] = free_keys.pop(0)
        self._save_bindings(folder_to_key)
        return {key: folder for folder, key in folder_to_key.items()}

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA LOADING
    # ═══════════════════════════════════════════════════════════════════════════
    def _scan(self):
        """Rescan the source folder: photos + subfolders."""
        dirs = sorted(
            d.name for d in self.base.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        self.key_map = self._assign_keys(dirs)
        self.photos = sorted(
            f for f in self.base.iterdir()
            if f.is_file() and f.suffix.lower() in EXTS
        )
        self.idx = 0
        if self.locked and self.locked not in self.key_map.values():
            self.locked = None
        self._rebuild_cards()
        self._refresh_cards(self.last)
        self._draw()
        self._update_bar()

    # ═══════════════════════════════════════════════════════════════════════════
    # DISPLAY
    # ═══════════════════════════════════════════════════════════════════════════
    def _draw(self):
        """Draw the current photo on the canvas."""
        self.canvas.delete("all")
        W = self.canvas.winfo_width()  or 940
        H = self.canvas.winfo_height() or 640

        if not self.photos or self.idx >= len(self.photos):
            if self.history:
                msg = "Toutes les photos sont triées ✓"
            elif not self.key_map:
                msg = (
                    f"Créez des sous-dossiers dans « {INBOX} »\n"
                    "pour définir vos catégories,\n"
                    "puis appuyez sur ⎋ pour recharger."
                )
            else:
                msg = (
                    f"Aucune photo dans « {INBOX} ».\n\n"
                    "Tri pris en charge : images + vidéos courantes"
                )
            self.canvas.create_text(
                W // 2, H // 2, text=msg,
                fill=DIM, font=("Helvetica Neue", 17),
                justify="center",
            )
            self._stop_video_playback()
            return

        path = self.photos[self.idx]
        suffix = path.suffix.lower()
        if suffix in VIDEO_EXTS:
            if not self._draw_video_player(path, W, H):
                self.canvas.create_text(
                    W // 2, H // 2 - 18,
                    text="VIDEO",
                    fill=TXT, font=("Helvetica Neue", 26, "bold"),
                    justify="center",
                )
                self.canvas.create_text(
                    W // 2, H // 2 + 18,
                    text=f"{path.suffix.upper()}  •  aperçu non disponible\ntri et déplacement pris en charge",
                    fill=DIM, font=("Helvetica Neue", 14),
                    justify="center",
                )
            return
        self._stop_video_playback()
        try:
            img = _auto_rotate(Image.open(path))
            img.thumbnail((W - 32, H - 32), Image.LANCZOS)
            self._img_ref = ImageTk.PhotoImage(img)
            self.canvas.create_image(W // 2, H // 2, anchor="center",
                                     image=self._img_ref)
        except Exception as e:
            self.canvas.create_text(
                W // 2, H // 2,
                text=(
                    f"Aperçu indisponible\n{path.name}\n\n"
                    f"{path.suffix.upper()} reconnu, tri possible\n\n{e}"
                ),
                fill=DIM, font=("Helvetica Neue", 14), justify="center",
            )

    def _get_video_preview_path(self, path: Path) -> Path | None:
        """Extract a video preview frame via ffmpeg and cache it."""
        preview_path = self.video_cache_dir / f"{_cache_key(path)}.jpg"
        if preview_path.exists():
            return preview_path
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", str(path),
            "-vf", "thumbnail,scale=1600:-1",
            "-frames:v", "1",
            str(preview_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except Exception:
            return None
        return preview_path if result.returncode == 0 and preview_path.exists() else None

    def _get_video_info(self, path: Path) -> tuple[int, int, float] | None:
        """Return video width, height, and fps."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-of", "json",
            str(path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout or "{}")
            stream = (data.get("streams") or [{}])[0]
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            rate = str(stream.get("r_frame_rate") or "25/1")
            num, den = rate.split("/", 1)
            fps = float(num) / float(den)
            if width <= 0 or height <= 0:
                return None
            return width, height, min(max(fps, 12.0), 30.0)
        except Exception:
            return None

    def _start_audio(self):
        """Start audio playback for the current video (muted by default)."""
        if self.video_muted or not self._current_video_path:
            return
        self._stop_audio()
        elapsed = max(0.0, time.monotonic() - self._video_started_at)
        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel", "quiet",
            "-ss", f"{elapsed:.3f}",
            str(self._current_video_path),
        ]
        try:
            self._audio_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self._audio_proc = None

    def _stop_audio(self):
        """Stop the current audio playback."""
        if not self._audio_proc:
            return
        try:
            self._audio_proc.terminate()
            self._audio_proc.wait(timeout=0.5)
        except Exception:
            try:
                self._audio_proc.kill()
            except Exception:
                pass
        self._audio_proc = None

    def _stop_video_playback(self):
        """Cleanly stop video playback."""
        self._stop_audio()
        self._video_generation += 1
        if self._video_after_id:
            try:
                self.after_cancel(self._video_after_id)
            except Exception:
                pass
            self._video_after_id = None
        if self._video_proc:
            try:
                self._video_proc.terminate()
                self._video_proc.wait(timeout=0.5)
            except Exception:
                try:
                    self._video_proc.kill()
                except Exception:
                    pass
            self._video_proc = None
        with self._video_frame_lock:
            self._video_pending_frame = None
        self._video_frame_size = None
        self._current_video_path = None
        self._current_video_size = None

    def _video_reader(self, path: Path, size: tuple[int, int], generation: int):
        """Read RGB frames from ffmpeg."""
        width, height = size
        frame_bytes = width * height * 3
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(path),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-",
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            return
        self._video_proc = proc
        try:
            while generation == self._video_generation and proc.stdout:
                chunk = proc.stdout.read(frame_bytes)
                if len(chunk) != frame_bytes:
                    break
                with self._video_frame_lock:
                    self._video_pending_frame = chunk
        except Exception:
            pass
        finally:
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            if self._video_proc is proc:
                self._video_proc = None

    def _pump_video_frame(self, fps: float):
        """Update the displayed video frame."""
        interval = max(15, int(1000 / fps))
        payload = None
        size = self._video_frame_size
        with self._video_frame_lock:
            if self._video_pending_frame is not None:
                payload = self._video_pending_frame
                self._video_pending_frame = None
        if payload and size and self._current_video_path:
            try:
                image = Image.frombytes("RGB", size, payload)
                self._img_ref = ImageTk.PhotoImage(image)
                self.canvas.delete("all")
                self.canvas.create_image(
                    self.canvas.winfo_width() // 2,
                    self.canvas.winfo_height() // 2 - 12,
                    anchor="center",
                    image=self._img_ref,
                )
                sound_state = "son actif" if not self.video_muted else "muet"
                self.canvas.create_text(
                    self.canvas.winfo_width() // 2,
                    self.canvas.winfo_height() - 26,
                    text=f"VIDEO {self._current_video_path.suffix.upper()}  •  M pour {('couper' if not self.video_muted else 'activer')} le son  •  {sound_state}",
                    fill=DIM, font=("Helvetica Neue", 12),
                    justify="center",
                )
            except Exception:
                pass
        if self._video_proc or payload is not None:
            self._video_after_id = self.after(interval, lambda: self._pump_video_frame(fps))
        else:
            self._video_after_id = None

    def _draw_video_player(self, path: Path, width: int, height: int) -> bool:
        """Play a video automatically, muted by default."""
        info = self._get_video_info(path)
        if not info:
            return self._draw_video_preview(path, width, height)
        src_w, src_h, fps = info
        target_w = max(64, width - 32)
        target_h = max(64, height - 70)
        aspect = min(target_w / src_w, target_h / src_h)
        frame_size = (max(2, int(src_w * aspect)), max(2, int(src_h * aspect)))
        if self._current_video_path == path and self._current_video_size == frame_size and self._video_proc:
            if not self._video_after_id:
                self._pump_video_frame(fps)
            return True
        self._stop_video_playback()
        self._current_video_path = path
        self._current_video_size = frame_size
        self._video_frame_size = frame_size
        self._video_started_at = time.monotonic()
        generation = self._video_generation
        threading.Thread(
            target=self._video_reader,
            args=(path, frame_size, generation),
            daemon=True,
        ).start()
        if not self.video_muted:
            self._start_audio()
        self._pump_video_frame(fps)
        return True

    def _draw_video_preview(self, path: Path, width: int, height: int) -> bool:
        """Show a video thumbnail when real-time playback isn't available."""
        preview_path = self._get_video_preview_path(path)
        if not preview_path:
            return False
        try:
            img = Image.open(preview_path)
            img.thumbnail((width - 32, height - 70), Image.LANCZOS)
            self._img_ref = ImageTk.PhotoImage(img)
            self.canvas.create_image(width // 2, height // 2 - 12, anchor="center", image=self._img_ref)
            self.canvas.create_text(
                width // 2, height - 26,
                text=f"VIDEO {path.suffix.upper()}",
                fill=DIM, font=("Helvetica Neue", 12),
                justify="center",
            )
            return True
        except Exception:
            return False

    def _update_bar(self):
        """Update the bottom status bar."""
        n = len(self.photos)
        total = n + len(self.history)
        done = len(self.history)

        # progress
        pos = min(self.idx + 1, n) if n else 0
        self.lbl_progress.configure(text=f"{done} / {total}" if total else "—")
        self.progress_canvas.delete("all")
        bar_w = 220
        bar_h = 12
        self.progress_canvas.create_rectangle(
            0, 0, bar_w, bar_h, fill=CARD, outline=BORDER
        )
        fill_w = int((done / total) * bar_w) if total else 0
        if fill_w > 0:
            self.progress_canvas.create_rectangle(
                0, 0, fill_w, bar_h, fill=GREEN, outline=GREEN
            )

        # file name
        fname = self.photos[self.idx].name if self.idx < n else ""
        self.lbl_filename.configure(text=fname)

        # last action + batch-mode hint
        if self.last:
            s = f"  ×{self.streak}" if self.streak > 1 else ""
            mode = f"    ⇥ verrouillé sur {self.locked}" if self.locked else ""
            self.lbl_action.configure(text=f"→ {self.last}{s}    ⎵ pour répéter{mode}")
        elif self.locked:
            self.lbl_action.configure(text=f"⇥ verrouillé sur {self.locked}")
        else:
            self.lbl_action.configure(text="")

        # left panel stats
        stats = [f"{n} restant(s)", f"{done} trié(s) cette session"]
        if n:
            stats.append(f"position {pos} / {n}")
        self.lbl_stats.configure(text="\n".join(stats))

    def _prompt_new_folder(self):
        """Prompt for a name and create a new subfolder in the inbox."""
        name = simpledialog.askstring(
            "Nouveau dossier",
            "Nom du sous-dossier :",
            parent=self,
        )
        if name is None:
            return

        folder = name.strip()
        if not folder:
            messagebox.showerror("Nom invalide", "Le nom du dossier ne peut pas être vide.", parent=self)
            return
        if any(ch in folder for ch in ("/", "\\")):
            messagebox.showerror(
                "Nom invalide",
                "Le nom du dossier ne doit pas contenir '/' ou '\\'.",
                parent=self,
            )
            return

        path = self.base / folder
        if path.exists():
            messagebox.showinfo("Déjà présent", f"Le dossier « {folder} » existe déjà.", parent=self)
            return

        path.mkdir()
        self._scan()

        if folder in self.key_map.values():
            key = next(k for k, v in self.key_map.items() if v == folder)
            self.lbl_action.configure(text=f"+ dossier créé : {folder}    touche {key}")
        else:
            self.lbl_action.configure(
                text=f"+ dossier créé : {folder}    aucune touche libre"
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # ACTIONS
    # ═══════════════════════════════════════════════════════════════════════════
    def _sort(self, folder: str):
        """Move the current photo into folder."""
        if not self.photos or self.idx >= len(self.photos):
            return

        src = self.photos[self.idx]
        dst = _safe_dest(self.base / folder / src.name)
        (self.base / folder).mkdir(exist_ok=True)
        shutil.move(str(src), str(dst))
        self.history.append((src, dst, self.idx, self.last, self.streak, self.locked))

        # update the streak
        self.streak = self.streak + 1 if folder == self.last else 1
        self.last   = folder

        # remove the photo from the list, adjust the index
        self.photos.pop(self.idx)
        if self.idx >= len(self.photos):
            self.idx = max(0, len(self.photos) - 1)

        self._refresh_cards(folder)
        self._draw()
        self._update_bar()

    def _skip(self):
        """Skip to the next photo without sorting."""
        if len(self.photos) < 2:
            return
        self.idx = (self.idx + 1) % len(self.photos)
        self._draw()
        self._update_bar()

    def _undo(self):
        """Undo the last move."""
        if not self.history:
            return
        src, dst, prev_idx, prev_last, prev_streak, prev_locked = self.history.pop()
        if dst.exists():
            shutil.move(str(dst), str(src))
        insert_at = min(prev_idx, len(self.photos))
        self.photos.insert(insert_at, src)
        self.idx = insert_at
        self.last = prev_last
        self.streak = prev_streak
        self.locked = prev_locked
        self._refresh_cards(self.last)
        self._draw()
        self._update_bar()

    def _toggle_lock(self):
        """Lock/unlock the last used folder for batch sorting."""
        if not self.last:
            return
        self.locked = None if self.locked == self.last else self.last
        self._refresh_cards(self.last)
        self._update_bar()

    def _toggle_mute(self):
        """Toggle audio for the current video."""
        self.video_muted = not self.video_muted
        if self._current_video_path:
            if self.video_muted:
                self._stop_audio()
            else:
                self._start_audio()
            self._draw()

    def _on_close(self):
        """Clean up running processes before closing."""
        self._stop_video_playback()
        self.destroy()

    # ═══════════════════════════════════════════════════════════════════════════
    # KEYBOARD
    # ═══════════════════════════════════════════════════════════════════════════
    def _on_key(self, e: tk.Event):
        ch, ks = e.char, e.keysym

        if ks == "space":
            # ⎵  → repeat the last folder (batch shortcut)
            target = self.locked or self.last
            if target:
                self._sort(target)

        elif ks == "Tab":
            # ⇥ → lock or unlock the last used folder
            self._toggle_lock()

        elif ch.lower() == "m":
            # M → toggle video audio
            self._toggle_mute()

        elif ch.lower() == "n":
            # N → create a new subfolder
            self._prompt_new_folder()

        elif ks in ("Right", "Return"):
            # → or Enter → skip without sorting
            self._skip()

        elif ks in ("BackSpace", "Delete"):
            # ⌫ → undo the last move
            self._undo()

        elif ks == "Escape":
            # ⎋  → reload the folder (after adding subfolders)
            self._scan()

        elif ch in self.key_map:
            # AZERTY key → sort into the associated folder
            self._sort(self.key_map[ch])


# ── entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    App().mainloop()
