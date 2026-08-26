_socketio = None


def set_socketio(sio):
    global _socketio
    _socketio = sio


def emit(event, data, room=None):
    if _socketio:
        if room:
            _socketio.emit(event, data, room=room, namespace='/')
        else:
            _socketio.emit(event, data, namespace='/')