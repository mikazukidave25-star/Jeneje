import os
import json
import socket

import flask
from flask_socketio import SocketIO

from modules.utils.logger import get_ws_handler, get_logger
from modules.utils.data_store import read_text, write_text, validate_json_text
from modules.utils import cache, ws

logger = get_logger('app')

app = flask.Flask(__name__)
app.config['SECRET_KEY'] = 'Phamdat Selfbot'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

bot_manager = None

DASHBOARD_PASSWORD = os.environ.get('DASHBOARD_PASSWORD')

if os.environ.get('PORT') and not DASHBOARD_PASSWORD:
    logger.warning(
        'PORT is set (this looks like a cloud deploy) but DASHBOARD_PASSWORD is not - '
        'the dashboard and its API (including token/config read-write) are PUBLICLY '
        'ACCESSIBLE with no login. Set DASHBOARD_PASSWORD to protect it.'
    )


@app.before_request
def require_dashboard_password():
    if not DASHBOARD_PASSWORD:
        return None  # Auth disabled - matches original local-only behavior.

    auth = flask.request.authorization
    if not auth or auth.password != DASHBOARD_PASSWORD:
        return flask.Response(
            'Authentication required', 401,
            {'WWW-Authenticate': 'Basic realm="Phamdat Selfbot Dashboard"'},
        )
    return None


def set_bot_manager(bm):
    global bot_manager
    bot_manager = bm


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return flask.send_from_directory('assets', filename)


@app.route('/')
@app.route('/terminal')
def page_terminal():
    return flask.render_template('terminal.html')


@app.route('/captcha')
def page_captcha():
    return flask.render_template('captcha.html')


@app.route('/data')
def page_data():
    return flask.render_template('data.html')


@app.route('/api/status')
def api_status():
    running = bot_manager.is_running() if bot_manager else False
    start_time = bot_manager.start_time() if bot_manager else None
    bots = bot_manager.status() if bot_manager else {}
    return flask.jsonify({'running': running, 'start_time': start_time if running else None, 'bots': bots})


@app.route('/api/start', methods=['POST'])
def api_start():
    if not bot_manager:
        return flask.jsonify({'ok': False, 'error': 'Bot manager not initialized'}), 500
    if bot_manager.is_running():
        return flask.jsonify({'ok': False, 'error': 'Already running'})
    try:
        bot_manager.start()
        logger.info('Started via web')
        return flask.jsonify({'ok': True})
    except Exception:
        logger.exception('Failed to start')
        return flask.jsonify({'ok': False, 'error': 'Failed to start'}), 500


@app.route('/api/stop', methods=['POST'])
def api_stop():
    if not bot_manager:
        return flask.jsonify({'ok': False, 'error': 'Bot manager not initialized'}), 500
    try:
        bot_manager.stop()
        logger.info('Stopped via web')
        return flask.jsonify({'ok': True})
    except Exception:
        logger.exception('Failed to stop')
        return flask.jsonify({'ok': False, 'error': 'Failed to stop'}), 500


@app.route('/api/captcha/list')
def api_captcha_list():
    bot = flask.request.args.get('bot')
    return flask.jsonify(cache.list(bot))


@app.route('/api/captcha/solve', methods=['POST'])
def api_captcha_solve():
    payload = flask.request.get_json() or {}
    captcha = cache.find_by_id(payload.get('id'))
    if not captcha:
        return flask.jsonify({'ok': False, 'error': 'Captcha not found'}), 404

    answer = payload.get('answer')
    bot = captcha.get('bot')
    user_id = captcha.get('user_id')

    cache.update(bot, user_id, {'answer': answer, 'status': 'solved'})

    if bot_manager:
        bot_manager.solve_captcha(captcha, answer)

    ws.emit('captcha_update', {'id': captcha['id'], 'bot': bot, 'action': 'processing'})
    return flask.jsonify({'ok': True, 'status': 'processing'})


