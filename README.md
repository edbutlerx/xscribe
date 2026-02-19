# xscribe

Transcribe video and audio to markdown with timestamps. Powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

## Features

- Transcribe local video/audio files
- Download and transcribe streams (m3u8, etc.) via yt-dlp
- Output as clean markdown with timestamps
- Multiple Whisper model sizes (tiny → large-v3)

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (only needed for stream URLs)

## Install

```bash
# with uv (recommended)
uv tool install xscribe

# with pip
pip install xscribe
```

## Usage

```bash
# transcribe a local file
xscribe video.mp4

# transcribe a stream
xscribe "https://example.com/stream.m3u8"

# use a larger model for better accuracy
xscribe video.mp4 -m large-v3

# custom output path
xscribe video.mp4 -o notes.md
```

### Model sizes

| Model | Speed | Accuracy |
|-------|-------|----------|
| `tiny` | Fastest | Lower |
| `base` | Fast | Good (default) |
| `small` | Medium | Better |
| `medium` | Slow | High |
| `large-v3` | Slowest | Highest |

The model is downloaded automatically on first use and cached locally.

## Output

```markdown
# Transcription

**Source:** `video.mp4`

---

**[00:03]** Hello and welcome to the presentation.

**[00:07]** Today we'll be discussing...
```

## License

MIT
