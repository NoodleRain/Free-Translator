from flask import Flask, request, jsonify
import requests
import logging
import hashlib
import time
from functools import lru_cache
from collections import defaultdict

# --- Config ---
LIBRETRANSLATE_URL = "https://libretranslate.com"
MAX_TEXT_LENGTH = 5000
RATE_LIMIT_REQUESTS = 10   # max requests
RATE_LIMIT_WINDOW = 60     # per N seconds
API_KEY = None             # Set if your LibreTranslate instance requires one

# --- App Setup ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- Rate Limiter ---
rate_tracker = defaultdict(list)

def is_rate_limited(ip: str) -> bool:
    now = time.time()
    timestamps = rate_tracker[ip]
    rate_tracker[ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(rate_tracker[ip]) >= RATE_LIMIT_REQUESTS:
        return True
    rate_tracker[ip].append(now)
    return False

# --- Translation Cache ---
@lru_cache(maxsize=512)
def cached_translate(text: str, source: str, target: str) -> dict:
    payload = {"q": text, "source": source, "target": target, "format": "text"}
    if API_KEY:
        payload["api_key"] = API_KEY
    response = requests.post(
        f"{LIBRETRANSLATE_URL}/translate",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    response.raise_for_status()
    return response.json()

# --- Routes ---
@app.route("/")
def home():
    return jsonify({"status": "running", "service": "Second Life Translator"})

@app.route("/translate")
def translate():
    ip = request.remote_addr

    if is_rate_limited(ip):
        logger.warning(f"Rate limit hit by {ip}")
        return jsonify({"error": "Rate limit exceeded. Try again shortly."}), 429

    text = request.args.get("text", "").strip()
    target = request.args.get("target", "en").strip()
    source = request.args.get("source", "auto").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if len(text) > MAX_TEXT_LENGTH:
        return jsonify({"error": f"Text exceeds {MAX_TEXT_LENGTH} character limit"}), 400
    if len(target) != 2:
        return jsonify({"error": "Invalid target language code"}), 400

    try:
        data = cached_translate(text, source, target)
        translated = data.get("translatedText")
        if not translated:
            raise ValueError("Empty translation response")
        logger.info(f"Translated {len(text)} chars from '{source}' to '{target}' for {ip}")
        return jsonify({
            "original": text,
            "translated": translated,
            "source": source,
            "target": target
        })
    except requests.exceptions.Timeout:
        logger.error("LibreTranslate request timed out")
        return jsonify({"error": "Translation service timed out"}), 504
    except requests.exceptions.HTTPError as e:
        logger.error(f"LibreTranslate HTTP error: {e}")
        return jsonify({"error": "Translation service error", "detail": str(e)}), 502
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/languages")
def languages():
    """Return list of supported languages from LibreTranslate."""
    try:
        response = requests.get(f"{LIBRETRANSLATE_URL}/languages", timeout=10)
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        logger.error(f"Failed to fetch languages: {e}")
        return jsonify({"error": "Could not retrieve languages"}), 502

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": time.time()})

# --- Entry Point ---
if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))