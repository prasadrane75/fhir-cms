#!/usr/bin/env python3
"""
Generate voice commentary and merge it with the capability demo video.

Uses macOS `say` for text-to-speech and ffmpeg for audio/video muxing.

Usage:
  python3 scripts/add_voice_commentary.py
  python3 scripts/add_voice_commentary.py --voice Samantha --video docs/demo/capability_journey.mp4
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from narration.capability_demo_narration import NARRATION_SEGMENTS as JOURNEY_NARRATION  # noqa: E402
from narration.capability_explorer_narration import NARRATION_SEGMENTS as EXPLORER_NARRATION  # noqa: E402

NARRATION_MODULES = {
    "journey": JOURNEY_NARRATION,
    "explorer": EXPLORER_NARRATION,
}

DEFAULT_VIDEO = ROOT / "docs" / "demo" / "capability_journey.mp4"
DEFAULT_OUTPUT = ROOT / "docs" / "demo" / "capability_journey_narrated.mp4"
SAMPLE_RATE = 44100


def require_tools() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required. Install with: brew install ffmpeg")
    if shutil.which("say") is None:
        raise SystemExit("macOS `say` command is required for text-to-speech.")


def video_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def say_to_wav(text: str, wav_path: Path, voice: str, rate: int) -> None:
    aiff_path = wav_path.with_suffix(".aiff")
    subprocess.run(
        ["say", "-v", voice, "-r", str(rate), "-o", str(aiff_path), text],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff_path), "-ar", str(SAMPLE_RATE), "-ac", "1", str(wav_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    aiff_path.unlink(missing_ok=True)


def make_silence(wav_path: Path, duration_sec: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={SAMPLE_RATE}:cl=mono",
            "-t",
            f"{max(duration_sec, 0):.3f}",
            str(wav_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def concat_wavs(wav_paths: list[Path], output_path: Path) -> None:
    list_file = output_path.with_suffix(".txt")
    list_file.write_text("\n".join(f"file '{path}'" for path in wav_paths))
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(output_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    list_file.unlink(missing_ok=True)


def scale_segment_targets(segments: list[dict], total_video_sec: float) -> list[dict]:
    planned = sum(segment["duration_sec"] for segment in segments)
    ratio = total_video_sec / planned if planned else 1.0
    return [
        {**segment, "duration_sec": segment["duration_sec"] * ratio}
        for segment in segments
    ]


def build_narration_track(
    output_wav: Path,
    voice: str,
    rate: int,
    video_sec: float,
    segments: list[dict],
) -> None:
    scaled = scale_segment_targets(segments, video_sec)
    temp_dir = Path(tempfile.mkdtemp(prefix="cms-narration-"))
    timeline: list[Path] = []

    try:
        for index, segment in enumerate(scaled):
            speech_wav = temp_dir / f"{index:02d}_{segment['id']}_speech.wav"
            silence_wav = temp_dir / f"{index:02d}_{segment['id']}_pad.wav"

            print(f"  Narrating: {segment['id']}", flush=True)
            say_to_wav(segment["text"], speech_wav, voice, rate)

            speech_sec = wav_duration(speech_wav)
            pad_sec = max(segment["duration_sec"] - speech_sec, 0.0)
            make_silence(silence_wav, pad_sec)

            timeline.extend([speech_wav, silence_wav])

        concat_wavs(timeline, output_wav)
    finally:
        for path in temp_dir.glob("*"):
            path.unlink(missing_ok=True)
        temp_dir.rmdir()


def mux_video_audio(video_path: Path, audio_wav: Path, output_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_wav),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            str(output_path),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Add voice commentary to capability demo video")
    parser.add_argument("--video", default=str(DEFAULT_VIDEO))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--narration", choices=["journey", "explorer"], default="journey")
    parser.add_argument("--voice", default="Samantha", help="macOS say voice name")
    parser.add_argument("--rate", type=int, default=178, help="Speech rate for say")
    args = parser.parse_args()

    segments = NARRATION_MODULES[args.narration]
    if args.narration == "explorer" and args.video == str(DEFAULT_VIDEO):
        video_path = ROOT / "docs" / "demo" / "capability_explorer.mp4"
    else:
        video_path = Path(args.video)
    if args.narration == "explorer" and args.output == str(DEFAULT_OUTPUT):
        output_path = ROOT / "docs" / "demo" / "capability_explorer_narrated.mp4"
    else:
        output_path = Path(args.output)
    require_tools()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise SystemExit(f"Video not found: {video_path}")

    duration = video_duration(video_path)
    print(f"Video duration: {duration:.1f}s")
    print(f"Generating narration with voice '{args.voice}'…")

    with tempfile.TemporaryDirectory(prefix="cms-narration-audio-") as tmp:
        narration_wav = Path(tmp) / "narration.wav"
        build_narration_track(narration_wav, args.voice, args.rate, duration, segments)
        print("Merging narration with video…")
        mux_video_audio(video_path, narration_wav, output_path)

    print(f"Saved narrated video: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
