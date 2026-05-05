#!/usr/bin/env python3
"""Check which Piper voices from piper_voices.json are installed locally.

Usage:
  python tools/check_piper_voices.py
  python tools/check_piper_voices.py --catalog piper_voices.json --voices-dir voices

The script accepts both layouts:
  voices/en_US-joe-medium.onnx
  voices/en/en_US/joe/medium/en_US-joe-medium.onnx
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def companion_json(path: Path) -> Path:
    return Path(str(path) + ".json")


def candidate_paths(voices_dir: Path, entry: dict) -> list[Path]:
    paths: list[Path] = []
    for rel_path in (entry.get("files") or {}).keys():
        rel_text = str(rel_path)
        if not rel_text.endswith(".onnx"):
            continue
        rel = Path(rel_text)
        paths.append(voices_dir / rel)
        paths.append(voices_dir / rel.name)
    seen = set()
    out = []
    for p in paths:
        k = str(p)
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="piper_voices.json")
    parser.add_argument("--voices-dir", default="voices")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    voices_dir = Path(args.voices_dir)

    if not catalog_path.exists():
        print(f"Catalogue not found: {catalog_path}")
        return 1

    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("Invalid catalogue: expected a JSON object.")
        return 1

    installed = []
    incomplete = []
    by_language: dict[str, list[str]] = {}

    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        lang = (entry.get("language") or {}).get("code", "unknown")
        for candidate in candidate_paths(voices_dir, entry):
            if candidate.exists():
                if companion_json(candidate).exists():
                    installed.append((lang, key, candidate))
                    by_language.setdefault(lang, []).append(key)
                else:
                    incomplete.append((lang, key, candidate))
                break

    print(f"Catalogue voices: {len(data)}")
    print(f"Installed complete voices: {len(installed)}")
    print(f"Incomplete voices missing .onnx.json: {len(incomplete)}")
    print()

    if by_language:
        print("Installed languages:")
        for lang in sorted(by_language):
            voices = ", ".join(sorted(by_language[lang])[:6])
            more = " ..." if len(by_language[lang]) > 6 else ""
            print(f"  {lang}: {voices}{more}")
    else:
        print("No complete voices found.")

    if incomplete:
        print("\nIncomplete voices:")
        for lang, key, path in incomplete[:20]:
            print(f"  {lang} / {key}: missing {path.name}.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
