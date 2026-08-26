import base64
import json
import logging
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger('quest')

running = False
stop_event = threading.Event()

API_BASE = 'https://discord.com/api/v9'
POLL_INTERVAL = 300
HEARTBEAT_INTERVAL = 30
AUTO_ACCEPT = True
MAX_WORKERS = 3

SUPPORTED_TASKS = ('WATCH_VIDEO', 'PLAY_ON_DESKTOP', 'STREAM_ON_DESKTOP', 'PLAY_ACTIVITY', 'WATCH_VIDEO_ON_MOBILE')

UA_CLIENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
             '(KHTML, like Gecko) discord/1.0.9175 Chrome/128.0.6613.186 '
             'Electron/32.2.7 Safari/537.36')


def read_tokens():
    tokens = []
    try:
        with open('data/quest.txt', encoding='utf-8') as f:
            for line in f:
                if line.strip() and not line.lstrip().startswith('#'):
                    tokens.append(line.strip())
    except FileNotFoundError:
        logger.warning('Quest token file not found: data/quest.txt')
    return tokens


def fetch_latest_build_number():
    FALLBACK = 504649
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
    try:
        r = requests.get('https://discord.com/app', headers={'User-Agent': ua}, timeout=15)
        if r.status_code == 200:
            scripts = re.findall(r'/assets/([a-f0-9]+)\.js', r.text) or \
                      [m.split('/')[-1][:-3] for m in re.findall(r'src="(/assets/[^"]+\.js)"', r.text)]
            for asset_hash in scripts[-5:]:
                ar = requests.get(f'https://discord.com/assets/{asset_hash}.js', headers={'User-Agent': ua}, timeout=15)
                m = re.search(r'buildNumber["\s:]+["\s]*(\d{5,7})', ar.text)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return FALLBACK


def make_super_properties(build_number):
    return base64.b64encode(json.dumps({
        'os': 'Windows',
        'browser': 'Discord Client',
        'release_channel': 'stable',
        'client_version': '1.0.9175',
        'os_version': '10.0.26100',
        'os_arch': 'x64',
        'app_arch': 'x64',
        'system_locale': 'en-US',
        'browser_user_agent': UA_CLIENT,
        'browser_version': '32.2.7',
        'client_build_number': build_number,
        'native_build_number': 59498,
        'client_event_source': None,
    }).encode()).decode()


class DiscordAPI:
    def __init__(self, token, build_number):
        self.session = requests.Session()
        pool = HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
        self.session.mount('https://', pool)
        self.session.mount('http://', pool)
        self.session.headers.update({
            'Authorization': token,
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'User-Agent': UA_CLIENT,
            'X-Super-Properties': make_super_properties(build_number),
            'X-Discord-Locale': 'en-US',
            'X-Discord-Timezone': 'Asia/Ho_Chi_Minh',
            'Origin': 'https://discord.com',
            'Referer': 'https://discord.com/channels/@me',
        })

    def get(self, path, **kwargs):
        return self.session.get(f'{API_BASE}{path}', timeout=15, **kwargs)

    def post(self, path, payload=None, **kwargs):
        return self.session.post(f'{API_BASE}{path}', json=payload, timeout=15, **kwargs)

    def validate_token(self):
        try:
            r = self.get('/users/@me')
            if r.status_code == 200:
                user = r.json()
                logger.info(f'Logged in as {user["username"]} (ID: {user["id"]})')
                return True
            logger.warning(f'Token invalid (status {r.status_code})')
        except Exception as e:
            logger.warning(f'Connection to Discord failed: {e}')
        return False


def _get(source, *keys):
    if source is None:
        return None
    for k in keys:
        if k in source:
            return source[k]
    return None


def get_task_config(quest):
    return _get(quest.get('config', {}), 'taskConfig', 'task_config', 'taskConfigV2', 'task_config_v2')


def get_quest_name(quest):
    cfg = quest.get('config', {})
    msgs = cfg.get('messages', {})
    name = _get(msgs, 'questName', 'quest_name')
    if name:
        return name.strip()
    game = _get(msgs, 'gameTitle', 'game_title')
    if game:
        return game.strip()
    return cfg.get('application', {}).get('name') or f"Quest#{quest.get('id', '?')}"


