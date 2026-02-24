# xscribe

**Download and transcribe any online video in minutes.**

Turn any video or audio file into a clean, timestamped markdown transcript. Just point xscribe at a file, YouTube URL, or stream URL and get a readable transcript — no cloud services, no subscriptions, everything runs locally on your machine.

Powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

## Install

```bash
pip install xscribe
```

Missing dependencies (ffmpeg, yt-dlp) are detected automatically — xscribe will offer to install them for you on first run.

Optionally, pre-download the transcription model so your first transcription is fast:

```bash
xscribe setup
```

## Quick start

**Transcribe a video file on your computer:**

```bash
xscribe interview.mp4
```

This creates `interview.md` in your current folder with the full transcript and timestamps.

**Transcribe a YouTube video:**

```bash
xscribe "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

**Transcribe an online video stream:**

```bash
xscribe "https://stream.example.com/video/playlist.m3u8"
```

xscribe will download the media first, then transcribe it.

## Usage examples

```bash
# Transcribe a podcast episode
xscribe episode-42.mp3

# Transcribe a lecture recording
xscribe lecture.mov

# Transcribe a YouTube video URL
xscribe "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Use a more accurate model (slower but better for tricky audio)
xscribe meeting.mp4 -m large-v3

# Save the transcript to a specific file
xscribe keynote.mp4 -o keynote-notes.md

# Force a specific language instead of auto-detect
xscribe video.mp4 -l es

# Force URL downloads to convert to mp3
xscribe "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --audio-format mp3

# If YouTube blocks anonymous requests, pass browser cookies
xscribe "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --cookies-from-browser chrome

# Force URL downloads to keep video-first behavior
xscribe "https://stream.example.com/video/playlist.m3u8" --download-mode video

# List videos detected on a page and pick one by index
xscribe "https://example.com/page-with-embeds" --list-videos
xscribe "https://example.com/page-with-embeds" --video-index 2

# Transcribe multiple files at once
xscribe recording1.mp4 recording2.mp4 recording3.mp4

# Pre-download a specific model
xscribe setup -m large-v3
```

**Supported file types:** mp4, mp3, wav, mov, mkv, webm, m4a, flac, ogg, and anything else ffmpeg can read.

## How to get an .m3u8 URL from any website

Most streaming videos use .m3u8 playlist URLs behind the scenes. Here's how to find them:

1. Open the website with the video in Chrome or any browser
2. Right-click anywhere on the page and select **Inspect** (or press `F12`)
3. Click the **Network** tab in the developer tools panel
4. Play the video on the page
5. In the Network tab's filter/search bar, type `.m3u8`
6. You'll see one or more requests appear — right-click the URL and select **Copy URL**
7. Paste it into xscribe: `xscribe "https://...your-copied-url.m3u8"`

## Options

| Flag | Description |
|------|-------------|
| `-m, --model` | Whisper model size (see below) |
| `-l, --lang` | Force language code (e.g. `en`, `es`, `fr`, `de`, `ja`) |
| `--download-mode` | For URL inputs, choose `audio` (default) or `video` download behavior |
| `--audio-format` | For URL inputs, download/convert to one format: `best`, `mp3`, `m4a`, `wav`, `opus`, `vorbis`, `flac` |
| `--list-videos` | For URL inputs, list extractable videos with 1-based indexes and exit |
| `--video-index` | For URL inputs with multiple detected videos, pick one index to transcribe |
| `--cookies-from-browser` | For URL inputs, pass browser cookies to `yt-dlp` (for site-gated/blocked videos) |
| `-o, --output` | Custom output file path |
| `-v, --version` | Show version |

## Model sizes

| Model | Flag | Best for |
|-------|------|----------|
| Tiny | `-m tiny` | Quick and dirty, when you just need the gist |
| Base | *(default)* | General use, good balance of speed and quality |
| Small | `-m small` | Better accuracy, still reasonably fast |
| Medium | `-m medium` | High accuracy for important transcripts |
| Large | `-m large-v3` | Best possible accuracy, but slowest |

The model downloads automatically the first time you use it and gets cached for future runs. Use `xscribe setup -m <model>` to pre-download.

## Output format

xscribe saves transcripts as markdown files with timestamps:

```markdown
# Transcription

**Source:** `interview.mp4`

---

**[00:03]** Hello and welcome to the show.

**[00:07]** Today we're joined by a special guest...

**[01:24]** Let's dive into the first topic.
```

## License

MIT
