#!/usr/bin/env python3
'''
ASCII Music Player with Animation — by github.com/Paim41
──────────────────────────────────────────────────────────
Plays an audio file while:
  1. Rendering a high-resolution ASCII-art animation from a video/image
     (or a built-in plasma demo)
  2. Showing synced lyrics (small, rainbow-coloured, centred)
  3. Displaying a frequency-spectrum visualiser that follows the music

Green-family colour theme throughout (dark green, lime, neon cyan, etc.)

Usage:
    python ascii_music_player.py \
        --audio "song.mp3" \
        --video "clip.mp4" \         # optional – omit for built-in demo
        --lrc   "lyrics.lrc"         # optional – auto-fetched if omitted

Controls: Ctrl-C to quit.

Install deps:
    pip install sounddevice soundfile imageio imageio-ffmpeg pillow \
                numpy requests pyfiglet tqdm
'''

import os, sys, re, shutil, difflib, tempfile, time, argparse, threading
import numpy as np
import sounddevice as sd
import soundfile  as sf
import imageio
import imageio_ffmpeg          # noqa – registers ffmpeg backend
import pyfiglet
import requests
from PIL          import Image, ImageFont, ImageDraw, ImageFilter, ImageEnhance
from tqdm         import tqdm  as ProgressBar            # noqa – kept for compat

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
BLOCKSIZE     = 2048
LYRIC_OFFSET  = 0.0
LRC_FOLDER    = os.path.expanduser("~/lyrics")
FONT_FILE     = "cour.ttf"      # monospace TTF; falls back to default
FONT_SIZE     = 11
BOLDNESS      = 1
BACKGROUND    = 0               # 0 = dark terminal (recommended)

# ASCII density ramp — more characters = finer detail
ASCII_CHARS = np.array(list(" .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"))

# Green-family hue anchor (0.0=red … 0.33=green … 0.5=cyan … 1.0=red)
GREEN_HUE_MIN = 0.28   # dark / forest green
GREEN_HUE_MAX = 0.52   # neon cyan-green

# ═══════════════════════════════════════════════════════════════════════════════
# ANSI HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def rgb(r, g, b, text):
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"

def bg_rgb(r, g, b, text):
    return f"\033[48;2;{r};{g};{b}m\033[38;2;255;255;255m{text}\033[0m"

def clr():
    return "\033[H\033[J"

def cursor_hide():
    sys.stdout.write("\033[?25l"); sys.stdout.flush()

def cursor_show():
    sys.stdout.write("\033[?25h"); sys.stdout.flush()

def hsv_to_rgb(h, s, v):
    """HSV → (R,G,B) each 0-255."""
    h = h % 1.0
    i = int(h * 6)
    f = h * 6 - i
    p = int(255 * v * (1 - s))
    q = int(255 * v * (1 - f * s))
    t_ = int(255 * v * (1 - (1 - f) * s))
    v_ = int(255 * v)
    i %= 6
    return [(v_, t_, p), (q, v_, p), (p, v_, t_), (p, q, v_), (t_, p, v_), (v_, p, q)][i]

def green_rgb(t, brightness=1.0):
    """Return an RGB tuple from the green-family palette. t in [0,1]."""
    hue = GREEN_HUE_MIN + t * (GREEN_HUE_MAX - GREEN_HUE_MIN)
    sat = 0.80 + 0.20 * np.sin(t * np.pi)
    r, g, b = hsv_to_rgb(hue, sat, brightness)
    return r, g, b

def strip_ansi(s):
    return re.sub(r'\033\[[^m]*m', '', s)

