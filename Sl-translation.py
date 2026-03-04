from flask import Flask, request, jsonify
import requests
import logging
import time
from functools import lru_cache
from collections import defaultdict

# --- Config ---
MAX_TEXT_LENGTH = 5000
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW = 60

# --- App Setup ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- Rate Limiter ---
rate_tracker = defaultdict(list)

def is_rate_limited(ip: str) -> bool:
    now = time.time()
    rate_tracker[ip] = [t for t in rate_tracker[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(rate_tracker[ip]) >= RATE_LIMIT_REQUESTS:
        return True
    rate_tracker[ip].append(now)
    return False

# -------------------------------------------------------------------
# TRANSLATION ENGINES (tried in order until one succeeds)
# -------------------------------------------------------------------

def try_mymemory(text: str, source: str, target: str) -> str | None:
    """MyMemory — free, no key, 100+ languages, 5000 chars/day."""
    try:
        langpair = f"{source}|{target}" if source != "auto" else f"en|{target}"
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": langpair},
            timeout=8
        )
        r.raise_for_status()
        data = r.json()
        if data.get("responseStatus") == 200:
            result = data["responseData"]["translatedText"]
            if result and result != text:
                return result
    except Exception as e:
        logger.warning(f"MyMemory failed: {e}")
    return None


def try_lingva(text: str, source: str, target: str) -> str | None:
    """Lingva Translate — open source Google Translate frontend, 130+ languages."""
    mirrors = [
        "https://lingva.ml",
        "https://translate.plausibility.cloud",
        "https://lingva.thedaviddelta.com",
    ]
    src = source if source != "auto" else "auto"
    for mirror in mirrors:
        try:
            r = requests.get(
                f"{mirror}/api/v1/{src}/{target}/{requests.utils.quote(text)}",
                timeout=8
            )
            r.raise_for_status()
            data = r.json()
            result = data.get("translation")
            if result and result != text:
                logger.info(f"Lingva success via {mirror}")
                return result
        except Exception as e:
            logger.warning(f"Lingva mirror {mirror} failed: {e}")
    return None


def try_libretranslate(text: str, source: str, target: str) -> str | None:
    """LibreTranslate — open source, 30+ languages, multiple free mirrors."""
    mirrors = [
        "https://libretranslate.com",
        "https://translate.argosopentech.com",
        "https://translate.terraprint.co",
    ]
    for mirror in mirrors:
        try:
            r = requests.post(
                f"{mirror}/translate",
                json={"q": text, "source": source, "target": target, "format": "text"},
                headers={"Content-Type": "application/json"},
                timeout=8
            )
            r.raise_for_status()
            data = r.json()
            result = data.get("translatedText")
            if result and result != text:
                logger.info(f"LibreTranslate success via {mirror}")
                return result
        except Exception as e:
            logger.warning(f"LibreTranslate mirror {mirror} failed: {e}")
    return None


# Chain of engines to try in order
ENGINES = [
    ("Lingva",         try_lingva),
    ("MyMemory",       try_mymemory),
    ("LibreTranslate", try_libretranslate),
]

@lru_cache(maxsize=1024)
def translate_with_fallback(text: str, source: str, target: str) -> dict:
    for name, engine in ENGINES:
        logger.info(f"Trying engine: {name}")
        result = engine(text, source, target)
        if result:
            return {"translatedText": result, "engine": name}
    raise RuntimeError("All translation engines failed")


# -------------------------------------------------------------------
# SUPPORTED LANGUAGES (union of all engines)
# -------------------------------------------------------------------

# 130+ language codes supported across all engines combined
ALL_LANGUAGES = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic",
    "hy": "Armenian", "az": "Azerbaijani", "eu": "Basque", "be": "Belarusian",
    "bn": "Bengali", "bs": "Bosnian", "bg": "Bulgarian", "ca": "Catalan",
    "ceb": "Cebuano", "zh": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)",
    "co": "Corsican", "hr": "Croatian", "cs": "Czech", "da": "Danish",
    "nl": "Dutch", "en": "English", "eo": "Esperanto", "et": "Estonian",
    "fi": "Finnish", "fr": "French", "fy": "Frisian", "gl": "Galician",
    "ka": "Georgian", "de": "German", "el": "Greek", "gu": "Gujarati",
    "ht": "Haitian Creole", "ha": "Hausa", "haw": "Hawaiian", "he": "Hebrew",
    "hi": "Hindi", "hmn": "Hmong", "hu": "Hungarian", "is": "Icelandic",
    "ig": "Igbo", "id": "Indonesian", "ga": "Irish", "it": "Italian",
    "ja": "Japanese", "jv": "Javanese", "kn": "Kannada", "kk": "Kazakh",
    "km": "Khmer", "rw": "Kinyarwanda", "ko": "Korean", "ku": "Kurdish",
    "ky": "Kyrgyz", "lo": "Lao", "la": "Latin", "lv": "Latvian",
    "lt": "Lithuanian", "lb": "Luxembourgish", "mk": "Macedonian",
    "mg": "Malagasy", "ms": "Malay", "ml": "Malayalam", "mt": "Maltese",
    "mi": "Maori", "mr": "Marathi", "mn": "Mongolian", "my": "Myanmar (Burmese)",
    "ne": "Nepali", "no": "Norwegian", "ny": "Nyanja (Chichewa)",
    "or": "Odia (Oriya)", "ps": "Pashto", "fa": "Persian", "pl": "Polish",
    "pt": "Portuguese", "pa": "Punjabi", "ro": "Romanian", "ru": "Russian",
    "sm": "Samoan", "gd": "Scots Gaelic", "sr": "Serbian", "st": "Sesotho",
    "sn": "Shona", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "so": "Somali", "es": "Spanish", "su": "Sundanese",
    "sw": "Swahili", "sv": "Swedish", "tl": "Tagalog (Filipino)",
    "tg": "Tajik", "ta": "Tamil", "tt": "Tatar", "te": "Telugu",
    "th": "Thai", "tr": "Turkish", "tk": "Turkmen", "uk": "Ukrainian",
    "ur": "Urdu", "ug": "Uyghur", "uz": "Uzbek", "vi": "Vietnamese",
    "cy": "Welsh", "xh": "Xhosa", "yi": "Yiddish", "yo": "Yoruba",
    "zu": "Zulu"
}

# -------------------------------------------------------------------
# ROUTES
# -------------------------------------------------------------------

@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "service": "Second Life Translator",
        "languages_supported": len(ALL_LANGUAGES),
        "engines": [e[0] for e in ENGINES]
    })


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
    if target not in ALL_LANGUAGES:
        return jsonify({
            "error": f"Unsupported target language '{target}'",
            "hint": "Call /languages to see all supported codes"
        }), 400

    try:
        data = translate_with_fallback(text, source, target)
        logger.info(f"Translated via {data['engine']}: {len(text)} chars → '{target}' for {ip}")
        return jsonify({
            "original": text,
            "translated": data["translatedText"],
            "source": source,
            "target": target,
            "engine": data["engine"]   # tells you which engine was used
        })
    except RuntimeError:
        return jsonify({"error": "All translation engines are currently unavailable"}), 503
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/languages")
def languages():
    """Return all supported language codes and names."""
    return jsonify([
        {"code": code, "name": name}
        for code, name in sorted(ALL_LANGUAGES.items(), key=lambda x: x[1])
    ])


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": time.time(), "engines": [e[0] for e in ENGINES]})


# --- Entry Point ---
if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))