@app.route('/api/captcha/delete', methods=['POST'])
def api_captcha_delete():
    payload = flask.request.get_json() or {}
    captcha = cache.find_by_id(payload.get('id'))
    if not captcha:
        return flask.jsonify({'ok': False, 'error': 'Captcha not found'}), 404

    bot = captcha.get('bot')
    user_id = captcha.get('user_id')

    if bot_manager:
        bot_manager.delete_captcha(captcha)

    cache.remove(bot, user_id)
    ws.emit('captcha_update', {'id': captcha['id'], 'bot': bot, 'action': 'deleted'})
    ws.emit('captcha_count', {'count': cache.count()})
    return flask.jsonify({'ok': True, 'status': 'deleted', 'removed': True})


@app.route('/api/data/files')
def api_data_files():
    try:
        files = sorted([
            f for f in os.listdir('data')
            if os.path.isfile(os.path.join('data', f))
        ])
        return flask.jsonify(files)
    except Exception:
        logger.exception('Failed to list files')
        return flask.jsonify([])


@app.route('/api/data/read')
def api_data_read():
    filename = flask.request.args.get('file', '')
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return flask.jsonify({'ok': False, 'error': 'Invalid filename'}), 400

    filepath = f'data/{filename}'
    if not os.path.isfile(filepath):
        return flask.jsonify({'ok': False, 'error': 'File not found'}), 404

    try:
        content = read_text(filepath)
        return flask.jsonify({'ok': True, 'content': content, 'filename': filename})
    except Exception:
        logger.exception(f'Failed to read: {filename}')
        return flask.jsonify({'ok': False, 'error': 'Failed to read file'}), 500


@app.route('/api/data/write', methods=['POST'])
def api_data_write():
    payload = flask.request.get_json()
    if not payload:
        return flask.jsonify({'ok': False, 'error': 'Empty payload'}), 400

    filename = payload.get('file', '')
    content = payload.get('content', '')

    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return flask.jsonify({'ok': False, 'error': 'Invalid filename'}), 400

    filepath = f'data/{filename}'
    if not os.path.isfile(filepath):
        return flask.jsonify({'ok': False, 'error': 'File not found'}), 404

    try:
        if filename.endswith('.json'):
            validate_json_text(content)
        write_text(filepath, content)
        logger.info(f'File saved: {filename}')
        return flask.jsonify({'ok': True})
    except json.JSONDecodeError as e:
        return flask.jsonify({'ok': False, 'error': f'Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}'}), 400
    except Exception:
        logger.exception(f'Failed to write: {filename}')
        return flask.jsonify({'ok': False, 'error': 'Failed to write file'}), 500


@app.route('/api/logs')
def api_logs():
    handler = get_ws_handler()
    limit = flask.request.args.get('limit', 1000, type=int)
    before = flask.request.args.get('before', type=int)
    after = flask.request.args.get('after', type=int)
    limit = max(1, min(limit, 1000))
    logs, has_more = handler.get_buffer(limit=limit, before=before, after=after)
    return flask.jsonify({'logs': logs, 'has_more': has_more, 'names': handler.get_names()})


@socketio.on('connect')
def handle_connect():
    ws.emit('captcha_count', {'count': cache.count()}, room=flask.request.sid)


def _get_lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except Exception:
        return None


def run_server(host, port):
    local_url = f'http://localhost:{port}'
    loopback_url = f'http://127.0.0.1:{port}'
    lan_ip = _get_lan_ip()
    urls = [local_url]
    if loopback_url not in urls:
        urls.append(loopback_url)
    if lan_ip:
        urls.append(f'http://{lan_ip}:{port}')

    logger.info('Website server started')
    logger.info(f'  Local:    {urls[0]} (this computer)')
    if len(urls) > 1:
        logger.info(f'  Loopback: {urls[1]} (this computer)')
    if lan_ip:
        logger.info(f'  Network:  {urls[-1]} (devices on the same network)')
    else:
        logger.info('  Network:  LAN address unavailable')
    logger.info(f'  Binding:  {host}:{port} (0.0.0.0 means all network interfaces)')
    socketio.run(app, host=host, port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)