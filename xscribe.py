#!/usr/bin/env python3
"""Video transcription CLI. Transcribes video/audio files to markdown with timestamps."""

__version__ = "0.2.0"

import argparse
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
        print("yt-dlp is required for stream URLs but not installed.")
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


def download_stream(url: str, output_dir: str) -> str:
    """Download a stream URL using yt-dlp and return the output file path."""
    global _active_spinner
    output_path = os.path.join(output_dir, "downloaded_video.%(ext)s")
    cmd = ["yt-dlp", "-o", output_path, "--no-playlist", url]

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

    for f in os.listdir(output_dir):
        if f.startswith("downloaded_video"):
            return os.path.join(output_dir, f)

    print("Error: could not find downloaded file", file=sys.stderr)
    sys.exit(1)


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


def process_single(source: str, model_size: str, output: str | None, language: str | None):
    """Process a single input file or stream URL."""
    is_stream = is_stream_url(source)
    check_dependencies(need_ytdlp=is_stream)
    temp_dir = None

    try:
        if is_stream:
            temp_dir = tempfile.mkdtemp(prefix="xscribe_")
            _temp_dirs.append(temp_dir)
            file_path = download_stream(source, temp_dir)
        else:
            file_path = os.path.abspath(source)
            if not os.path.isfile(file_path):
                print(f"Error: file not found: {file_path}", file=sys.stderr)
                return False

        if output:
            output_path = os.path.abspath(output)
        else:
            base_name = Path(source).stem if not is_stream else "transcription"
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
    parser.add_argument("input", nargs="*", help="File path(s) or stream URL(s) to transcribe")
    parser.add_argument("-o", "--output", help="Output markdown file path (only for single file)")
    parser.add_argument("-m", "--model", default="base",
                        choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper model size (default: base)")
    parser.add_argument("-l", "--lang",
                        help="Force language code (e.g. en, es, fr, de, ja). Auto-detected if not set.")

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

    success = 0
    total = len(args.input)

    for i, source in enumerate(args.input):
        if total > 1:
            print(f"\n[{i + 1}/{total}] {source}")
        if process_single(source, args.model, args.output, args.lang):
            success += 1

    if total > 1:
        print(f"\nDone: {success}/{total} files transcribed.")

    if success == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
