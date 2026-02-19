#!/usr/bin/env python3
"""Video transcription CLI. Transcribes video/audio files to markdown with timestamps."""

import argparse
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


def is_stream_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://") or path.endswith(".m3u8")


def download_stream(url: str, output_dir: str) -> str:
    """Download a stream URL using yt-dlp and return the output file path."""
    output_path = os.path.join(output_dir, "downloaded_video.%(ext)s")
    cmd = [
        "yt-dlp",
        "-o", output_path,
        "--no-playlist",
        url,
    ]
    spinner = ProgressSpinner("Downloading stream...")
    spinner.start()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        spinner.stop("✗ Download failed")
        print(f"yt-dlp error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    spinner.stop("✓ Download complete")

    # Find the downloaded file
    for f in os.listdir(output_dir):
        if f.startswith("downloaded_video"):
            return os.path.join(output_dir, f)

    print("Error: could not find downloaded file", file=sys.stderr)
    sys.exit(1)


SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def get_audio_duration(file_path: str) -> float | None:
    """Get duration of a media file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except (ValueError, FileNotFoundError):
        return None


class ProgressSpinner:
    """Spinner with percentage progress on a single line."""

    def __init__(self, label: str, total: float | None = None):
        self.label = label
        self.total = total
        self.current = 0.0
        self._stop = threading.Event()
        self._frame = 0
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def start(self):
        self._thread.start()

    def update(self, value: float):
        self.current = value

    def _spin(self):
        while not self._stop.is_set():
            frame = SPINNER_FRAMES[self._frame % len(SPINNER_FRAMES)]
            if self.total and self.total > 0:
                pct = min(self.current / self.total * 100, 100)
                sys.stdout.write(f"\r{frame} {self.label} {pct:.0f}%")
            else:
                sys.stdout.write(f"\r{frame} {self.label}")
            sys.stdout.flush()
            self._frame += 1
            self._stop.wait(0.1)

    def stop(self, final_message: str = ""):
        self._stop.set()
        self._thread.join()
        sys.stdout.write(f"\r\033[K{final_message}\n")
        sys.stdout.flush()


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def transcribe(file_path: str, model_size: str) -> list[dict]:
    """Transcribe a file using faster-whisper. Returns list of segments."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("Error: faster-whisper is not installed.", file=sys.stderr)
        print("Install it with: pip install faster-whisper", file=sys.stderr)
        sys.exit(1)

    duration = get_audio_duration(file_path)

    spinner = ProgressSpinner("Loading model...", total=None)
    spinner.start()
    model = WhisperModel(model_size, device="auto", compute_type="auto")
    spinner.stop(f"✓ Model loaded: {model_size}")

    spinner = ProgressSpinner("Transcribing...", total=duration)
    spinner.start()
    segments_gen, info = model.transcribe(file_path, beam_size=5)

    segments = []
    for segment in segments_gen:
        segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
        })
        spinner.update(segment.end)

    spinner.stop(f"✓ Transcription complete ({info.language})")

    return segments


def write_markdown(segments: list[dict], output_path: str, source: str):
    """Write transcription segments to a markdown file."""
    with open(output_path, "w") as f:
        f.write(f"# Transcription\n\n")
        f.write(f"**Source:** `{source}`\n\n")
        f.write("---\n\n")

        for seg in segments:
            ts = format_timestamp(seg["start"])
            f.write(f"**[{ts}]** {seg['text']}\n\n")

    print(f"✓ Saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Transcribe video/audio to markdown with timestamps.")
    parser.add_argument("input", help="File path or stream URL (m3u8, etc.) to transcribe")
    parser.add_argument("-o", "--output", help="Output markdown file path (default: <input_name>.md)")
    parser.add_argument("-m", "--model", default="base", choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper model size (default: base)")
    args = parser.parse_args()

    source = args.input
    temp_dir = None

    try:
        if is_stream_url(source):
            temp_dir = tempfile.mkdtemp(prefix="xscribe_")
            file_path = download_stream(source, temp_dir)
        else:
            file_path = os.path.abspath(source)
            if not os.path.isfile(file_path):
                print(f"Error: file not found: {file_path}", file=sys.stderr)
                sys.exit(1)

        # Determine output path
        if args.output:
            output_path = os.path.abspath(args.output)
        else:
            base_name = Path(source).stem if not is_stream_url(source) else "transcription"
            output_path = os.path.join(os.getcwd(), f"{base_name}.md")

        segments = transcribe(file_path, args.model)

        if not segments:
            print("No speech detected.", file=sys.stderr)
            sys.exit(1)

        write_markdown(segments, output_path, source)

    finally:
        # Clean up temp files
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