def center_line(line, width):
    plain_len = len(strip_ansi(line))
    pad = max(0, (width - plain_len) // 2)
    return " " * pad + line

# ═══════════════════════════════════════════════════════════════════════════════
# OPENING SPLASH — ASCII art banner with github handle
# ═══════════════════════════════════════════════════════════════════════════════
SPLASH_FONT_BIG   = "doom"       # large font for the player name
SPLASH_FONT_SMALL = "doom"    # smaller font for the handle

def render_splash():
    """Render a full green-themed ASCII splash screen and return it as a string."""
    cols, rows = shutil.get_terminal_size((120, 35))

    big_art   = pyfiglet.figlet_format("ASCII PLAYER", font=SPLASH_FONT_BIG)
    small_art = pyfiglet.figlet_format("github.com/Paim41", font=SPLASH_FONT_SMALL)

    lines_big   = big_art.split("\n")
    lines_small = small_art.split("\n")

    def colour_block(lines, hue_start, hue_end):
        coloured = []
        total = max(1, len(lines) - 1)
        for i, ln in enumerate(lines):
            t   = i / total
            hue = hue_start + (hue_end - hue_start) * t
            r, g, b = hsv_to_rgb(hue, 0.85, 0.95)
            pad = max(0, (cols - len(ln)) // 2)
            coloured.append(" " * pad + rgb(r, g, b, ln))
        return coloured

    # Neon green → cyan-green gradient for the title
    c_big   = colour_block(lines_big,   GREEN_HUE_MIN, GREEN_HUE_MAX)
    # Darker green for the handle
    c_small = colour_block(lines_small, 0.30, 0.38)

    divider_char = "═"
    divider = rgb(0, 200, 80, divider_char * cols)

    tag_line = "  ♫  Terminal Music Player  ·  High-Res ASCII Video  ·  Synced Lyrics  ♫  "
    tag_pad  = max(0, (cols - len(tag_line)) // 2)
    c_tag    = " " * tag_pad + rgb(0, 255, 130, tag_line)

    splash_lines = [""] * 2 + c_big + [""] + c_small + [""] + [divider, c_tag, divider] + [""]
    return "\n".join(splash_lines)


def show_splash():
    cursor_hide()
    os.system("cls" if os.name == "nt" else "clear")
    print(render_splash())
    time.sleep(2.8)


# ═══════════════════════════════════════════════════════════════════════════════
# HIGH-QUALITY ASCII FRAME RENDERER
# ═══════════════════════════════════════════════════════════════════════════════

def _build_char_ramp():
    """Pre-compute (brightness → char) lookup array (length 256)."""
    n   = len(ASCII_CHARS)
    idx = (np.arange(256) / 255 * (n - 1)).astype(int)
    return ASCII_CHARS[idx]          # shape (256,)

_CHAR_RAMP = _build_char_ramp()


def frame_to_ansi_hq(frame: np.ndarray, term_cols: int, term_rows: int,
                      hue_shift: float = 0.0) -> list[str]:
    """
    High-resolution coloured ASCII renderer.

    Strategy:
      • Resize the raw video frame so that each terminal character maps to
        exactly one pixel-block (aspect ratio corrected for char cells ≈ 2:1).
      • Apply sharpening + contrast enhancement for crisper details.
      • Map pixel brightness → ASCII density character.
      • Colour each character with the actual pixel colour, shifted into the
        green family so the overall palette stays themed while preserving
        perceptible detail differences (edges, faces, etc.).
    """
    from PIL import Image as PILImage

    pil = PILImage.fromarray(frame).convert("RGB")

    # Terminal character cells are roughly twice as tall as wide.
    # Render at 2× col resolution then sub-sample in X for better detail.
    target_w = term_cols
    target_h = term_rows

    # Resize — LANCZOS keeps sharp edges
    pil = pil.resize((target_w, target_h), PILImage.Resampling.LANCZOS)

    # --- Enhance contrast and sharpness so the ASCII output "reads" clearly ---
    pil = ImageEnhance.Contrast(pil).enhance(1.55)
    pil = ImageEnhance.Sharpness(pil).enhance(2.2)
    pil = ImageEnhance.Brightness(pil).enhance(1.15)

    arr = np.array(pil, dtype=np.uint8)          # (H, W, 3)

    # Luminance for character selection
    luma = (0.299 * arr[:, :, 0].astype(np.float32) +
            0.587 * arr[:, :, 1].astype(np.float32) +
            0.114 * arr[:, :, 2].astype(np.float32)).astype(np.uint8)

    chars = _CHAR_RAMP[luma]   # (H, W) char array

    # Build output lines
    lines = []
    H, W  = arr.shape[:2]
    for y in range(H):
        row_parts = []
        row_chars = chars[y]
        row_rgb   = arr[y]
        for x in range(W):
            ch = row_chars[x]
            pr, pg, pb = int(row_rgb[x, 0]), int(row_rgb[x, 1]), int(row_rgb[x, 2])

            # Shift hue toward green family while preserving relative brightness
            brightness = (0.299 * pr + 0.587 * pg + 0.114 * pb) / 255.0

            # Map brightness to a hue in [GREEN_HUE_MIN, GREEN_HUE_MAX]
            # with a slight shimmer from hue_shift
            t   = brightness
            hue = (GREEN_HUE_MIN + t * (GREEN_HUE_MAX - GREEN_HUE_MIN) + hue_shift * 0.15) % 1.0

            # Saturation: edges (bright/dark extremes) get more vivid
            sat = 0.65 + 0.35 * abs(brightness - 0.5) * 2
            val = max(0.15, brightness)

            r_, g_, b_ = hsv_to_rgb(hue, sat, val)
            row_parts.append(f"\033[38;2;{r_};{g_};{b_}m{ch}\033[0m")
        lines.append("".join(row_parts))
    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO ANIMATION (plasma) — used when no video is supplied
# ═══════════════════════════════════════════════════════════════════════════════
class DemoAnimation:
    def __init__(self):
        self.t = 0.0

    def next_frame(self, h, w):
        self.t += 0.07
        Y, X = np.mgrid[0:h, 0:w]
        cx = w / 2 + np.cos(self.t * 0.7) * w * 0.35
        cy = h / 2 + np.sin(self.t * 0.5) * h * 0.35
        d1 = np.sin(X / 10.0 + self.t)
        d2 = np.sin(Y / 7.0  + self.t * 1.3)
        d3 = np.sin(np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / 9.0 + self.t)
        plasma = (d1 + d2 + d3) / 3.0      # -1 … 1
        frame  = np.zeros((h, w, 3), dtype=np.uint8)
        # Map plasma → green-family colour
        for r_ in range(0, h, max(1, h // 80)):
            for c_ in range(0, w, max(1, w // 160)):
                t_ = float((plasma[r_, c_] + 1) / 2)
                ri, gi, bi = green_rgb(t_, brightness=0.90)
                frame[r_, c_] = (ri, gi, bi)
        return frame


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO SOURCE
# ═══════════════════════════════════════════════════════════════════════════════
class VideoSource:
    def __init__(self, path):
        self.path  = path
        self.reader     = None
        self.frame_iter = None
        self._reset()

    def _reset(self):
        try:
            if self.reader:
                self.reader.close()
        except Exception:
            pass
        self.reader     = imageio.get_reader(self.path, format="ffmpeg")
        self.frame_iter = iter(self.reader)

    def next_frame(self) -> np.ndarray:
        try:
            frame = next(self.frame_iter)
            if frame.ndim == 2:
                frame = np.stack([frame] * 3, axis=-1)
            if frame.shape[-1] == 4:
                frame = frame[:, :, :3]
            return frame.astype(np.uint8)
        except StopIteration:
            self._reset()
            return self.next_frame()
        except Exception as e:
            sys.stderr.write(f"Video frame error: {e}\n")
            time.sleep(1 / 30)
            self._reset()
            return np.zeros((240, 320, 3), dtype=np.uint8)


# ═══════════════════════════════════════════════════════════════════════════════
# LRC HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_lrc(title, artist=""):
    try:
        r = requests.get("https://lrclib.net/api/search",
                         params={"q": f"{title} {artist}".strip()}, timeout=10)
        r.raise_for_status()
        for item in r.json():
            if item.get("syncedLyrics"):
                return item["syncedLyrics"]
    except Exception as e:
        print("LRCLIB fetch failed:", e)
    return None


def find_closest_lrc(song_title, folder):
    if not os.path.isdir(folder):
        return None
    bases   = [os.path.splitext(f)[0] for f in os.listdir(folder) if f.lower().endswith(".lrc")]
    closest = difflib.get_close_matches(song_title, bases, n=1, cutoff=0.4)
    return os.path.join(folder, closest[0] + ".lrc") if closest else None


def parse_lrc(path):
    pat = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = pat.match(line.strip())
            if m:
                mins, secs, txt = m.groups()
                t = int(mins) * 60 + float(secs) + LYRIC_OFFSET
                out.append((max(0.0, t), txt.strip()))
    return sorted(out)


# ═══════════════════════════════════════════════════════════════════════════════
# SPECTRUM VISUALISER — green family
# ═══════════════════════════════════════════════════════════════════════════════
def render_spectrum(chunk, samplerate, columns, height, shimmer_t):
    n = len(chunk)
    if n == 0:
        return [""] * (height + 1)

    win  = np.hanning(n)
    fft  = np.abs(np.fft.rfft(chunk * win))[: n // 2]

    # Log-spaced frequency bins for a more musical-looking spectrum
    log_bins = np.logspace(np.log10(1), np.log10(len(fft) - 1), columns + 1).astype(int)
    log_bins = np.clip(log_bins, 0, len(fft) - 1)
    bands = np.array([
        np.mean(fft[log_bins[i]: max(log_bins[i] + 1, log_bins[i + 1])])
        for i in range(columns)
    ], dtype=float)

    # Smooth & normalise
    if len(bands) > 3:
        kernel = np.array([0.25, 0.5, 0.25])
        bands  = np.convolve(bands, kernel, mode="same")

    peak = np.max(bands)
    if peak > 0:
        bands /= peak
    bands = np.power(bands, 0.55)           # gamma for perceptual balance
    bar_h = (bands * height).astype(int)

    BAR_CHARS = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

    rows = []
    for row in range(height, -1, -1):
        line = []
        for col_i, bh in enumerate(bar_h):
            if row == 0:
                # Baseline — dim teal
                line.append(rgb(0, 80, 60, "─"))
            elif bh >= row:
                # Map column position to green-family hue
                t   = (col_i / max(1, columns) + shimmer_t * 0.04) % 1.0
                hue = GREEN_HUE_MIN + t * (GREEN_HUE_MAX - GREEN_HUE_MIN)
                # Brighter near the top of each bar
                frac = row / max(1, bh)
                val  = 0.55 + 0.45 * (1 - frac)
                sat  = 0.75 + 0.25 * frac
                r_, g_, b_ = hsv_to_rgb(hue, sat, val)

                # Pick block character by how full this row-slice is
                bar_idx = min(len(BAR_CHARS) - 1, int((1 - frac) * len(BAR_CHARS)))
                ch = BAR_CHARS[bar_idx]

                # Top pixel: brighter / "lit" cap
                if row == bh:
                    r_, g_, b_ = hsv_to_rgb(hue, 0.3, 1.0)   # near-white top
                    ch = "▀"

                line.append(rgb(r_, g_, b_, ch))
            else:
                line.append(" ")
        rows.append("".join(line))
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# PROGRESS BAR — green family
# ═══════════════════════════════════════════════════════════════════════════════
def render_progress(play_time, total_time, width, shimmer_t):
    ratio  = max(0.0, min(play_time, total_time)) / max(1.0, total_time)
    bar_w  = max(10, width - 18)
    filled = int(bar_w * ratio)
    empty  = bar_w - filled

    def fmt(s):
        return f"{int(s // 60):02d}:{int(s % 60):02d}"

    # Gradient fill along the bar
    fill_str = ""
    for i in range(filled):
        t   = i / max(1, bar_w)
        r_, g_, b_ = green_rgb(t, brightness=0.85)
        fill_str += rgb(r_, g_, b_, "█")

    head    = rgb(0, 255, 120, "▶")
    tail    = rgb(0, 40, 20, "░" * empty)
    bar     = fill_str + head + tail

    ts_play  = rgb(0, 220, 100, fmt(play_time))
    ts_sep   = rgb(0, 80, 40, " / ")
    ts_total = rgb(0, 160, 80, fmt(total_time))

    return f" {bar} {ts_play}{ts_sep}{ts_total}"


# ═══════════════════════════════════════════════════════════════════════════════
# LYRIC DISPLAY — green-family rainbow
# ═══════════════════════════════════════════════════════════════════════════════
def render_lyric_small(text, width, shimmer_t):
    if not text.strip():
        return []
    out = []
    n   = len(text)
    for i, ch in enumerate(text):
        if not ch.strip():
            out.append(ch)
            continue
        t   = (i / max(1, n) + shimmer_t * 0.03) % 1.0
        r_, g_, b_ = green_rgb(t, brightness=0.95)
        out.append(rgb(r_, g_, b_, ch))

    deco_l = rgb(0, 100, 60, "  ♫  ")
    deco_r = rgb(0, 100, 60, "  ♫  ")
    return [center_line(deco_l + "".join(out) + deco_r, width)]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PLAYER
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="ASCII Music Player — by github.com/Paim41")
    parser.add_argument("--audio",  required=True,        help="Audio file (mp3/wav/flac/…)")
    parser.add_argument("--video",  default=None,         help="Video/image for ASCII animation (optional)")
    parser.add_argument("--lrc",    default=None,         help="LRC lyrics file (optional, auto-fetched)")
    parser.add_argument("--start",  type=float, default=0.0, help="Start time in seconds")
    parser.add_argument("--fps",    type=int,   default=20,  help="Target render FPS (default 20)")
    parser.add_argument("--nosplash", action="store_true",   help="Skip opening splash screen")
    args = parser.parse_args()

    # ── Opening splash ─────────────────────────────────────────────────────────
    if not args.nosplash:
        show_splash()

    # ── Terminal geometry ──────────────────────────────────────────────────────
    term_cols, term_rows = shutil.get_terminal_size((160, 40))
    term_cols = min(320, term_cols)

    SPEC_HEIGHT  = 8          # rows for frequency spectrum
    LYRIC_ROWS   = 2          # rows for lyrics
    PROG_ROWS    = 2          # rows for progress bar + blank
    ANIM_ROWS    = max(10, term_rows - SPEC_HEIGHT - LYRIC_ROWS - PROG_ROWS - 2)
    ANIM_COLS    = term_cols

    # ── Load audio ─────────────────────────────────────────────────────────────
    print(rgb(0, 200, 80, "Loading audio…"))
    audio_data, samplerate = sf.read(args.audio, dtype="float32")
    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=1)
    audio_data /= (np.max(np.abs(audio_data)) + 1e-9)
    total_time  = len(audio_data) / samplerate
    start_idx   = int(args.start * samplerate)

    # ── Load lyrics ────────────────────────────────────────────────────────────
    lyrics_path = args.lrc
    if not lyrics_path:
        base      = os.path.splitext(os.path.basename(args.audio))[0]
        artist_g  = ""
        title_g   = base
        if "-" in base:
            parts    = base.split("-", 1)
            artist_g = parts[0].strip()
            title_g  = parts[1].strip()
        print(rgb(0, 180, 80, f"Fetching lyrics for: {title_g} – {artist_g}"))
        lrc_text = fetch_lrc(title_g, artist_g)
        if lrc_text:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".lrc")
            tmp.write(lrc_text.encode("utf-8")); tmp.close()
            lyrics_path = tmp.name
            print(rgb(0, 255, 100, "  ✓ Synced lyrics fetched"))
        else:
            match = find_closest_lrc(title_g, LRC_FOLDER)
            if match:
                lyrics_path = match
                print(rgb(0, 200, 80, f"  ✓ Using local: {os.path.basename(match)}"))
            else:
                print(rgb(100, 100, 100, "  ✗ No lyrics found – continuing without"))

    lyrics    = parse_lrc(lyrics_path) if lyrics_path else []
    lyric_idx = 0
    for i, (t, _) in enumerate(lyrics):
        if t >= args.start:
            lyric_idx = max(0, i - 1)
            break

    # ── Prepare animation source ───────────────────────────────────────────────
    if args.video:
        print(rgb(0, 200, 80, f"Loading video: {args.video}"))
        video_src = VideoSource(args.video)
        use_demo  = False
    else:
        print(rgb(0, 140, 60, "No video supplied – using built-in plasma demo"))
        demo_anim = DemoAnimation()
        use_demo  = True

    # ── Shared playback state ──────────────────────────────────────────────────
    state = {
        "play_time" : args.start,
        "chunk"     : np.zeros(BLOCKSIZE, dtype=np.float32),
        "lyric_idx" : lyric_idx,
        "shimmer_t" : 0.0,
        "running"   : True,
    }
    state_lock = threading.Lock()
    pos        = [start_idx]

    def callback(outdata, frames, time_info, status):
        if status:
            sys.stderr.write(str(status) + "\n")
        chunk = audio_data[pos[0]: pos[0] + frames]
        if len(chunk) < frames:
            outdata[: len(chunk), 0] = chunk
            outdata[len(chunk):]     = 0
            with state_lock:
                state["running"] = False
            raise sd.CallbackStop
        outdata[:, 0] = chunk
        pt             = pos[0] / samplerate
        pos[0]        += frames
        with state_lock:
            state["chunk"]     = chunk.copy()
            state["play_time"] = pt
            state["shimmer_t"] += 0.05
            if lyrics:
                li = state["lyric_idx"]
                while li + 1 < len(lyrics) and pt >= lyrics[li + 1][0]:
                    li += 1
                state["lyric_idx"] = li

    # ── Start stream ───────────────────────────────────────────────────────────
    stream = sd.OutputStream(
        channels=1, samplerate=samplerate,
        callback=callback, blocksize=BLOCKSIZE, latency="low",
    )

    cursor_hide()
    os.system("cls" if os.name == "nt" else "clear")
    frame_interval = 1.0 / max(1, args.fps)

    try:
        stream.start()

        while True:
            t0 = time.perf_counter()

            with state_lock:
                if not state["running"]:
                    break
                play_time = state["play_time"]
                chunk     = state["chunk"]
                shimmer_t = state["shimmer_t"]
                li        = state["lyric_idx"]

            hue_shift = (play_time * 0.04) % 1.0

            # ── 1. ASCII video frame ──────────────────────────────────────────
            if use_demo:
                raw_frame = demo_anim.next_frame(ANIM_ROWS, ANIM_COLS)
            else:
                raw_frame = video_src.next_frame()

            anim_lines = frame_to_ansi_hq(
                raw_frame, ANIM_COLS, ANIM_ROWS, hue_shift
            )

            # ── 2. Spectrum ───────────────────────────────────────────────────
            spec_lines = render_spectrum(
                chunk, samplerate, term_cols, SPEC_HEIGHT, shimmer_t
            )

            # ── 3. Progress bar ───────────────────────────────────────────────
            prog_line = render_progress(play_time, total_time, term_cols, shimmer_t)

            # ── 4. Lyrics ─────────────────────────────────────────────────────
            cur_lyric   = lyrics[li][1] if lyrics and li < len(lyrics) else ""
            lyric_lines = render_lyric_small(cur_lyric, term_cols, shimmer_t)

            # ── Assemble screen ───────────────────────────────────────────────
            screen = []
            screen += anim_lines[: ANIM_ROWS]
            while len(screen) < ANIM_ROWS:
                screen.append("")
            screen += spec_lines
            screen.append(prog_line)
            screen.append("")
            screen += lyric_lines
            while len(screen) < term_rows:
                screen.append("")

            sys.stdout.write(clr() + "\n".join(screen[: term_rows]))
            sys.stdout.flush()

            # Frame-rate limiter
            elapsed = time.perf_counter() - t0
            sleep   = frame_interval - elapsed
            if sleep > 0:
                time.sleep(sleep)

    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        stream.close()
        cursor_show()
        os.system("cls" if os.name == "nt" else "clear")
        print(rgb(0, 220, 100, "\n  Thanks for listening! ♫  github.com/Paim41\n"))


if __name__ == "__main__":
    main()