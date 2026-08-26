import asyncio
import threading

from modules.utils.data_store import read_json, deep_merge
from modules.utils import cache
from modules.utils.logger import get_logger
from modules.bots.owo.client import OWOClient
from modules.bots.owo.defaults import OWO_DEFAULT_CONFIG
from modules.bots.owo.captcha import Captcha
from modules.bots.owo.interaction import Interaction

logger = get_logger('owo')

loop = None
thread = None
clients = []
clients_by_user = {}
interaction = None


def status():
    accounts = read_json('data/owo.json', {}) or {}
    return {
        'running': any(c.macro_enabled for c in clients),
        'accounts': len(clients),
        'configured': len(accounts),
        'captchas': cache.count('owo'),
    }


def boot():
    global loop, thread, interaction
    if loop:
        return

    interaction = Interaction(clients)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=run_loop, name='owo_runtime', daemon=True)
    thread.start()
    asyncio.run_coroutine_threadsafe(start_accounts(), loop)


def run_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()


async def start_accounts():
    accounts = load_accounts()
    if not accounts:
        logger.warning('No OWO accounts configured')
        return

    index = 0
    total = len(accounts)
    for token_text, config in accounts.items():
        index += 1
        client = OWOClient(token=token_text, config=config, clients=clients, interaction=interaction)
        clients.append(client)
        asyncio.create_task(run_client(client, token_text), name=f'owo_account_{index}')
        logger.info(f'Initializing account ({index}/{total})')


def load_accounts():
    raw_accounts = read_json('data/owo.json', {}) or {}
    return {
        token_text: deep_merge(OWO_DEFAULT_CONFIG, config)
        for token_text, config in raw_accounts.items()
        if token_text
    }


async def run_client(client, token_text):
    try:
        await client.start(token_text)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning(f'OWO client error: {exc}')
    finally:
        if not client.is_closed():
            try:
                await client.close()
            except Exception:
                logger.exception('Failed to close OWO client')
        if client.user is None and client in clients:
            clients.remove(client)
            logger.warning('Removed account that failed to log in')


def start_macro():
    if not loop or not loop.is_running():
        return False
    for client in clients:
        client.macro_enabled = True
    logger.info('OWO macro started')
    return True


def stop_macro():
    for client in clients:
        client.macro_enabled = False
        client.reset_quest_state()
    logger.info('OWO macro stopped')


def shutdown():
    global loop, thread, interaction
    if not loop:
        return

    for client in clients:
        client.macro_enabled = False

    if loop.is_running():
        future = asyncio.run_coroutine_threadsafe(stop_accounts(), loop)
        try:
            future.result(timeout=20)
        except Exception:
            logger.exception('OWO shutdown failed')
        loop.call_soon_threadsafe(loop.stop)

    if thread and thread.is_alive():
        thread.join(timeout=10)

    clients.clear()
    clients_by_user.clear()
    interaction = None
    loop = None
    thread = None


async def stop_accounts():
    await asyncio.gather(*(client.stop_runtime() for client in clients), return_exceptions=True)
    if interaction:
        interaction.stop()


def solve_captcha(captcha, answer=None):
    if not loop or not loop.is_running():
        return None
    client = find_client(captcha)
    if not client:
        return None
    return asyncio.run_coroutine_threadsafe(Captcha.handle_web_solve(client, captcha, answer), loop)


def delete_captcha(captcha):
    if not loop or not loop.is_running():
        return None
    client = find_client(captcha)
    if not client:
        return None
    return asyncio.run_coroutine_threadsafe(Captcha.handle_web_delete(client), loop)


def find_client(captcha):
    user_id = str(captcha.get('user_id', ''))
    if user_id in clients_by_user:
        return clients_by_user[user_id]

    for client in clients:
        user = getattr(client, 'user', None)
        if user and str(user.id) == user_id:
            clients_by_user[user_id] = client
            return client


def reload():
    if not loop or not loop.is_running():
        return

    future = asyncio.run_coroutine_threadsafe(reload_accounts(), loop)
    try:
        future.result(timeout=60)
    except Exception:
        logger.exception('OWO reload failed')


async def reload_accounts():
    await asyncio.gather(*(client.stop_runtime() for client in clients), return_exceptions=True)

    clients.clear()
    clients_by_user.clear()
    if interaction:
        interaction.reset()

    await start_accounts()