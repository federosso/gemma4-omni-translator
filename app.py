import os
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Offline-first: prevent accidental Hugging Face network calls at runtime.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch
from flask import Flask, jsonify, render_template, request
from transformers import AutoModelForMultimodalLM, AutoProcessor

from tts_engine import TTSUserWarning, synthesize_piper_wav_base64, tts_status

warnings.filterwarnings("ignore")

# ─── Configuration ──────────────────────────────────────────────────────────
MODEL_ID = os.getenv("GEMMA_MODEL_ID", "google/gemma-4-E2B-it")
TRANSLATION_MAX_NEW_TOKENS = int(os.getenv("TRANSLATION_MAX_NEW_TOKENS", os.getenv("MAX_NEW_TOKENS", "128")))
ENABLE_TTS = os.getenv("ENABLE_TTS", "1").strip().lower() not in {"0", "false", "no", "off"}
TTS_VERBOSE_ERRORS = os.getenv("TTS_VERBOSE_ERRORS", "0").strip().lower() in {"1", "true", "yes", "on"}
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg").strip() or "ffmpeg"

# UI language list. Values are the English language names used in Gemma prompts.
# The Piper voice resolver works independently: it maps these names to local
# Piper codes such as en_US, it_IT, es_ES, etc.
LANGUAGES = {
    "English": "English",
    "Italian": "Italian",
    "French": "French",
    "Spanish": "Spanish",
    "German": "German",
    "Portuguese": "Portuguese",
    "Dutch": "Dutch",
    "Polish": "Polish",
    "Turkish": "Turkish",
    "Russian": "Russian",
    "Czech": "Czech",
    "Arabic": "Arabic",
    "Chinese": "Chinese",
    "Japanese": "Japanese",
    "Hungarian": "Hungarian",
    "Korean": "Korean",
    "Hindi": "Hindi",
    "Bulgarian": "Bulgarian",
    "Catalan": "Catalan",
    "Welsh": "Welsh",
    "Danish": "Danish",
    "Greek": "Greek",
    "Basque": "Basque",
    "Farsi": "Farsi",
    "Finnish": "Finnish",
    "Icelandic": "Icelandic",
    "Indonesian": "Indonesian",
    "Hebrew": "Hebrew",
    "Georgian": "Georgian",
    "Kazakh": "Kazakh",
    "Kurmanji Kurdish": "Kurmanji Kurdish",
    "Luxembourgish": "Luxembourgish",
    "Latvian": "Latvian",
    "Nepali": "Nepali",
    "Norwegian": "Norwegian",
    "Malayalam": "Malayalam",
    "Romanian": "Romanian",
    "Slovak": "Slovak",
    "Slovenian": "Slovenian",
    "Albanian": "Albanian",
    "Serbian": "Serbian",
    "Swedish": "Swedish",
    "Swahili": "Swahili",
    "Telugu": "Telugu",
    "Ukrainian": "Ukrainian",
    "Urdu": "Urdu",
    "Vietnamese": "Vietnamese",
}

app = Flask(__name__)
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"[INFO] Torch: {torch.__version__} | CUDA build: {torch.version.cuda} | CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"[INFO] GPU: {torch.cuda.get_device_name(0)}")
print(f"[INFO] Initializing Gemma 4 Multimodal on {device}...")
print("[INFO] Runtime mode: offline-first. HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1")

processor = AutoProcessor.from_pretrained(MODEL_ID, local_files_only=True)
model = AutoModelForMultimodalLM.from_pretrained(
    MODEL_ID,
    dtype=torch.float16,
    low_cpu_mem_usage=True,
    local_files_only=True,
).to(device)

print("[INFO] Gemma 4 E2B model loaded successfully!")
print(f"[INFO] {tts_status()}")

# ─── Core Functions ───────────────────────────────────────────────────────────

def parse_gemma_output(raw_output, target_lang_en):
    marker = f"{target_lang_en}: "
    parts = raw_output.split(marker, 1)
    if len(parts) == 2:
        original_text = parts[0].strip()
        translated_text = parts[1].strip()
    else:
        original_text = "N/A"
        translated_text = raw_output.strip()
    return original_text, translated_text