def get_expires_at(quest):
    return _get(quest.get('config', {}), 'expiresAt', 'expires_at')


def get_user_status(quest):
    us = _get(quest, 'userStatus', 'user_status')
    return us if isinstance(us, dict) else {}


def is_completable(quest):
    expires = get_expires_at(quest)
    if expires:
        try:
            if datetime.fromisoformat(expires.replace('Z', '+00:00')) <= datetime.now(timezone.utc):
                return False
        except ValueError:
            pass
    tasks = get_task_config(quest).get('tasks') if get_task_config(quest) else None
    return bool(tasks) and any(tasks.get(t) is not None for t in SUPPORTED_TASKS)


def is_enrolled(quest):
    return bool(_get(get_user_status(quest), 'enrolledAt', 'enrolled_at'))


def is_completed(quest):
    return bool(_get(get_user_status(quest), 'completedAt', 'completed_at'))


def get_task_type(quest):
    tasks = get_task_config(quest).get('tasks') if get_task_config(quest) else None
    if tasks:
        for t in SUPPORTED_TASKS:
            if tasks.get(t) is not None:
                return t
    return None


def get_seconds_needed(quest):
    tc = get_task_config(quest)
    task_type = get_task_type(quest)
    return tc['tasks'][task_type].get('target', 0) if tc and task_type else 0


def get_seconds_done(quest):
    task_type = get_task_type(quest)
    if not task_type:
        return 0
    return get_user_status(quest).get('progress', {}).get(task_type, {}).get('value', 0)


def get_enrolled_at(quest):
    return _get(get_user_status(quest), 'enrolledAt', 'enrolled_at')


class _HeartbeatThrottle:
    def __init__(self, gap):
        self._lock = threading.Lock()
        self._gap = gap
        self._next = 0.0

    def wait(self):
        with self._lock:
            while True:
                if not running:
                    return False
                wait = self._next - time.time()
                if wait <= 0:
                    self._next = time.time() + self._gap
                    return True
                if stop_event.wait(wait):
                    return False


