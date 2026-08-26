import time
import threading

from modules.utils.logger import get_logger
from modules.utils import topgg
from modules.bots.owo import runtime as owo
from modules.extensions.quest import runtime as quest
from modules.extensions.topgg import runtime as topgg_runtime
from modules.extensions.command import runtime as command_runtime

logger = get_logger('bot')

BOTS = {'owo': owo}
EXTENSIONS = {'quest': quest, 'topgg': topgg_runtime, 'command': command_runtime}

_running = False
_lock = threading.Lock()


class BotManager:
    def __init__(self):
        self._start_time = None

    def boot(self):
        for bot in BOTS.values():
            bot.boot()

    @staticmethod
    def reload():
        for bot in BOTS.values():
            if hasattr(bot, 'reload'):
                bot.reload()

    def start(self):
        global _running
        with _lock:
            if _running:
                return
            BotManager.reload()
            topgg.clear_stop()
            for bot in BOTS.values():
                bot.start_macro()
            for ext in EXTENSIONS.values():
                ext.start()
            _running = True
            self._start_time = time.time()
        logger.info('Started')

    def stop(self):
        global _running
        with _lock:
            if not _running:
                return
            for bot in BOTS.values():
                bot.stop_macro()
            for ext in EXTENSIONS.values():
                ext.stop()
            topgg.stop()
            _running = False
            self._start_time = None
        logger.info('Stopped')

    def shutdown(self):
        for bot in BOTS.values():
            bot.shutdown()
        for ext in EXTENSIONS.values():
            ext.stop()
        topgg.stop()

    def is_running(self):
        return _running

    def start_time(self):
        return self._start_time

    def status(self):
        return {name: bot.status() for name, bot in BOTS.items() if hasattr(bot, 'status')}

    def solve_captcha(self, captcha, answer=None):
        bot = BOTS.get(captcha.get('bot'))
        if bot and hasattr(bot, 'solve_captcha'):
            return bot.solve_captcha(captcha, answer)
        return None

    def delete_captcha(self, captcha):
        bot = BOTS.get(captcha.get('bot'))
        if bot and hasattr(bot, 'delete_captcha'):
            return bot.delete_captcha(captcha)
        return None