def request_bool(value, default=True):
    """Parse a user-facing boolean from form/json values."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def generate_tts_payload(text, target_lang_name, enable_tts_for_request=True):
    """Return audio payload while keeping translation usable if TTS fails.

    TTS problems are non-fatal: the translation must remain visible. The UI
    receives a friendly warning instead of a raw traceback/technical exception.
    """

    if not enable_tts_for_request:
        return {
            "audio": "",
            "audio_mime": "",
            "tts_engine": "disabled_by_request",
            "tts_warning": "",
            "tts_detail": "",
            "audio_skipped": True,
        }

    if not ENABLE_TTS:
        return {
            "audio": "",
            "audio_mime": "",
            "tts_engine": "disabled",
            "tts_warning": "Audio output is disabled by server configuration (ENABLE_TTS=0).",
            "tts_detail": "TTS disabled by configuration.",
            "audio_skipped": False,
        }

    try:
        audio_b64 = synthesize_piper_wav_base64(text, target_lang_name)
        return {
            "audio": audio_b64,
            "audio_mime": "audio/wav",
            "tts_engine": "piper",
            "tts_warning": "",
            "tts_detail": "",
            "audio_skipped": False,
        }
    except TTSUserWarning as exc:
        return {
            "audio": "",
            "audio_mime": "",
            "tts_engine": "piper",
            "tts_warning": exc.user_message,
            "tts_detail": exc.technical_detail if TTS_VERBOSE_ERRORS else "",
            "audio_skipped": False,
        }
    except Exception as exc:
        return {
            "audio": "",
            "audio_mime": "",
            "tts_engine": "piper",
            "tts_warning": (
                f"Audio was not generated for {target_lang_name}: the Piper module failed. "
                "The text translation is still available."
            ),
            "tts_detail": f"{type(exc).__name__}: {exc}" if TTS_VERBOSE_ERRORS else "",
            "audio_skipped": False,
        }


def resolve_executable(command_or_path: str, label: str) -> str:
    """Resolve an executable name or absolute path and raise a helpful Windows-safe error."""

    candidate = Path(command_or_path).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)

    resolved = shutil.which(command_or_path)
    if resolved:
        return resolved

    raise FileNotFoundError(
        f"{label} executable not found: '{command_or_path}'. "
        f"Install {label} and add it to PATH, or set {label.upper()}_BIN in .env "
        f"to the full .exe path."
    )


def convert_webm_to_wav_16k(audio_bytes):
    """Convert browser WebM/Opus bytes to a temporary 16 kHz mono WAV path."""

    ffmpeg_exe = resolve_executable(FFMPEG_BIN, "ffmpeg")

    with tempfile.NamedTemporaryFile(prefix="gemma_input_", suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    cmd = [
        ffmpeg_exe, "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        str(wav_path),
    ]
    subprocess.run(cmd, input=audio_bytes, capture_output=True, check=True)
    return wav_path


def run_gemma_messages(messages):
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}
    if "pixel_values" in inputs:
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.float16)

    outputs = model.generate(**inputs, max_new_tokens=TRANSLATION_MAX_NEW_TOKENS)
    input_length = inputs["input_ids"].shape[1]
    return processor.decode(outputs[0][input_length:], skip_special_tokens=True).strip()


# ─── Flask Endpoints ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    return render_template(
        "index.html",
        languages=list(LANGUAGES.keys()),
        model_ver="4 E2B Native",
        gpu_str=gpu_name,
        tts_str=tts_status(),
    )


@app.route("/api/translate_speech", methods=["POST"])
def api_translate_speech():
    wav_path = None
    try:
        audio_file = request.files.get("audio")
        src_name = request.form.get("src_lang", "English")
        tgt_name = request.form.get("tgt_lang", "Italian")
        enable_tts_req = request_bool(request.form.get("enable_tts", "1"), default=True)

        if not audio_file:
            return jsonify({"error": "No audio provided."}), 400
        if src_name not in LANGUAGES or tgt_name not in LANGUAGES:
            return jsonify({"error": "Unsupported language."}), 400

        src_lang_en = LANGUAGES[src_name]
        tgt_lang_en = LANGUAGES[tgt_name]

        wav_path = convert_webm_to_wav_16k(audio_file.read())

        prompt_text = (
            f"Transcribe the following speech segment in {src_lang_en}, then translate it into {tgt_lang_en}. "
            f"When formatting the answer, first output the transcription in {src_lang_en}, then one newline, "
            f"then output the string '{tgt_lang_en}: ', then the translation in {tgt_lang_en}."
        )

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {"type": "audio", "audio": str(wav_path)},
            ],
        }]

        raw_text = run_gemma_messages(messages)
        original_text, translated_text = parse_gemma_output(raw_text, tgt_lang_en)
        tts_payload = generate_tts_payload(translated_text, tgt_name, enable_tts_req)

        return jsonify({
            **tts_payload,
            "text": translated_text,
            "original_text": original_text,
            "src": src_name,
            "tgt": tgt_name,
        })

    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
        return jsonify({"error": f"FFmpeg conversion failed: {err}"}), 500
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500
    finally:
        if wav_path:
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass


@app.route("/api/translate_text", methods=["POST"])
def api_translate_text():
    try:
        data = request.get_json(force=True)
        text_input = data.get("text", "").strip()
        src_name = data.get("src_lang", "English")
        tgt_name = data.get("tgt_lang", "Italian")
        enable_tts_req = request_bool(data.get("enable_tts", True), default=True)

        if not text_input:
            return jsonify({"error": "No text provided."}), 400
        if src_name not in LANGUAGES or tgt_name not in LANGUAGES:
            return jsonify({"error": "Unsupported language."}), 400

        src_lang_en = LANGUAGES[src_name]
        tgt_lang_en = LANGUAGES[tgt_name]

        messages = [{
            "role": "user",
            "content": [{
                "type": "text",
                "text": (
                    f"Translate the following {src_lang_en} text into {tgt_lang_en}. "
                    f"Only output the translation, without any notes or prefixes. Text: '{text_input}'"
                ),
            }],
        }]

        translated_text = run_gemma_messages(messages)
        tts_payload = generate_tts_payload(translated_text, tgt_name, enable_tts_req)

        return jsonify({
            **tts_payload,
            "text": translated_text,
            "input_text": text_input,
            "src": src_name,
            "tgt": tgt_name,
        })

    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=7860,
        debug=False,
        use_reloader=False,
        threaded=False,
    )
