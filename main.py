from modules.utils.logger import setup_logging, get_logger, get_ws_handler
from modules.utils.ws import set_socketio
from bot import BotManager
from app import socketio, set_bot_manager, run_server

import os


def main():
    setup_logging()
    logger = get_logger('main')
    logger.info('Initializing')

    set_socketio(socketio)
    get_ws_handler().set_socketio(socketio)

    bot_manager = BotManager()
    bot_manager.boot()
    set_bot_manager(bot_manager)

    try:
        port = int(os.environ.get('PORT', 2010))
        run_server(host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        logger.info('Shutting down')
    except Exception:
        logger.exception('Server error')
    finally:
        bot_manager.shutdown()


if __name__ == '__main__':
    main()