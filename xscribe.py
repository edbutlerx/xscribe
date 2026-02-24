#!/usr/bin/env python3
"""Video transcription CLI. Transcribes video/audio files to markdown with timestamps."""

__version__ = "0.3.3"

import argparse
import glob
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Track active spinner and temp dirs for clean Ctrl+C shutdown
_active_spinner = None
_temp_dirs = []


def _cleanup_and_exit(signum=None, frame=None):
    """Clean up resources and exit on Ctrl+C."""
    global _active_spinner
    if _active_spinner:
        _active_spinner.stop("Interrupted")
        _active_spinner = None
    for d in _temp_dirs:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
    print("\nCancelled.", file=sys.stderr)
    sys.exit(130)


signal.signal(signal.SIGINT, _cleanup_and_exit)


# --- Dependency management ---

def _pip_install(package: str) -> bool:
    """Install a Python package using pip."""
    print(f"Installing {package}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def _get_system_install_hint(package: str) -> str:
    """Return an install command hint based on the platform."""
    system = platform.system()
    if system == "Darwin":
        return f"brew install {package}"
    elif system == "Linux":
        return f"sudo apt install {package}"
    elif system == "Windows":
        return f"winget install {package}"
    return f"Install {package} from https://ffmpeg.org"


def check_dependencies(need_ytdlp: bool = False):
    """Check and auto-install missing dependencies."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        hint = _get_system_install_hint("ffmpeg")
        print("ffmpeg is required but not installed.")
        answer = input(f"Run `{hint}`? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            result = subprocess.run(hint.split())
            if result.returncode != 0:
                print("Failed to install ffmpeg. Please install it manually.", file=sys.stderr)
                sys.exit(1)
            print("✓ ffmpeg installed")
        else:
            print(f"Please install ffmpeg manually: {hint}", file=sys.stderr)
            sys.exit(1)

    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        print("faster-whisper is required but not installed.")
        answer = input("Install it now? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            if _pip_install("faster-whisper"):
                print("✓ faster-whisper installed")
            else:
                print("Failed to install. Run manually: pip install faster-whisper", file=sys.stderr)
                sys.exit(1)
        else:
            print("Run manually: pip install faster-whisper", file=sys.stderr)
            sys.exit(1)

    if need_ytdlp and not shutil.which("yt-dlp"):
        print("yt-dlp is required for online URLs (including YouTube) but not installed.")
        answer = input("Install it now? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            if _pip_install("yt-dlp"):
                print("✓ yt-dlp installed")
            else:
                print("Failed to install. Run manually: pip install yt-dlp", file=sys.stderr)
                sys.exit(1)
        else:
            print("Run manually: pip install yt-dlp", file=sys.stderr)
            sys.exit(1)


# --- Helpers ---

def is_stream_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://") or path.endswith(".m3u8")


def download_stream(
    url: str, output_dir: str, audio_format: str, download_mode: str, video_index: int | None
) -> str:
    """Download an online URL using yt-dlp and return the output file path."""
    global _active_spinner
    output_path = os.path.join(output_dir, "%(title).180B.%(ext)s")
    cmd = [
        "yt-dlp",
        "-o",
        output_path,
        "--restrict-filenames",
        "--windows-filenames",
    ]
    if video_index is None:
        cmd.append("--no-playlist")
    else:
        cmd.extend(["--playlist-items", str(video_index)])

    if download_mode == "video":
        cmd.extend(["-f", "best"])
        if audio_format != "best":
            print("Note: --audio-format is ignored when --download-mode video is used.")
    else:
        if audio_format == "best":
            cmd.extend(["-f", "bestaudio/best"])
        else:
            cmd.extend(["-f", "bestaudio/best", "--extract-audio", "--audio-format", audio_format])
    cmd.append(url)

    spinner = ProgressSpinner("Downloading stream...")
    _active_spinner = spinner
    spinner.start()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        spinner.stop("✗ Download failed")
        _active_spinner = None
        print(f"yt-dlp error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    spinner.stop("✓ Download complete")
    _active_spinner = None

    candidates = []
    for pattern in ("*.mp3", "*.m4a", "*.webm", "*.ogg", "*.opus", "*.wav", "*.mp4", "*.mkv"):
        candidates.extend(glob.glob(os.path.join(output_dir, pattern)))
    if candidates:
        return max(candidates, key=os.path.getmtime)

    print("Error: could not find downloaded file", file=sys.stderr)
    sys.exit(1)


def list_url_videos(url: str) -> list[dict]:
    """List extractable media entries for a URL using yt-dlp metadata."""
    cmd = ["yt-dlp", "--flat-playlist", "--dump-single-json", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"yt-dlp error: {result.stderr}", file=sys.stderr)
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("Could not parse yt-dlp metadata output.", file=sys.stderr)
        return []

    entries = data.get("entries")
    if entries and isinstance(entries, list):
        out = []
        for i, entry in enumerate(entries, start=1):
            title = entry.get("title") or "(untitled)"
            video_id = entry.get("id") or ""
            entry_url = entry.get("webpage_url") or entry.get("url") or ""
            out.append({"index": i, "title": title, "id": video_id, "url": entry_url})
        return out

    title = data.get("title") or "(untitled)"
    video_id = data.get("id") or ""
    entry_url = data.get("webpage_url") or data.get("url") or url
    return [{"index": 1, "title": title, "id": video_id, "url": entry_url}]


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


# --- Core ---

def transcribe(file_path: str, model_size: str, language: str | None = None) -> list[dict]:
    """Transcribe a file using faster-whisper. Returns list of segments."""
    global _active_spinner
    from faster_whisper import WhisperModel

    duration = get_audio_duration(file_path)

    spinner = ProgressSpinner("Loading model...")
    _active_spinner = spinner
    spinner.start()
    model = WhisperModel(model_size, device="auto", compute_type="auto")
    spinner.stop(f"✓ Model loaded: {model_size}")
    _active_spinner = None

    transcribe_opts = {"beam_size": 5}
    if language:
        transcribe_opts["language"] = language

    spinner = ProgressSpinner("Transcribing...", total=duration)
    _active_spinner = spinner
    spinner.start()

    try:
        segments_gen, info = model.transcribe(file_path, **transcribe_opts)
    except Exception as e:
        spinner.stop("✗ Transcription failed")
        _active_spinner = None
        print(f"Error: could not transcribe file: {e}", file=sys.stderr)
        return []

    segments = []
    try:
        for segment in segments_gen:
            segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
            })
            spinner.update(segment.end)
    except Exception as e:
        spinner.stop("✗ Transcription failed")
        _active_spinner = None
        print(f"Error during transcription: {e}", file=sys.stderr)
        return []

    lang = language or info.language
    spinner.stop(f"✓ Transcription complete ({lang})")
    _active_spinner = None

    return segments


def write_markdown(segments: list[dict], output_path: str, source: str):
    """Write transcription segments to a markdown file."""
    with open(output_path, "w") as f:
        f.write("# Transcription\n\n")
        f.write(f"**Source:** `{source}`\n\n")
        f.write("---\n\n")

        for seg in segments:
            ts = format_timestamp(seg["start"])
            f.write(f"**[{ts}]** {seg['text']}\n\n")

    print(f"✓ Saved to: {output_path}")


def process_single(
    source: str,
    model_size: str,
    output: str | None,
    language: str | None,
    audio_format: str,
    download_mode: str,
    video_index: int | None,
):
    """Process a single input file or online URL."""
    is_stream = is_stream_url(source)
    check_dependencies(need_ytdlp=is_stream)
    temp_dir = None

    try:
        if is_stream:
            temp_dir = tempfile.mkdtemp(prefix="xscribe_")
            _temp_dirs.append(temp_dir)
            file_path = download_stream(source, temp_dir, audio_format, download_mode, video_index)
        else:
            file_path = os.path.abspath(source)
            if not os.path.isfile(file_path):
                print(f"Error: file not found: {file_path}", file=sys.stderr)
                return False

        if output:
            output_path = os.path.abspath(output)
        else:
            base_name = Path(file_path).stem if is_stream else Path(source).stem
            output_path = os.path.join(os.getcwd(), f"{base_name}.md")

        segments = transcribe(file_path, model_size, language)

        if not segments:
            print(f"No speech detected in: {source}", file=sys.stderr)
            return False

        write_markdown(segments, output_path, source)
        return True

    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            if temp_dir in _temp_dirs:
                _temp_dirs.remove(temp_dir)


def cmd_setup(args):
    """Pre-download a Whisper model."""
    check_dependencies()
    from faster_whisper import WhisperModel

    spinner = ProgressSpinner(f"Downloading model: {args.model}...")
    global _active_spinner
    _active_spinner = spinner
    spinner.start()
    WhisperModel(args.model, device="auto", compute_type="auto")
    spinner.stop(f"✓ Model ready: {args.model}")
    _active_spinner = None
    print("You're all set! Run `xscribe <file>` to transcribe.")


def main():
    parser = argparse.ArgumentParser(
        prog="xscribe",
        description="Download and transcribe any video to markdown with timestamps.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"xscribe {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # setup subcommand
    setup_parser = subparsers.add_parser("setup", help="Pre-download a Whisper model")
    setup_parser.add_argument("-m", "--model", default="base",
                              choices=["tiny", "base", "small", "medium", "large-v3"],
                              help="Model to download (default: base)")

    # default transcription arguments (on main parser)
    parser.add_argument("input", nargs="*", help="File path(s) or URL(s) to transcribe")
    parser.add_argument("-o", "--output", help="Output markdown file path (only for single file)")
    parser.add_argument("-m", "--model", default="base",
                        choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper model size (default: base)")
    parser.add_argument("-l", "--lang",
                        help="Force language code (e.g. en, es, fr, de, ja). Auto-detected if not set.")
    parser.add_argument(
        "--audio-format",
        default="best",
        choices=["best", "mp3", "m4a", "wav", "opus", "vorbis", "flac"],
        help="For URL inputs, download/convert to this audio format (default: best).",
    )
    parser.add_argument(
        "--download-mode",
        default="audio",
        choices=["audio", "video"],
        help="For URL inputs, choose audio-first (default) or video-first downloading.",
    )
    parser.add_argument(
        "--list-videos",
        action="store_true",
        help="For URL inputs, list extractable videos with indexes and exit.",
    )
    parser.add_argument(
        "--video-index",
        type=int,
        help="For URL inputs with multiple videos, pick a 1-based index to download/transcribe.",
    )

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    if args.output and len(args.input) > 1:
        print("Error: --output can only be used with a single input file.", file=sys.stderr)
        sys.exit(1)

    if args.video_index is not None and args.video_index < 1:
        print("Error: --video-index must be >= 1.", file=sys.stderr)
        sys.exit(1)
    if args.video_index is not None:
        non_url_inputs = [source for source in args.input if not is_stream_url(source)]
        if non_url_inputs:
            print("Error: --video-index can only be used with URL inputs.", file=sys.stderr)
            sys.exit(1)

    if args.list_videos:
        listed_any = False
        for source in args.input:
            if not is_stream_url(source):
                print(f"Skipping non-URL input: {source}")
                continue
            check_dependencies(need_ytdlp=True)
            entries = list_url_videos(source)
            print(f"\n{source}")
            if not entries:
                print("  No extractable videos found.")
                continue
            listed_any = True
            for item in entries:
                vid = f" | id={item['id']}" if item["id"] else ""
                url_hint = f" | {item['url']}" if item["url"] else ""
                print(f"  [{item['index']}] {item['title']}{vid}{url_hint}")
        if not listed_any:
            sys.exit(1)
        return

    success = 0
    total = len(args.input)

    for i, source in enumerate(args.input):
        if total > 1:
            print(f"\n[{i + 1}/{total}] {source}")
        if process_single(
            source, args.model, args.output, args.lang, args.audio_format, args.download_mode, args.video_index
        ):
            success += 1

    if total > 1:
        print(f"\nDone: {success}/{total} files transcribed.")

    if success == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
