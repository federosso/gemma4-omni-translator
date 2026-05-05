# 🌐 Gemma 4 Omni-Translator

![Gemma](https://img.shields.io/badge/Model-Gemma_4_E2B-orange?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square)
![Flask](https://img.shields.io/badge/Framework-Flask-green?style=flat-square)
![TTS](https://img.shields.io/badge/TTS-Piper_Offline-38bdf8?style=flat-square)
![Status](https://img.shields.io/badge/Status-Hackathon_Ready-success?style=flat-square)

**Local-first multimodal speech and text translation powered by Gemma 4 + Piper Offline TTS.**

Gemma 4 Omni-Translator is a Flask web app that records speech from the browser, converts it to 16 kHz mono WAV with FFmpeg, sends the audio directly to a local Gemma 4 multimodal model, and optionally plays the translated text through a local Piper voice.

The goal is simple: **translate speech without sending the user's voice or translated text to external cloud TTS services at runtime.**

> First-time setup still requires downloading/caching the Gemma model and any Piper voices you want to use. After the model and voice files are available locally, the app is designed to run in offline-first mode.

---

## 💡 Why this project?

Most voice translation applications rely on a multi-step pipeline:

```text
Speech-to-Text → Text Translation → Text-to-Speech
```

That often means sending audio or text to cloud services. Gemma 4 Omni-Translator explores a more local, privacy-oriented architecture:

1. **Local multimodal inference**  
   The browser records audio, FFmpeg converts it to 16 kHz mono WAV, and the audio is passed directly to Gemma 4. No separate Whisper/STT model is required in the app pipeline.

2. **Offline speech output with Piper**  
   The previous version used `gTTS`, which required an external Google TTS service. This refactor removes `gTTS` and uses Piper `.onnx` voices for local speech synthesis.

3. **Conversation and language-learning workflow**  
   The UI keeps a history of original recordings and translated outputs, making it useful both for bilingual conversations and EdTech-style pronunciation practice.

---

## ✨ Key features

- **🎙️ Speech translation**  
  Record speech in the browser and translate it through Gemma 4 multimodal inference.

- **⌨️ Text translation**  
  Translate typed text with the same interface and optionally generate spoken output.

- **🔊 Local Piper TTS**  
  Translated text can be synthesized using local Piper `.onnx` voices. No `gTTS` dependency is used.

- **🧠 No separate Whisper/STT stage**  
  Audio is converted to the format expected by the multimodal processor and sent directly to Gemma 4.

- **💬 Auto-swap conversation mode**  
  Source and target languages can be swapped automatically after each exchange, making bilingual dialogue smoother.

- **📝 Text-only mode**  
  Both Speech and Text panels include a **Generate voice output** toggle. Turn it off to skip Piper and return only translated text.

- **🎧 EdTech shadowing workflow**  
  Original audio and synthesized translation can be played back and downloaded from the chat history.

- **🛡️ Friendly error handling**  
  Missing Piper voices, missing audio, FFmpeg errors, or TTS failures are shown as readable warnings instead of raw tracebacks.

- **📚 Piper catalogue driven**  
  Voice selection is based on `piper_voices.json` plus the `.onnx` files actually installed inside `voices/`. The `.env` file no longer needs one variable per language.

- **🌍 Broad language UI**  
  The interface exposes many target languages for translation prompts. Audio is generated only when a matching local Piper voice is installed.

---

## 🏗️ Architecture

```mermaid
graph TD
    classDef frontend fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#fff
    classDef backend fill:#0f172a,stroke:#10b981,stroke-width:2px,color:#fff
    classDef ai fill:#3f2a14,stroke:#f59e0b,stroke-width:2px,color:#fff
    classDef localtts fill:#172554,stroke:#38bdf8,stroke-width:2px,color:#fff

    subgraph Browser_UI ["🖥️ Step 1: Frontend"]
        A(["🎙️ User Speaks"])
        B["WebM/Opus Recording"]
        T["Typed Text"]
    end

    subgraph Server ["⚙️ Step 2: Flask Backend"]
        C["POST /api/translate_speech"]
        C2["POST /api/translate_text"]
        D["FFmpeg: WAV 16kHz Mono"]
    end

    subgraph CoreAI ["🧠 Step 3: Local Edge AI"]
        E{"Gemma 4 E2B Multimodal"}
        F["float16 Local Inference"]
    end

    subgraph Local_TTS ["🔊 Step 4: Optional Local TTS"]
        G["piper_voices.json"]
        V["Installed Piper .onnx Voice"]
        I["Generate WAV/Base64 Audio"]
    end

    subgraph Output_UI ["🎧 Step 5: Output"]
        H(["Translated Text + Optional Audio"])
        W(["Friendly Warning if Voice Missing"])
    end

    A --> B
    B --> C
    C --> D
    D -->|"16kHz Audio + Prompt"| E
    T --> C2
    C2 -->|"Text + Prompt"| E
    E --> F
    F -->|"Translated Text"| H
    F -->|"Translated Text"| G
    G --> V
    V --> I
    I --> H
    G -->|"No matching local voice"| W

    class A,B,T,H,W frontend
    class C,C2,D backend
    class E,F ai
    class G,V,I localtts
```

---

## 📁 Project structure

```text
.
├── app.py                    # Flask app + Gemma inference endpoints
├── tts_engine.py             # Offline Piper TTS resolver/invoker
├── piper_voices.json         # Piper voice catalogue
├── requirements.txt          # App dependencies, excluding PyTorch CUDA
├── .env.example              # Minimal runtime configuration
├── .env                      # Local runtime configuration
├── templates/
│   └── index.html            # Offline UI, vanilla HTML/CSS/JS
├── tools/
│   └── check_piper_voices.py # Diagnostic tool for local Piper voices
└── voices/
    └── README.md             # Put Piper .onnx voice files here
```

---

## ✅ Requirements

Recommended environment:

- Python 3.11
- NVIDIA GPU with CUDA support recommended for Gemma inference
- FFmpeg installed and available in `PATH`
- Local Hugging Face cache containing `google/gemma-4-E2B-it`
- Piper voice files stored locally inside `voices/`
- Windows, Linux, or macOS capable of running Flask + PyTorch

> The project is designed for local GPU inference. Running Gemma on CPU may be extremely slow or may fail due to RAM/page-file limits.

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/federosso/gemma4-omni-translator.git
cd gemma4-omni-translator
```

### 2. Create and activate a virtual environment

Windows:

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
```

Linux/macOS:

```bash
python3.11 -m venv .venv311
source .venv311/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

### 3. Install PyTorch CUDA separately

PyTorch is intentionally not installed from `requirements.txt`, because the correct CUDA build depends on your system.

For CUDA 12.8:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

Verify GPU detection:

```bash
python -c "import torch; print('torch:', torch.__version__); print('cuda build:', torch.version.cuda); print('cuda available:', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')"
```

Expected result:

```text
cuda available: True
gpu: NVIDIA ...
```

### 4. Install app dependencies

```bash
pip install -r requirements.txt
```

---

## 🧠 Gemma offline setup

The app runs with offline-first Hugging Face settings:

```text
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
local_files_only=True
```

This means the Gemma model must already be cached locally before the app starts in offline mode.

If you need to cache the model for the first time, run once while online after accepting the model terms:

```bash
huggingface-cli login
python - <<'PY'
from transformers import AutoProcessor, AutoModelForMultimodalLM

MODEL_ID = "google/gemma-4-E2B-it"
AutoProcessor.from_pretrained(MODEL_ID)
AutoModelForMultimodalLM.from_pretrained(MODEL_ID)
PY
```

After this, you can run the app offline as long as the model remains in the local Hugging Face cache.

---

## 🔊 Piper voice setup

The project now uses one catalogue file:

```text
piper_voices.json
```

Keep it in the project root. This file describes available Piper voices, their language codes, quality level, and expected file paths.

Then place the actual Piper voice files inside:

```text
voices/
```

Each Piper voice requires two files:

```text
<voice>.onnx
<voice>.onnx.json
```

Both layouts are supported.

Flat layout:

```text
voices/
  en_US-joe-medium.onnx
  en_US-joe-medium.onnx.json
  it_IT-riccardo-x_low.onnx
  it_IT-riccardo-x_low.onnx.json
```

Official nested Piper layout:

```text
voices/
  en/en_US/joe/medium/en_US-joe-medium.onnx
  en/en_US/joe/medium/en_US-joe-medium.onnx.json
  it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx
  it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx.json
```

Voice selection works like this:

```text
Target language selected in UI
        ↓
piper_voices.json catalogue lookup
        ↓
Installed files found inside voices/
        ↓
Quality preference check
        ↓
Piper synthesis, or friendly warning if no voice is available
```

The `.env` file no longer contains per-language voice variables. The app auto-discovers installed voices.

### Check installed voices

```bash
python tools/check_piper_voices.py
```

This tool reports which voices are complete, which are missing `.onnx.json`, and which languages are currently available for local audio output.

---

## ⚙️ Environment variables

Copy `.env.example` to `.env` if needed.

Minimal configuration:

```env
# Hugging Face offline-first runtime
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
GEMMA_MODEL_ID=google/gemma-4-E2B-it

# Translation generation limit
TRANSLATION_MAX_NEW_TOKENS=128

# Executables
FFMPEG_BIN=ffmpeg
PIPER_BIN=piper

# TTS behavior
ENABLE_TTS=1
TTS_VERBOSE_ERRORS=0

# Piper local assets
PIPER_MODEL_DIR=voices
PIPER_QUALITY_PREFERENCE=medium,high,low,x_low
```

Useful notes:

- Use `TRANSLATION_MAX_NEW_TOKENS=128` for short speech translations.
- Raise it to `256` or `512` for longer text translations.
- Set `ENABLE_TTS=0` to globally disable Piper audio generation.
- Set `TTS_VERBOSE_ERRORS=1` only while debugging.
- Use full paths for `FFMPEG_BIN` or `PIPER_BIN` if Windows cannot find them in `PATH`.

Example Windows paths:

```env
FFMPEG_BIN=C:\ffmpeg\bin\ffmpeg.exe
PIPER_BIN=C:\path\to\.venv311\Scripts\piper.exe
```

---

## ▶️ Run the app

```bash
python app.py
```

Open:

```text
http://127.0.0.1:7860
```

The server runs with Flask debug reloader disabled to avoid loading Gemma twice into memory.

---

## 🧪 How to use

### Speech tab

1. Select source and target languages.
2. Click the microphone button to start recording.
3. Click the microphone again to stop, or click **Translate** while recording to stop and translate immediately.
4. Enable or disable **Generate voice output** depending on whether you want Piper audio.
5. Use the history buttons to replay or download original and translated audio.

### Text tab

1. Type or paste text.
2. Select source and target languages.
3. Enable or disable **Generate voice output**.
4. Click **Translate Text**.
5. Replay/download the generated audio if a local Piper voice exists.

### Auto-swap mode

When enabled, the app automatically swaps source and target languages after each translation, making back-and-forth conversations easier.

---

## 🛠️ Troubleshooting

### CUDA is not detected

Run:

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

If `torch.cuda.is_available()` is `False`, reinstall PyTorch using the correct CUDA index.

### Flask starts, then crashes with a page-file or memory error

Make sure Flask is not running in debug reloader mode. The app should use:

```python
app.run(debug=False, use_reloader=False)
```

The reloader can load Gemma twice and exhaust memory.

### `[WinError 2] The system cannot find the file specified`

Usually FFmpeg or Piper is not in `PATH`.

Check:

```bash
ffmpeg -version
piper --help
```

If they fail, configure full paths in `.env`.

### Translation works but no audio is generated

This usually means no matching Piper voice is installed for the target language.

The app does not crash. It shows a warning and keeps the text translation available.

Install the matching `.onnx` and `.onnx.json` files inside `voices/`, then run:

```bash
python tools/check_piper_voices.py
```

### Piper catalogue exists but voices are not found

Make sure:

```text
piper_voices.json
voices/<voice>.onnx
voices/<voice>.onnx.json
```

are all present and correctly named.

---

## 🔌 API endpoints

### `POST /api/translate_speech`

Accepts multipart form data:

```text
audio=<webm audio blob>
source_lang=English
target_lang=Italian
enable_tts=1
```

Returns translated text, optional synthesized audio, warning metadata, and detected/source fields.

### `POST /api/translate_text`

Accepts JSON:

```json
{
  "text": "Hello, I need a doctor.",
  "source_lang": "English",
  "target_lang": "Italian",
  "enable_tts": true
}
```

Returns translated text and optional synthesized audio.

---

## ⚠️ Limitations

- The app is offline-first at runtime, but first-time model and voice downloads require internet access.
- Translation quality depends on the Gemma model and prompt behavior.
- Piper audio is available only for languages with locally installed voices.
- The app is a prototype/demo and is not a certified medical, legal, or emergency translation system.
- CPU-only execution is not recommended for the Gemma model.

---

## 🧭 Design principle

```text
Gemma handles local multimodal understanding and translation.
Piper handles local speech synthesis.
piper_voices.json describes what can exist.
voices/ contains what is actually installed.
.env controls runtime behavior, not per-language voice mapping.
```

This keeps the project cleaner, easier to configure, and more honest about offline execution.

---

## 📄 License

See `LICENSE`.
