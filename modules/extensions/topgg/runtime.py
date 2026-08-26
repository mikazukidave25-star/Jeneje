import threading

from modules.extensions.topgg import main

_thread = None


def start():
    global _thread
    if main.running:
        return
    main.running = True
    main.stop_event.clear()
    _thread = threading.Thread(target=main.main, name='topgg', daemon=True)
    _thread.start()


def stop():
    main.running = False
    main.stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=15)