class QuestAutocompleter:
    def __init__(self, api):
        self.api = api
        self.completed_ids = set()
        self.in_progress_ids = set()
        self.lock = threading.Lock()
        self.heartbeat = _HeartbeatThrottle(3.0)
        self.executor = None

    def _sleep(self, seconds):
        return not stop_event.wait(max(0, seconds))

    def _mark_done(self, qid, name):
        logger.info(f'Completed: {name}')
        with self.lock:
            self.completed_ids.add(qid)

    def fetch_quests(self):
        while running:
            try:
                r = self.api.get('/quests/@me')
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, dict):
                        blocked = _get(data, 'quest_enrollment_blocked_until')
                        if blocked:
                            logger.warning(f'Enrollment blocked until: {blocked}')
                        return data.get('quests', [])
                    return data if isinstance(data, list) else []
                if r.status_code == 429:
                    retry_after = r.json().get('retry_after', 10)
                    logger.warning(f'Rate limited, waiting {retry_after}s')
                    if stop_event.wait(retry_after):
                        return []
                    continue
                logger.warning(f'Quest fetch error ({r.status_code}): {r.text[:200]}')
                return []
            except Exception as e:
                logger.warning(f'Error fetching quests: {e}')
                return []
        return []

    def enroll_quest(self, quest):
        name = get_quest_name(quest)
        qid = quest['id']
        for attempt in range(1, 4):
            if not running:
                return False
            try:
                r = self.api.post(f'/quests/{qid}/enroll', {
                    'location': 11,
                    'is_targeted': False,
                    'metadata_raw': None,
                    'metadata_sealed': None,
                    'traffic_metadata_raw': quest.get('traffic_metadata_raw'),
                    'traffic_metadata_sealed': quest.get('traffic_metadata_sealed'),
                })
                if r.status_code == 429:
                    retry_after = r.json().get('retry_after', 5)
                    logger.warning(f'Rate limited on enroll "{name}" (attempt {attempt}/3), waiting {retry_after + 1}s')
                    if stop_event.wait(retry_after + 1):
                        return False
                    continue
                if r.status_code in (200, 201, 204):
                    logger.info(f'Enrolled: {name}')
                    return True
                logger.warning(f'Enroll "{name}" failed ({r.status_code}): {r.text[:200]}')
                return False
            except Exception as e:
                logger.warning(f'Enroll error "{name}": {e}')
                return False
        logger.warning(f'Skipping "{name}" after 3 rate limits')
        return False

    def auto_accept(self, quests):
        if not AUTO_ACCEPT:
            return quests
        unaccepted = [q for q in quests if not is_enrolled(q) and not is_completed(q) and is_completable(q)]
        if not unaccepted:
            return quests
        logger.info(f'Auto-accepting {len(unaccepted)} quest(s)')
        for q in unaccepted:
            if not running:
                return quests
            self.enroll_quest(q)
            if stop_event.wait(3):
                return quests
        if stop_event.wait(2):
            return quests
        return self.fetch_quests()

    def complete_video(self, quest):
        name = get_quest_name(quest)
        qid = quest['id']
        needed = get_seconds_needed(quest)
        done = get_seconds_done(quest)
        enrolled = get_enrolled_at(quest)
        enrolled_ts = datetime.fromisoformat(enrolled.replace('Z', '+00:00')).timestamp() if enrolled else time.time()
        logger.info(f'Video: {name} ({done:.0f}/{needed}s)')

        speed = 7
        fails = 0
        while done < needed:
            if not running:
                return
            timestamp = min(needed, done + speed)
            if (time.time() - enrolled_ts) + 10 >= timestamp:
                try:
                    r = self.api.post(f'/quests/{qid}/video-progress', {
                        'timestamp': min(needed, timestamp + random.random())
                    })
                except Exception as e:
                    logger.warning(f'Video: {e}')
                    if not self._sleep(1):
                        return
                    continue
                code = r.status_code
                if code in (200, 202):
                    fails = 0
                    if (r.json() if r.content else {}).get('completed_at'):
                        self._mark_done(qid, name)
                        return
                    done = timestamp
                    logger.info(f'[{name}] {done:.0f}/{needed}s')
                elif code == 429:
                    retry_after = r.json().get('retry_after', 5)
                    logger.warning(f'Video rate limited, retry in {retry_after + 1}s')
                    if not self._sleep(retry_after + 1):
                        return
                    continue
                elif code >= 500:
                    fails += 1
                    if fails >= 5:
                        logger.warning(f'Giving up "{name}" this cycle after repeated server errors')
                        return
                    if not self._sleep(min(60, 2 ** (fails - 1))):
                        return
                    continue
                else:
                    logger.warning(f'Video rejected ({code}): {r.text[:200]}')
                    return
            if done >= needed:
                break
            if not self._sleep(1):
                return

        try:
            self.api.post(f'/quests/{qid}/video-progress', {'timestamp': needed})
        except Exception:
            pass
        self._mark_done(qid, name)

    def _heartbeat_loop(self, quest, stream_key, progress_key):
        name = get_quest_name(quest)
        qid = quest['id']
        needed = get_seconds_needed(quest)
        done = get_seconds_done(quest)
        logger.info(f'[{get_task_type(quest)}] {name} (~{max(0, needed - done) // 60} min left)')

        fails = 0
        while done < needed:
            if not running:
                return
            if not self.heartbeat.wait():
                return
            try:
                r = self.api.post(f'/quests/{qid}/heartbeat', {'stream_key': stream_key, 'terminal': False})
            except Exception as e:
                logger.warning(f'Heartbeat: {e}')
                if not self._sleep(HEARTBEAT_INTERVAL):
                    return
                continue
            code = r.status_code
            if code in (200, 202, 204):
                fails = 0
                body = r.json() if r.content else {}
                value = (body.get('progress') or {}).get(progress_key, {}).get('value')
                if value is not None:
                    done = value
                logger.info(f'[{name}] {done:.0f}/{needed}s')
                if body.get('completed_at') or done >= needed:
                    self._mark_done(qid, name)
                    return
                if not self._sleep(HEARTBEAT_INTERVAL):
                    return
            elif code == 429:
                retry_after = r.json().get('retry_after', 5)
                logger.warning(f'Heartbeat rate limited, retry in {retry_after + 1}s')
                if not self._sleep(retry_after + 1):
                    return
            elif code >= 500:
                fails += 1
                if fails >= 5:
                    logger.warning(f'Giving up "{name}" this cycle after repeated server errors')
                    return
                if not self._sleep(min(60, HEARTBEAT_INTERVAL * (2 ** (fails - 1)))):
                    return
            else:
                logger.warning(f'Heartbeat rejected ({code}): {r.text[:200]}')
                return

        try:
            self.api.post(f'/quests/{qid}/heartbeat', {'stream_key': stream_key, 'terminal': True})
        except Exception:
            pass
        self._mark_done(qid, name)

    def complete_heartbeat(self, quest):
        self._heartbeat_loop(quest, f'call:0:{random.randint(1000, 30000)}', get_task_type(quest))

    def complete_activity(self, quest):
        self._heartbeat_loop(quest, 'call:0:1', 'PLAY_ACTIVITY')

    def process_quest(self, quest):
        qid = quest.get('id')
        name = get_quest_name(quest)
        task_type = get_task_type(quest)
        if not task_type:
            logger.warning(f'"{name}" - unsupported task, skipping')
            return
        if qid in self.completed_ids:
            return
        logger.info(f'Starting: {name} (task: {task_type})')
        if task_type in ('WATCH_VIDEO', 'WATCH_VIDEO_ON_MOBILE'):
            self.complete_video(quest)
        elif task_type in ('PLAY_ON_DESKTOP', 'STREAM_ON_DESKTOP'):
            self.complete_heartbeat(quest)
        else:
            self.complete_activity(quest)

    def _process_and_cleanup(self, quest):
        qid = quest['id']
        try:
            self.process_quest(quest)
        except Exception as e:
            logger.warning(f'Unexpected error processing quest {qid}: {e}')
        finally:
            with self.lock:
                self.in_progress_ids.discard(qid)

    def _spawn_workers(self, quests):
        if self.executor is not None:
            self.executor.shutdown(wait=False)
        self.executor = ThreadPoolExecutor(max_workers=min(len(quests), MAX_WORKERS))
        for q in quests:
            self.executor.submit(self._process_and_cleanup, q)
        logger.info(f'Started {len(quests)} quest(s) with {min(len(quests), MAX_WORKERS)} worker(s)')

    def run(self):
        logger.info(f'Quest Auto-Completer | Auto-accept: {"ON" if AUTO_ACCEPT else "OFF"} | Poll: {POLL_INTERVAL}s')
        cycle = 0
        while running:
            cycle += 1
            logger.info(f'-- Scan #{cycle} --')
            quests = self.fetch_quests()
            if not quests:
                logger.info('No quests available')
                if stop_event.wait(POLL_INTERVAL):
                    break
                continue
            enrolled = sum(is_enrolled(q) for q in quests)
            completed = sum(is_completed(q) for q in quests)
            completable = sum(is_completable(q) for q in quests)
            logger.info(f'Total: {len(quests)} | Enrolled: {enrolled} | Completed: {completed} | Completable: {completable}')

            quests = self.auto_accept(quests)
            with self.lock:
                actionable = [
                    q for q in quests
                    if is_enrolled(q) and not is_completed(q) and is_completable(q)
                    and q['id'] not in self.completed_ids
                    and q['id'] not in self.in_progress_ids
                ]
                for q in actionable:
                    self.in_progress_ids.add(q['id'])

            if actionable:
                self._spawn_workers(actionable)
            if stop_event.wait(POLL_INTERVAL):
                break

        if self.executor is not None:
            self.executor.shutdown(wait=False)
        logger.info('Quest autocompleter stopped')


def run_account(token, build_number):
    api = DiscordAPI(token, build_number)
    if not api.validate_token():
        logger.warning('Skipping account, token validation failed')
        return
    QuestAutocompleter(api).run()


def main():
    global running
    tokens = read_tokens()
    if not tokens:
        running = False
        return
    logger.info(f'Loaded {len(tokens)} token(s)')
    build_number = fetch_latest_build_number()
    account_threads = [threading.Thread(target=run_account, args=(t, build_number), daemon=True) for t in tokens]
    for t in account_threads:
        t.start()
    logger.info(f'Running {len(tokens)} account(s)')
    while running and any(t.is_alive() for t in account_threads):
        if stop_event.wait(1):
            break
    running = False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s', datefmt='%H:%M:%S')
    running = True
    stop_event.clear()
    main()