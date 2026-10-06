"""Сайт обращается только к серверу владельца и не знает ключ Mistral."""
import requests


class AIError(Exception):
    pass


def gateway_request(config, path, payload=None):
    base = config['GATEWAY_URL'].rstrip('/')
    token = config['DEMO_TOKEN']
    if not base or not token:
        raise AIError('Доступ к нейросети пока не настроен. Обратитесь к владельцу проекта.')
    try:
        response = requests.request(
            'POST' if payload is not None else 'GET', base + path,
            headers={'Authorization': f'Bearer {token}'}, json=payload,
            timeout=(5, 75), allow_redirects=False,
        )
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError('Invalid response')
        if response.status_code == 429:
            raise AIError('Четыре запроса уже использованы. Возобновить доступ может только владелец.')
        if response.status_code != 200:
            raise AIError('Сервис временно недоступен. Отправленная попытка могла засчитаться. Обратитесь к владельцу проекта.')
        return data
    except (requests.RequestException, ValueError):
        raise AIError('Не удалось получить ответ сервера. Отправленная попытка могла засчитаться. Проверьте подключение.') from None


def quota(config):
    data = gateway_request(config, '/v1/status')
    remaining = data.get('remaining')
    if not isinstance(remaining, int) or not 0 <= remaining <= 4:
        raise AIError('Сервер вернул некорректный остаток запросов.')
    return remaining


def ask(config, prompt, request_id):
    data = gateway_request(config, '/v1/chat', {'prompt': prompt, 'request_id': request_id})
    if not isinstance(data.get('answer'), str) or not data['answer'].strip():
        raise AIError('Нейросеть вернула пустой ответ.')
    return data['answer']
