import logging
import threading
import time

from modules.utils import topgg

logger = logging.getLogger('top.gg')

running = False
stop_event = threading.Event()

POLL_INTERVAL = 3600


def read_accounts():
    accounts = []
    try:
        with open('data/topgg.txt', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.lstrip().startswith('#'):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    accounts.append((parts[0], parts[1]))
    except FileNotFoundError:
        logger.warning('Top.gg data file not found: data/topgg.txt')
    return accounts


def vote_account(token, bot_id):
    logger.info(f'Voting for bot {bot_id}')
    if topgg.vote(bot_id, token):
        logger.info('Voted (next in 12h)')
        return 12 * 3600
    return 0


def main():
    global running
    accounts = read_accounts()
    if not accounts:
        running = False
        return
    logger.info(f'Loaded {len(accounts)} account(s)')
    schedule = [[token, bot_id, 0.0] for token, bot_id in accounts]
    cycle = 0
    while running:
        cycle += 1
        logger.info(f'-- Vote cycle #{cycle} --')
        for i, entry in enumerate(schedule, 1):
            if not running:
                break
            token, bot_id, next_at = entry
            if time.time() < next_at:
                continue
            logger.info(f'Voting ({i}/{len(accounts)})')
            retry = vote_account(token, bot_id)
            entry[2] = time.time() + (retry or POLL_INTERVAL)
        next_due = min(max(1.0, e[2] - time.time()) for e in schedule)
        if stop_event.wait(next_due):
            break
    running = False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s', datefmt='%H:%M:%S')
    running = True
    stop_event.clear()
    main()