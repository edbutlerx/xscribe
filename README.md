# xscribe

**Download and transcribe any online video in minutes.**

Turn any video or audio file into a clean, timestamped markdown transcript. Just point xscribe at a file or stream URL and get a readable transcript — no cloud services, no subscriptions, everything runs locally on your machine.

Powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

## Install

```bash
pip install xscribe
```

You also need **ffmpeg** installed on your system:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
winget install ffmpeg
```

## Quick start

**Transcribe a video file on your computer:**

```bash
xscribe interview.mp4
```

This creates `interview.md` in your current folder with the full transcript and timestamps.

**Transcribe an online video stream:**

```bash
xscribe "https://stream.example.com/video/playlist.m3u8"
```

xscribe will download the video first, then transcribe it. You'll need [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed for this (`brew install yt-dlp` or `pip install yt-dlp`).

## Usage examples

```bash
# Transcribe a podcast episode you downloaded
xscribe episode-42.mp3

# Transcribe a lecture recording
xscribe lecture.mov

# Transcribe a YouTube stream you grabbed the URL for
xscribe "https://manifest.googlevideo.com/.../playlist.m3u8"

# Use a more accurate model (slower but better for tricky audio)
xscribe meeting.mp4 -m large-v3

# Save the transcript to a specific file
xscribe keynote.mp4 -o keynote-notes.md
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

## Model sizes

xscribe uses OpenAI's Whisper speech recognition. You can choose different model sizes depending on whether you want speed or accuracy:

| Model | Flag | Best for |
|-------|------|----------|
| Tiny | `-m tiny` | Quick and dirty, when you just need the gist |
| Base | *(default)* | General use, good balance of speed and quality |
| Small | `-m small` | Better accuracy, still reasonably fast |
| Medium | `-m medium` | High accuracy for important transcripts |
| Large | `-m large-v3` | Best possible accuracy, but slowest |

The model downloads automatically the first time you use it and gets cached for future runs.

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
