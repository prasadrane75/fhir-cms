#!/usr/bin/env python3
"""
Record the capability demonstration as a video using Playwright.

Prerequisites:
  pip install playwright
  playwright install chromium

Optional (to convert WebM → MP4):
  brew install ffmpeg

Usage:
  python3 scripts/record_capability_demo.py
  python3 scripts/record_capability_demo.py --pace slow --output docs/demo/capability_journey.mp4

Before recording:
  docker compose up -d
  docker compose exec neo4j cypher-shell -u neo4j -p password -f /import/init.cypher
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "demo"
DEFAULT_BASE_URL = "http://localhost:8000"


def ensure_patient_fhir(base_fhir: str = "http://localhost:8080/fhir") -> None:
    import json
    import urllib.error
    import urllib.request

    patient_id = "P1002"
    url = f"{base_fhir}/Patient/{patient_id}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            if resp.status == 200:
                return
    except urllib.error.HTTPError:
        pass

    payload = json.dumps(
        {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [{"system": "http://hospital.local/mrn", "value": "1002"}],
            "name": [{"family": "Martinez", "given": ["Robert"]}],
            "gender": "male",
            "birthDate": "1965-06-12",
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/fhir+json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=15):
        pass


def check_health(base_url: str) -> None:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=5) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Health check failed: HTTP {resp.status}")
    except Exception as exc:
        raise SystemExit(
            f"API not reachable at {base_url}. Start the stack first:\n  docker compose up -d\n\n{exc}"
        ) from exc


def convert_webm_to_mp4(webm_path: Path, mp4_path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found — keeping WebM only. Install ffmpeg to produce MP4.")
        return False

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(webm_path),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        str(mp4_path),
    ]
    subprocess.run(cmd, check=False)
    return mp4_path.exists() and mp4_path.stat().st_size > 0


def record_demo(base_url: str, output_dir: Path, pace: str, fast: bool, timeout_sec: int) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is required for video recording.\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    demo_url = f"{base_url}/demo?autoplay=1&pace={pace}" + ("&fast=1" if fast else "")

    print(f"Recording: {demo_url}")
    print("This may take 3–8 minutes (LangGraph prior auth step is live).")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(output_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        page.goto(demo_url, wait_until="domcontentloaded", timeout=120_000)
        print("Demo page loaded, waiting for completion…", flush=True)

        try:
            page.wait_for_selector("#demo-complete:not(.hidden)", timeout=timeout_sec * 1000)
        except Exception:
            print("Timed out waiting for demo completion — saving partial recording.")

        time.sleep(3)
        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()

    if not video_path:
        raise RuntimeError("Playwright did not produce a video file.")

    final_webm = output_dir / "capability_journey.webm"
    Path(video_path).replace(final_webm)
    print(f"Saved WebM: {final_webm}")
    return final_webm


def main() -> int:
    parser = argparse.ArgumentParser(description="Record capability demonstration video")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--pace", choices=["normal", "slow"], default="slow")
    parser.add_argument("--fast", action="store_true", help="Skip live LangGraph call for faster recording")
    parser.add_argument("--timeout", type=int, default=900, help="Max seconds to wait for demo completion")
    parser.add_argument("--output", default="docs/demo/capability_journey.mp4")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_path = ROOT / args.output
    if output_path.suffix.lower() != ".mp4":
        output_path = output_path.with_suffix(".mp4")
        print(f"Note: output path normalized to {output_path}")

    check_health(args.base_url)
    print("Ensuring FHIR patient P1002 exists…")
    try:
        ensure_patient_fhir()
    except Exception as exc:
        print(f"Warning: could not ensure patient: {exc}")

    webm_path = record_demo(args.base_url, output_dir, args.pace, args.fast, args.timeout)

    if convert_webm_to_mp4(webm_path, output_path):
        print(f"Saved MP4: {output_path}")
    else:
        print(f"Open WebM in QuickTime/VLC: {webm_path}")

    print("\nDone. Share the MP4 or re-record with QuickTime:")
    print(f"  open {args.base_url}/demo?autoplay=1&pace=slow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
