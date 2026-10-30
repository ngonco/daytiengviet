"""Connection checks. Never prints credentials or provider response bodies."""
from pathlib import Path
import sys
import json
import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
config = dotenv_values(ROOT / '.env')
results = {}
with httpx.Client(timeout=90, follow_redirects=True) as client:
    for provider, key_name in [('groq', 'GROQ_API_KEY'), ('vilao', 'VILAO_API_KEY'), ('pexels', 'PEXELS_API_KEY')]:
        key = config.get(key_name, '')
        if not key:
            results[provider] = {'ok': False, 'error': 'missing_key'}
            continue
        try:
            if provider == 'groq':
                response = client.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {key}'})
                results[provider] = {'ok': response.is_success, 'status': response.status_code}
            elif provider == 'vilao':
                response = client.post(config.get('VILAO_BASE_URL', '').rstrip('/') + '/chat/completions', headers={'Authorization': f'Bearer {key}'}, json={'model': config.get('VILAO_MODEL'), 'messages': [{'role': 'user', 'content': 'Reply with exactly OK.'}], 'max_tokens': 16})
                content = response.json().get('choices', [{}])[0].get('message', {}).get('content', '') if response.is_success else ''
                results[provider] = {'ok': response.is_success and bool(content), 'status': response.status_code, 'has_content': bool(content)}
            else:
                response = client.get('https://api.pexels.com/v1/search', headers={'Authorization': key}, params={'query': 'Vietnam', 'per_page': 1})
                results[provider] = {'ok': response.is_success, 'status': response.status_code, 'photos': len(response.json().get('photos', [])) if response.is_success else 0}
        except Exception as exc:
            results[provider] = {'ok': False, 'error': type(exc).__name__}
print(json.dumps(results))
sys.exit(0 if all(r['ok'] for r in results.values()) else 1)
