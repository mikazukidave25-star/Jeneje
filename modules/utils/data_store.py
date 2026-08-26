import json
import os
import tempfile
import aiohttp

from copy import deepcopy


def read_text(path, default=''):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return default


def write_text(path, content):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def read_lines(path):
    result = []
    for line in read_text(path, '').splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            result.append(stripped)
    return result


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, data):
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix='.tmp-', suffix='.json', dir=folder, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.write('\n')
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def validate_json_text(content):
    return json.loads(content)


def deep_merge(defaults, user_config):
    base = deepcopy(defaults or {})
    if not isinstance(user_config, dict):
        return base
    for key, value in user_config.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = deep_merge(base[key], value)
        else:
            base[key] = deepcopy(value)
    return base