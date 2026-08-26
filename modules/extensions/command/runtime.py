import asyncio
import threading

from modules.extensions.command import main
from modules.utils.logger import get_logger

logger = get_logger('command')

_thread = None
_loop = None


def start():
    global _thread, _loop
    if main.running:
        return
    main.running = True
    _loop = asyncio.new_event_loop()
    _thread = threading.Thread(target=_run, name='command_runtime', daemon=True)
    _thread.start()


def _run():
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(main.main())
    except Exception:
        logger.exception('Command runtime crashed')
    finally:
        _loop.close()


def stop():
    main.running = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=15)