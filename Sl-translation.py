from flask import Flask, request
import requests

app = Flask(__name__)

@app.route('/translate')
def translate():
    text = request.args.get('text', '')
    target = request.args.get('target', 'en')
    if not text:
        return "No text provided"
    try:
        r = requests.post('https://libretranslate.com/translate', data={
            'q': text,
            'source': 'auto',
            'target': target,
            'format': 'text'
        })
        return r.json().get('translatedText', 'Translation error')
    except:
        return "Translation error"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)