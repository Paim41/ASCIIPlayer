# ASCII Player

A terminal-based music player that renders audio playback as a green-themed ASCII animation, with a real-time spectrum visualiser and auto-synced lyrics.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Terminal-True--Colour-00C853?style=for-the-badge&logo=gnometerminal&logoColor=white" />
  <img src="https://img.shields.io/badge/Audio-sounddevice-FF6B6B?style=for-the-badge&logo=soundcloud&logoColor=white" />
  <img src="https://img.shields.io/badge/Video-imageio--ffmpeg-FF9F43?style=for-the-badge&logo=ffmpeg&logoColor=white" />
  <img src="https://img.shields.io/badge/Lyrics-lrclib.net-43A047?style=for-the-badge&logo=microphone&logoColor=white" />
</p>

<img width="1897" height="636" alt="image" src="https://github.com/user-attachments/assets/a6588c58-21b9-4dc5-a567-59062ec32a15" />


---

## Features

- **ASCII video rendering** — video frames are resized to terminal dimensions and mapped to ASCII characters by luminance, coloured in the green-to-cyan palette
- **Plasma animation** — a green-family plasma demo plays automatically when no video is provided
- **Spectrum visualiser** — FFT-based frequency display with logarithmic binning and a glowing bar style
- **Synced lyrics** — auto-fetched from [lrclib.net](https://lrclib.net), with fallback to local `.lrc` files in `~/lyrics/`
- **Progress bar** — gradient fill displaying playback position and timestamps

---

## Requirements

- Python 3.10 or higher
- A terminal with 24-bit true-colour support (e.g. Windows Terminal, iTerm2, Kitty, Alacritty)

---

## Installation

```bash
git clone https://github.com/Paim41/ascii-player.git
cd ascii-player
pip install sounddevice soundfile imageio imageio-ffmpeg pillow numpy requests pyfiglet tqdm
```

---

## Usage

**Audio only**
```bash
python asciiplayer.py --audio "song.mp3"
```

**With video**
```bash
python asciiplayer.py --audio "song.mp3" --video "clip.mp4"
```

**With a local lyrics file**
```bash
python asciiplayer.py --audio "song.mp3" --lrc "lyrics.lrc"
```

> Lyrics are fetched automatically if the audio filename is in `Artist - Title` format and no `--lrc` is provided.

---

## Arguments

| Argument | Default | Description |
|---|---|---|
| `--audio` | *(required)* | Path to the audio file (`.mp3`, `.wav`, `.flac`, etc.) |
| `--video` | `None` | Path to a video file. Omit to use the plasma animation |
| `--lrc` | `None` | Path to a local `.lrc` lyrics file |
| `--fps` | `20` | Target render framerate |
| `--start` | `0.0` | Playback start position in seconds |
| `--nosplash` | `False` | Skip the startup splash screen |

---

## Controls

| Key | Action |
|---|---|
| `Ctrl-C` | Quit |

---

## Dependencies

| Package | Purpose |
|---|---|
| `sounddevice` | Audio playback |
| `soundfile` | Audio file decoding |
| `imageio` + `imageio-ffmpeg` | Video frame reading |
| `Pillow` | Image resizing and colour enhancement |
| `numpy` | FFT and pixel operations |
| `requests` | Lyrics API requests |
| `pyfiglet` | Splash screen rendering |

---

## Credits

Built by [@Paim41](https://github.com/Paim41).
<br>
Lyrics provided by [lrclib.net](https://lrclib.net).
