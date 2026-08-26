import threading

from modules.extensions.quest import main

_thread = None


def start():
    global _thread
    if main.running:
        return
    main.running = True
    main.stop_event.clear()
    _thread = threading.Thread(target=main.main, name='quest', daemon=True)
    _thread.start()


def stop():
    main.running = False
    main.stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=15)