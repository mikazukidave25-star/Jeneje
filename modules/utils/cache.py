import time
import threading

from modules.utils.data_store import read_json, write_json

_lock = threading.RLock()


def _load():
    data = read_json('data/caches.json', {})
    if 'captchas' not in data:
        data['captchas'] = {}
    return data


def _save(data):
    write_json('data/caches.json', data)


def _key(bot, user_id):
    return f'{bot}_{user_id}'


def list(bot=None):
    with _lock:
        data = _load()
        captchas = data.get('captchas', {})
        if bot:
            return [c for k, c in captchas.items() if c.get('bot') == bot]
        return [*captchas.values()]


def count(bot=None):
    return len(list(bot))


def get(bot, user_id):
    with _lock:
        return _load().get('captchas', {}).get(_key(bot, str(user_id)))


def add(bot, user_id, payload):
    with _lock:
        data = _load()
        data.setdefault('captchas', {})[_key(bot, str(user_id))] = payload
        _save(data)
        return payload


def update(bot, user_id, patch):
    with _lock:
        data = _load()
        key = _key(bot, str(user_id))
        captcha = data.get('captchas', {}).get(key)
        if not captcha:
            return None
        captcha.update(patch)
        captcha['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        _save(data)
        return captcha


def remove(bot, user_id):
    with _lock:
        data = _load()
        key = _key(bot, str(user_id))
        existed = key in data.get('captchas', {})
        data.get('captchas', {}).pop(key, None)
        if existed:
            _save(data)
        return existed


def add_wrong_answer(bot, user_id, answer):
    with _lock:
        data = _load()
        key = _key(bot, str(user_id))
        captcha = data.get('captchas', {}).get(key)
        if not captcha:
            return
        wrong = captcha.setdefault('wrong_answers', [])
        if answer not in wrong:
            wrong.append(answer)
            captcha['wrong_answers'] = wrong[-50:]
            _save(data)


def get_wrong_answers(bot, user_id):
    captcha = get(bot, user_id)
    if not captcha:
        return []
    return captcha.get('wrong_answers', [])


def find_by_id(captcha_id):
    with _lock:
        return _load().get('captchas', {}).get(captcha_id)