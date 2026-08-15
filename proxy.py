from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import json
import re
import os

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "gsk_ваш_ключ_здесь")

def load_all_laws():
    laws = {}
    for filename in os.listdir('.'):
        if filename.startswith('laws_') and filename.endswith('.json'):
            codex_name = filename.replace('laws_', '').replace('.json', '')
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    laws[codex_name] = json.load(f)
                print(f"Загружен {codex_name}: {len(laws[codex_name])} статей")
            except Exception as e:
                print(f"Ошибка загрузки {filename}: {e}")
    return laws

ALL_LAWS = load_all_laws()

def find_in_all_laws(query, top_k=5):
    query_lower = query.lower()
    results = []
    for codex_name, articles in ALL_LAWS.items():
        for article in articles:
            text = article['text'].lower()
            title = article['title'].lower()
            score = 0
            words = query_lower.split()
            for word in words:
                if word in text:
                    score += 1
                if word in title:
                    score += 2
            if score > 0:
                results.append({
                    'codex': codex_name,
                    'title': article['title'],
                    'text': article['text'],
                    'score': score
                })
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api', methods=['OPTIONS', 'POST'])
def proxy():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.get_json()
        user_text = data.get('text', '')
        codex = data.get('codex', 'auto')

        if codex == 'auto':
            found = find_in_all_laws(user_text, top_k=6)
            if not found:
                return jsonify({'reply': 'Ничего не найдено. Попробуйте уточнить запрос.'})
            context = "\n\n".join([
                f"[{f['codex'].upper()}] {f['title']}: {f['text'][:600]}..." for f in found
            ])
            system_prompt = """
Ты — юридический эксперт. Пользователь описывает ситуацию. Найди в предоставленном контексте наиболее подходящие статьи законов и дай чёткий ответ.
Формат ответа:
[ARTICLE] — статьи с номерами и названиями
[PUNISHMENT] — наказание или санкции
[IMPORTANT] — важные нюансы
"""
            user_prompt = f"Ситуация: {user_text}\n\nКонтекст:\n{context}"
        else:
            if codex not in ALL_LAWS:
                return jsonify({'error': f'Кодекс "{codex}" не найден'}), 404
            found = find_in_all_laws(user_text, top_k=6)
            filtered = [f for f in found if f['codex'] == codex]
            if not filtered:
                return jsonify({'reply': f'В {codex} ничего не найдено.'})
            context = "\n\n".join([
                f"{f['title']}: {f['text'][:600]}..." for f in filtered
            ])
            system_prompt = f"""
Ты — юридический эксперт по {codex}. Ответь на вопрос пользователя, используя только предоставленный контекст.
Формат: [ARTICLE] — статьи, [PUNISHMENT] — наказание, [IMPORTANT] — нюансы.
"""
            user_prompt = f"Ситуация: {user_text}\n\nКонтекст:\n{context}"

        headers = {
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': 'llama-3.3-70b-versatile',
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            'temperature': 0.3,
            'max_tokens': 2000
        }

        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            return jsonify({'error': f'API error: {response.status_code}'}), 500

        result = response.json()
        reply = result.get('choices', [{}])[0].get('message', {}).get('content', 'Нет ответа')
        return jsonify({'reply': reply})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/codexes', methods=['GET'])
def get_codexes():
    return jsonify(list(ALL_LAWS.keys()))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
