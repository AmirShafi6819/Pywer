import signal
import sys
from .. import config
from .server import Server


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else config.PORT
    srv = Server(port)
    srv.banner()

    # Save on SIGTERM too, so `kill` and service managers persist the world like Ctrl+C does.
    def _terminate(_signum, _frame):
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, _terminate)
    except (ValueError, OSError):
        pass

    try:
        srv.run()
    except KeyboardInterrupt:
        print("bye")
    finally:
        try:
            srv.save_all(force=True)
            print("[INFO] [Storage] saved world and player data")
        except Exception as e:
            print("[INFO] [Storage] save on exit failed: %r" % (e,))


if __name__ == "__main__":
    main()