import logging
import sys
import time
from collections import deque

_ws_handler = None
_streams_hooked = False


class WebSocketHandler(logging.Handler):
    def __init__(self, max_buffer=100000):
        super().__init__()
        self.buffer = deque(maxlen=max_buffer)
        self.names = {}
        self.socketio = None
        self.seq = 0

    def set_socketio(self, sio):
        self.socketio = sio

    def emit(self, record):
        try:
            self.push(record.levelname, record.name, self.format(record), record.created)
        except Exception:
            self.handleError(record)

    def push(self, level, name, message, created=None):
        self.seq += 1
        entry = {
            'seq': self.seq,
            'time': time.strftime('%H:%M:%S', time.localtime(created or time.time())),
            'level': level,
            'name': name,
            'message': message.rstrip(),
        }
        if len(self.buffer) == self.buffer.maxlen:
            dropped = self.buffer[0]['name']
            count = self.names.get(dropped, 0) - 1
            if count:
                self.names[dropped] = count
            else:
                self.names.pop(dropped, None)
        self.buffer.append(entry)
        self.names[name] = self.names.get(name, 0) + 1
        if self.socketio:
            self.socketio.emit('log', entry, namespace='/')

    def get_buffer(self, limit=1000, before=None, after=None):
        if before is not None:
            filtered = [e for e in self.buffer if e['seq'] < before]
            return filtered[-limit:], len(filtered) > limit
        if after is not None:
            filtered = [e for e in self.buffer if e['seq'] > after]
            return filtered[:limit], len(filtered) > limit
        logs = list(self.buffer)
        return logs[-limit:], len(logs) > limit

    def get_names(self):
        return sorted(self.names)


class TerminalStream:
    def __init__(self, stream, level):
        self.stream = stream
        self.level = level
        self.line = ''

    def write(self, text):
        self.stream.write(text)
        self.line += text
        while '\n' in self.line:
            line, self.line = self.line.split('\n', 1)
            if line.strip():
                get_ws_handler().push(self.level, 'terminal', line)

    def flush(self):
        self.stream.flush()
        if self.line.strip():
            get_ws_handler().push(self.level, 'terminal', self.line)
            self.line = ''


def get_ws_handler():
    global _ws_handler
    if _ws_handler is None:
        _ws_handler = WebSocketHandler()
        _ws_handler.setFormatter(logging.Formatter('%(message)s'))
    return _ws_handler


def setup_logging():
    global _streams_hooked
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    try:
        sys.__stdout__.reconfigure(encoding='utf-8', errors='replace')
        sys.__stderr__.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    for h in list(root.handlers):
        root.removeHandler(h)

    console = logging.StreamHandler(sys.__stdout__)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%H:%M:%S',
    ))

    handler = get_ws_handler()
    handler.setLevel(logging.INFO)

    root.addHandler(console)
    root.addHandler(handler)

    if not _streams_hooked:
        sys.stdout = TerminalStream(sys.__stdout__, 'INFO')
        sys.stderr = TerminalStream(sys.__stderr__, 'ERROR')
        _streams_hooked = True

    for name in ('werkzeug', 'engineio', 'socketio'):
        l = logging.getLogger(name)
        l.setLevel(logging.WARNING)
        l.propagate = True

    return handler


def get_logger(name):
    return logging.getLogger(name)