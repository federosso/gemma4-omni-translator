import os
import io
import base64
import torch
import subprocess
import warnings
from flask import Flask, render_template, request, jsonify
from transformers import AutoProcessor, AutoModelForMultimodalLM
from gtts import gTTS

warnings.filterwarnings("ignore")

# ─── Configuration ──────────────────────────────────────────────────────────
MODEL_ID = "google/gemma-4-E2B-it"

# Languages for Gemma prompt (English keys for UI)
LANGUAGES = {
    "English": "English", "Italian": "Italian", "French": "French", 
    "Spanish": "Spanish", "German": "German", "Portuguese": "Portuguese", 
    "Polish": "Polish", "Turkish": "Turkish", "Russian": "Russian", 
    "Dutch": "Dutch", "Czech": "Czech", "Arabic": "Arabic", 
    "Chinese": "Chinese", "Japanese": "Japanese", "Hungarian": "Hungarian", 
    "Korean": "Korean", "Hindi": "Hindi"
}

# Language codes for gTTS
TTS_LANG_CODES = {
    "English": "en", "Italian": "it", "French": "fr", "Spanish": "es", 
    "German": "de", "Portuguese": "pt", "Polish": "pl", "Turkish": "tr", 
    "Russian": "ru", "Dutch": "nl", "Czech": "cs", "Arabic": "ar", 
    "Chinese": "zh-CN", "Japanese": "ja", "Hungarian": "hu", 
    "Korean": "ko", "Hindi": "hi"
}

app = Flask(__name__)
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"[INFO] Initializing Gemma 4 Multimodal on {device}...")


# Disable Hugging Face request
os.environ["HF_HUB_OFFLINE"] = "1"

processor = AutoProcessor.from_pretrained(MODEL_ID, local_files_only=True)
model = AutoModelForMultimodalLM.from_pretrained(
    MODEL_ID, 
    dtype=torch.float16,  
    low_cpu_mem_usage=True,
    local_files_only=True # No external call to HF
).to(device)


print("[INFO] Gemma 4 E2B model loaded successfully!")

# ─── Core Functions ───────────────────────────────────────────────────────────

def generate_audio_gtts(text, target_lang_name):
    lang_code = TTS_LANG_CODES.get(target_lang_name, "en")
    tts = gTTS(text=text, lang=lang_code)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return base64.b64encode(fp.read()).decode('utf-8')

def parse_gemma_output(raw_output, target_lang_en):
    parts = raw_output.split(f"{target_lang_en}: ")
    if len(parts) >= 2:
        original_text = parts[0].strip()
        translated_text = parts[1].strip()
    else:
        original_text = "N/A"
        translated_text = raw_output.strip()
    return original_text, translated_text

# ─── Flask Endpoints ──────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html',
                           languages=list(LANGUAGES.keys()),
                           model_ver="4 E2B Native",
                           gpu_str="RTX 4050")

@app.route('/api/translate_speech', methods=['POST'])
def api_translate_speech():
    try:
        audio_file = request.files.get('audio')
        src_name = request.form.get('src_lang', 'English')
        tgt_name = request.form.get('tgt_lang', 'Italian')

        if not audio_file: return jsonify({'error': 'No audio provided.'}), 400

        src_lang_en = LANGUAGES[src_name]
        tgt_lang_en = LANGUAGES[tgt_name]

        temp_wav_path = "temp_input.wav"
        audio_bytes = audio_file.read()
        cmd = ['ffmpeg', '-y', '-i', 'pipe:0', '-ar', '16000', '-ac', '1', '-f', 'wav', temp_wav_path]
        subprocess.run(cmd, input=audio_bytes, capture_output=True, check=True)

        prompt_text = (
            f"Transcribe the following speech segment in {src_lang_en}, then translate it into {tgt_lang_en}. "
            f"When formatting the answer, first output the transcription in {src_lang_en}, then one newline, "
            f"then output the string '{tgt_lang_en}: ', then the translation in {tgt_lang_en}."
        )

        messages = [{"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "audio", "audio": temp_wav_path}]}]
        
        inputs = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        if "pixel_values" in inputs: inputs["pixel_values"] = inputs["pixel_values"].to(torch.float16)

        outputs = model.generate(**inputs, max_new_tokens=256)
        input_length = inputs["input_ids"].shape[1]
        raw_text = processor.decode(outputs[0][input_length:], skip_special_tokens=True)
        
        original_text, translated_text = parse_gemma_output(raw_text, tgt_lang_en)
        audio_b64 = generate_audio_gtts(translated_text, tgt_name)

        return jsonify({'audio': audio_b64, 'text': translated_text, 'original_text': original_text, 'src': src_name, 'tgt': tgt_name})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/translate_text', methods=['POST'])
def api_translate_text():
    try:
        data = request.get_json()
        text_input = data.get('text', '').strip()
        src_name = data.get('src_lang', 'English')
        tgt_name = data.get('tgt_lang', 'Italian')

        src_lang_en = LANGUAGES[src_name]
        tgt_lang_en = LANGUAGES[tgt_name]

        messages = [{"role": "user", "content": [{"type": "text", "text": f"Translate the following {src_lang_en} text into {tgt_lang_en}. Only output the translation, without any notes or prefixes. Text: '{text_input}'"}]}]
        
        inputs = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}

        outputs = model.generate(**inputs, max_new_tokens=256)
        input_length = inputs["input_ids"].shape[1]
        translated_text = processor.decode(outputs[0][input_length:], skip_special_tokens=True).strip()
        audio_b64 = generate_audio_gtts(translated_text, tgt_name)

        return jsonify({'audio': audio_b64, 'text': translated_text, 'input_text': text_input, 'src': src_name, 'tgt': tgt_name})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=True)