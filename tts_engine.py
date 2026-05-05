"""Offline Piper Text-to-Speech helpers for Gemma 4 Omni-Translator.

This module deliberately avoids cloud TTS services.

Current design, cleaned up:
  - The Piper catalogue file is always named ``piper_voices.json``.
  - Voice models are discovered under ``voices/``.
  - The .env file no longer contains per-language voice mappings.
  - Missing voices are non-fatal: translation text still works and the UI gets
    a friendly warning.

Expected local setup:
  project/
    piper_voices.json              # full Piper catalogue, optional but preferred
    voices/
      en_US-joe-medium.onnx        # flat layout is supported
      en_US-joe-medium.onnx.json
      it/it_IT/riccardo/x_low/...  # official nested layout is also supported

Useful environment variables kept intentionally minimal:
  PIPER_BIN=piper
  PIPER_MODEL_DIR=voices
  PIPER_QUALITY_PREFERENCE=medium,high,low,x_low
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional


LANGUAGE_PREFIXES = {
    "Arabic": "ar",
    "Bulgarian": "bg",
    "Catalan": "ca",
    "Czech": "cs",
    "Welsh": "cy",
    "Danish": "da",
    "German": "de",
    "Greek": "el",
    "English": "en",
    "Spanish": "es",
    "Basque": "eu",
    "Farsi": "fa",
    "Persian": "fa",
    "Finnish": "fi",
    "French": "fr",
    "Icelandic": "is",
    "Hindi": "hi",
    "Indonesian": "id",
    "Italian": "it",
    "Hebrew": "he",
    "Hungarian": "hu",
    "Georgian": "ka",
    "Kazakh": "kk",
    "Kurmanji Kurdish": "ku",
    "Kurdish": "ku",
    "Luxembourgish": "lb",
    "Latvian": "lv",
    "Nepali": "ne",
    "Dutch": "nl",
    "Norwegian": "no",
    "Malayalam": "ml",
    "Polish": "pl",
    "Portuguese": "pt",
    "Romanian": "ro",
    "Russian": "ru",
    "Slovak": "sk",
    "Slovenian": "sl",
    "Albanian": "sq",
    "Serbian": "sr",
    "Swedish": "sv",
    "Swahili": "sw",
    "Telugu": "te",
    "Turkish": "tr",
    "Ukrainian": "uk",
    "Urdu": "ur",
    "Vietnamese": "vi",
    "Chinese": "zh",
    # Kept because the UI may expose them even if Piper has no official voice.
    "Japanese": "ja",
    "Korean": "ko",
}

LANGUAGE_PIPER_CODES = {
    "Arabic": ["ar_JO", "ar"],
    "Bulgarian": ["bg_BG", "bg"],
    "Catalan": ["ca_ES", "ca"],
    "Czech": ["cs_CZ", "cs"],
    "Welsh": ["cy_GB", "cy"],
    "Danish": ["da_DK", "da"],
    "German": ["de_DE", "de"],
    "Greek": ["el_GR", "el"],
    "English": ["en_US", "en_GB", "en"],
    "Spanish": ["es_ES", "es_MX", "es_AR", "es"],
    "Basque": ["eu_ES", "eu"],
    "Farsi": ["fa_IR", "fa"],
    "Persian": ["fa_IR", "fa"],
    "Finnish": ["fi_FI", "fi"],
    "French": ["fr_FR", "fr"],
    "Icelandic": ["is_IS", "is"],
    "Hindi": ["hi_IN", "hi"],
    "Indonesian": ["id_ID", "id"],
    "Italian": ["it_IT", "it"],
    "Hebrew": ["he_IL", "he"],
    "Hungarian": ["hu_HU", "hu"],
    "Georgian": ["ka_GE", "ka"],
    "Kazakh": ["kk_KZ", "kk"],
    "Kurmanji Kurdish": ["ku_TR", "ku"],
    "Kurdish": ["ku_TR", "ku"],
    "Luxembourgish": ["lb_LU", "lb"],
    "Latvian": ["lv_LV", "lv"],
    "Nepali": ["ne_NP", "ne"],
    "Dutch": ["nl_NL", "nl_BE", "nl"],
    "Norwegian": ["no_NO", "no"],
    "Malayalam": ["ml_IN", "ml"],
    "Polish": ["pl_PL", "pl"],
    "Portuguese": ["pt_PT", "pt_BR", "pt"],
    "Romanian": ["ro_RO", "ro"],
    "Russian": ["ru_RU", "ru"],
    "Slovak": ["sk_SK", "sk"],
    "Slovenian": ["sl_SI", "sl"],
    "Albanian": ["sq_AL", "sq"],
    "Serbian": ["sr_RS", "sr"],
    "Swedish": ["sv_SE", "sv"],
    "Swahili": ["sw_CD", "sw"],
    "Telugu": ["te_IN", "te"],
    "Turkish": ["tr_TR", "tr"],
    "Ukrainian": ["uk_UA", "uk"],
    "Urdu": ["ur_PK", "ur"],
    "Vietnamese": ["vi_VN", "vi"],
    "Chinese": ["zh_CN", "zh"],
    "Japanese": ["ja_JP", "ja"],
    "Korean": ["ko_KR", "ko"],
}

CATALOG_FILENAME = "piper_voices.json"


class TTSUserWarning(Exception):
    """Exception carrying a UI-safe message plus optional technical details."""

    def __init__(self, user_message: str, technical_detail: str = ""):
        super().__init__(technical_detail or user_message)
        self.user_message = user_message
        self.technical_detail = technical_detail or user_message


class PiperVoiceNotConfigured(TTSUserWarning):
    pass


class PiperExecutableNotFound(TTSUserWarning):
    pass


class PiperSynthesisFailed(TTSUserWarning):
    pass


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _model_dir() -> Path:
    value = os.getenv("PIPER_MODEL_DIR", "voices").strip() or "voices"
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = _project_root() / path
    return path


def _catalog_path() -> Path:
    return _project_root() / CATALOG_FILENAME


def _model_companion_json(model_path: Path) -> Path:
    return Path(str(model_path) + ".json")


def _validate_model_files_or_none(model_path: Path) -> tuple[Optional[Path], str]:
    if not model_path.exists():
        return None, f"Missing ONNX model: {model_path}"

    json_path = _model_companion_json(model_path)
    if not json_path.exists():
        return None, f"Missing Piper companion JSON: {json_path}"

    return model_path, ""


@lru_cache(maxsize=1)
def _load_voice_catalog() -> dict[str, Any]:
    """Load the local Piper catalogue named piper_voices.json, if present."""

    path = _catalog_path()
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        # A broken catalogue should not prevent text translation.
        return {}


def _quality_preference() -> list[str]:
    raw = os.getenv("PIPER_QUALITY_PREFERENCE", "medium,high,low,x_low").strip()
    values = [v.strip().lower() for v in raw.split(",") if v.strip()]
    return values or ["medium", "high", "low", "x_low"]


def _quality_rank(quality: str) -> int:
    pref = _quality_preference()
    q = (quality or "").strip().lower()
    try:
        return pref.index(q)
    except ValueError:
        return len(pref) + 1


def _voice_entry_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, int, str]:
    key, entry = item
    quality = str(entry.get("quality", ""))
    speaker_count = int(entry.get("num_speakers", 1) or 1)
    # Prefer single-speaker voices for a minimal Piper CLI invocation.
    return (_quality_rank(quality), 0 if speaker_count == 1 else 1, key)


def _catalog_codes_for_language(language_name: str) -> list[str]:
    codes = list(LANGUAGE_PIPER_CODES.get(language_name, []))
    family = LANGUAGE_PREFIXES.get(language_name)
    if family and family not in codes:
        codes.append(family)

    target = language_name.strip().lower()
    for entry in _load_voice_catalog().values():
        if not isinstance(entry, dict):
            continue
        language = entry.get("language", {}) or {}
        code = str(language.get("code", "")).strip()
        family_code = str(language.get("family", "")).strip()
        english_name = str(language.get("name_english", "")).strip().lower()
        native_name = str(language.get("name_native", "")).strip().lower()
        if target in {english_name, native_name}:
            if code and code not in codes:
                codes.append(code)
            if family_code and family_code not in codes:
                codes.append(family_code)

    return codes or ([family] if family else [])


def _catalog_entries_for_language(language_name: str) -> list[tuple[str, dict[str, Any]]]:
    catalog = _load_voice_catalog()
    if not catalog:
        return []

    codes = {c.lower() for c in _catalog_codes_for_language(language_name) if c}
    family = LANGUAGE_PREFIXES.get(language_name, "").lower()
    target = language_name.strip().lower()

    matches: list[tuple[str, dict[str, Any]]] = []
    for key, entry in catalog.items():
        if not isinstance(entry, dict):
            continue
        language = entry.get("language", {}) or {}
        code = str(language.get("code", "")).lower()
        entry_family = str(language.get("family", "")).lower()
        english_name = str(language.get("name_english", "")).lower()
        native_name = str(language.get("name_native", "")).lower()
        aliases = [str(a).lower() for a in entry.get("aliases", []) or []]

        if (
            code in codes
            or entry_family in codes
            or (family and entry_family == family)
            or target in {english_name, native_name}
            or key.lower() in codes
            or any(alias in codes for alias in aliases)
        ):
            matches.append((key, entry))

    return sorted(matches, key=_voice_entry_sort_key)


def _model_paths_from_catalog_entry(entry: dict[str, Any]) -> list[Path]:
    files = entry.get("files", {}) or {}
    candidates: list[Path] = []
    model_dir = _model_dir()

    for rel_path in files.keys():
        rel_text = str(rel_path)
        if not rel_text.endswith(".onnx"):
            continue

        rel = Path(rel_text)
        filename = rel.name

        # Official nested layout, e.g. voices/en/en_US/joe/medium/en_US-joe-medium.onnx
        candidates.append(model_dir / rel)
        # Flat layout, e.g. voices/en_US-joe-medium.onnx
        candidates.append(model_dir / filename)
        # Last-resort project-root relative variants.
        candidates.append(_project_root() / rel)
        candidates.append(_project_root() / filename)

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def _find_catalog_model_for_language(language_name: str) -> tuple[Optional[Path], str]:
    notes: list[str] = []

    for voice_key, entry in _catalog_entries_for_language(language_name):
        for candidate in _model_paths_from_catalog_entry(entry):
            valid, warning = _validate_model_files_or_none(candidate)
            if valid:
                return valid, ""
            notes.append(f"{voice_key}: {warning}")

    return None, " | ".join(notes[:20])


def _find_language_model_in_dir(language_name: str, candidate_codes: list[str]) -> Optional[Path]:
    model_dir = _model_dir()
    if not model_dir.exists():
        return None

    all_models = sorted(model_dir.rglob("*.onnx"))
    if not all_models:
        return None

    normalized_codes = [c.lower() for c in candidate_codes if c]
    language_name_l = language_name.lower()

    preferred: list[Path] = []
    for p in all_models:
        p_text = p.as_posix().lower()
        p_name = p.name.lower()
        if language_name_l in p_text:
            preferred.append(p)
            continue
        for code in normalized_codes:
            if (
                p_name.startswith(f"{code}_")
                or p_name.startswith(f"{code}-")
                or f"/{code}_" in p_text
                or f"/{code}-" in p_text
                or f"/{code}/" in p_text
            ):
                preferred.append(p)
                break

    qualities = _quality_preference()

    def sort_key(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        for i, q in enumerate(qualities):
            if q in name:
                return (i, name)
        return (len(qualities) + 1, name)

    for candidate in sorted(preferred, key=sort_key):
        valid, _warning = _validate_model_files_or_none(candidate)
        if valid:
            return valid

    return None


def resolve_piper_model(language_name: str) -> Path:
    """Resolve a local Piper model for the requested UI language.

    Resolution order:
      1. piper_voices.json catalogue + real files under voices/.
      2. Recursive auto-discovery under PIPER_MODEL_DIR.

    There are intentionally no per-language PIPER_MODEL_<LANG> or PIPER_VOICE_<LANG>
    overrides anymore. The catalogue and the local voices folder are the source
    of truth.
    """

    lang_code = LANGUAGE_PREFIXES.get(language_name, "en")
    piper_codes = _catalog_codes_for_language(language_name) or LANGUAGE_PIPER_CODES.get(language_name, [lang_code])
    resolution_notes: list[str] = []

    catalog_candidate, catalog_warning = _find_catalog_model_for_language(language_name)
    if catalog_candidate:
        return catalog_candidate
    if catalog_warning:
        resolution_notes.append(f"catalogue: {catalog_warning}")

    candidate = _find_language_model_in_dir(language_name, piper_codes + [lang_code])
    if candidate:
        return candidate

    model_dir = _model_dir()
    technical = (
        f"No valid Piper voice model found for language={language_name}, "
        f"generic_code={lang_code}, piper_codes={piper_codes}. "
        f"Checked catalogue {_catalog_path()} and model dir {model_dir}."
    )
    if resolution_notes:
        technical += " Missing candidates: " + " | ".join(resolution_notes)

    raise PiperVoiceNotConfigured(
        (
            f"Audio was not generated: no complete Piper voice is installed for {language_name}. "
            "The text translation is still available. Add a matching .onnx voice and its "
            ".onnx.json file inside the voices/ folder."
        ),
        technical,
    )


def piper_command() -> list[str]:
    """Return Piper executable command as a list suitable for subprocess."""

    configured = os.getenv("PIPER_BIN", "piper").strip() or "piper"
    parts = shlex.split(configured)
    exe = parts[0]

    candidate = Path(exe).expanduser()
    if candidate.is_absolute():
        if candidate.exists():
            parts[0] = str(candidate)
            return parts
        raise PiperExecutableNotFound(
            "Piper was not found. Install piper-tts or set PIPER_BIN in the .env file.",
            f"Piper executable not found: {candidate}",
        )

    resolved = shutil.which(exe)
    if resolved:
        parts[0] = resolved
        return parts

    raise PiperExecutableNotFound(
        "Piper was not found. Install piper-tts or set PIPER_BIN in the .env file.",
        f"Piper executable not found in PATH: {exe}",
    )


def synthesize_piper_wav_base64(text: str, language_name: str) -> str:
    """Generate WAV audio with Piper and return it as a base64 string."""

    clean_text = (text or "").strip()
    if not clean_text:
        return ""

    model_path = resolve_piper_model(language_name)

    with tempfile.NamedTemporaryFile(prefix="piper_tts_", suffix=".wav", delete=False) as tmp:
        output_path = Path(tmp.name)

    base_cmd = piper_command() + ["--model", str(model_path)]

    # Piper versions in the wild differ between --output_file and --output-file.
    attempts = [
        base_cmd + ["--output_file", str(output_path)],
        base_cmd + ["--output-file", str(output_path)],
    ]

    last_error = ""
    try:
        for cmd in attempts:
            proc = subprocess.run(
                cmd,
                input=clean_text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                return base64.b64encode(output_path.read_bytes()).decode("utf-8")
            last_error = proc.stderr.decode("utf-8", errors="replace").strip()

        raise PiperSynthesisFailed(
            (
                f"Audio was not generated: Piper failed to synthesize speech for {language_name}. "
                "The text translation is still available. Check that the downloaded voice is compatible."
            ),
            f"Piper failed. Model={model_path}. Error={last_error or 'unknown error'}",
        )
    finally:
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass


def list_installed_piper_voices() -> list[dict[str, str]]:
    """Return installed complete voices discovered through the catalogue and voices/.

    This is intentionally small and side-effect free. It is useful for future UI
    diagnostics or CLI tools.
    """

    installed: list[dict[str, str]] = []
    seen: set[str] = set()

    catalog = _load_voice_catalog()
    for voice_key, entry in catalog.items():
        if not isinstance(entry, dict):
            continue
        for candidate in _model_paths_from_catalog_entry(entry):
            valid, _warning = _validate_model_files_or_none(candidate)
            if not valid:
                continue
            if str(valid) in seen:
                continue
            seen.add(str(valid))
            language = entry.get("language", {}) or {}
            installed.append({
                "voice_key": voice_key,
                "language_code": str(language.get("code", "")),
                "language_name": str(language.get("name_english", "")),
                "quality": str(entry.get("quality", "")),
                "path": str(valid),
            })

    # Also include complete voices not covered by the catalogue.
    model_dir = _model_dir()
    if model_dir.exists():
        for model in sorted(model_dir.rglob("*.onnx")):
            valid, _warning = _validate_model_files_or_none(model)
            if valid and str(valid) not in seen:
                seen.add(str(valid))
                installed.append({
                    "voice_key": model.stem,
                    "language_code": "",
                    "language_name": "",
                    "quality": "",
                    "path": str(valid),
                })

    return installed


def tts_status() -> str:
    """Small human-readable status for the UI badge."""

    installed = list_installed_piper_voices()
    if not installed:
        if _load_voice_catalog():
            return "Piper Offline TTS + catalogue: no local voice installed"
        return "Piper Offline TTS: no local voice installed"

    catalog_suffix = " + catalogue" if _load_voice_catalog() else ""
    return f"Piper Offline TTS{catalog_suffix}: {len(installed)} local voice(s)"
