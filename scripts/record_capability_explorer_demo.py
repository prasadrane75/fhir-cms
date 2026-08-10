#!/usr/bin/env python3
"""Record the Capability Explorer detailed demonstration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from record_capability_demo import (  # noqa: E402
    check_health,
    convert_webm_to_mp4,
    ensure_patient_fhir,
    record_demo,
)

DEFAULT_OUTPUT = ROOT / "docs" / "demo" / "capability_explorer.mp4"


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Capability Explorer demo video")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output-dir", default=str(ROOT / "docs" / "demo"))
    parser.add_argument("--pace", choices=["normal", "slow"], default="slow")
    parser.add_argument("--fast", action="store_true", help="Skip live LangGraph prior auth call")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output_path = Path(args.output)
    if output_path.suffix.lower() != ".mp4":
        output_path = output_path.with_suffix(".mp4")

    check_health(args.base_url)
    print("Ensuring FHIR patient P1001 exists…")
    try:
        ensure_patient_fhir(base_fhir="http://localhost:8080/fhir")
        import json
        import urllib.request

        patient_id = "P1001"
        url = f"http://localhost:8080/fhir/Patient/{patient_id}"
        payload = json.dumps(
            {
                "resourceType": "Patient",
                "id": patient_id,
                "identifier": [{"system": "http://hospital.local/mrn", "value": "1001"}],
                "name": [{"family": "Doe", "given": ["Jane"]}],
                "gender": "female",
                "birthDate": "1968-03-22",
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
    except Exception as exc:
        print(f"Warning: could not ensure patient P1001: {exc}")

    demo_url = f"{args.base_url}/demo/explorer?autoplay=1&record=narrated&fast=1"
    print(f"Recording: {demo_url}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("pip install playwright && playwright install chromium") from exc

    import time

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(output_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        page.goto(demo_url, wait_until="networkidle", timeout=120_000)
        page.wait_for_selector("#tourBtn", timeout=30_000)
        page.click("#tourBtn")
        print("Tour started, waiting for completion…", flush=True)
        try:
            page.wait_for_selector("#demo-complete:not(.hidden)", timeout=args.timeout * 1000)
            print("Tour completed.", flush=True)
        except Exception:
            print("Timed out — saving partial recording.", flush=True)
        time.sleep(3)
        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()

    if not video_path:
        raise RuntimeError("No video produced.")

    webm_path = output_dir / "capability_explorer.webm"
    Path(video_path).replace(webm_path)
    print(f"Saved WebM: {webm_path}")

    if convert_webm_to_mp4(webm_path, output_path):
        print(f"Saved MP4: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
