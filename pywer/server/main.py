import argparse
import os
import signal
from .. import config
from .server import Server


def _env_bool(name):
    v = os.environ.get(name)
    if v is None:
        return None
    return v.strip().lower() in ("1", "true", "yes", "on")


def main():
    ap = argparse.ArgumentParser(prog="pywer")
    ap.add_argument("port", nargs="?", type=int, default=config.PORT, help="UDP port (default %d)" % config.PORT)
    ap.add_argument("--bind", default=os.environ.get("PYWER_BIND", config.BIND),
                    help="address to bind (default %s)" % config.BIND)
    ap.add_argument("--proxy", action="store_true", help="run behind WaterdogPE (reads Waterdog_IP/Waterdog_XUID)")
    ap.add_argument("--no-encryption", action="store_true", help="disable packet encryption (proxy mode only)")
    args = ap.parse_args()

    env_proxy = _env_bool("PYWER_PROXY")
    config.PROXY_MODE = bool(args.proxy or env_proxy)
    env_enc = _env_bool("PYWER_ENCRYPTION")
    if config.PROXY_MODE:
        if args.no_encryption:
            config.PROXY_ENCRYPTION = False
        elif env_enc is not None:
            config.PROXY_ENCRYPTION = env_enc

    srv = None
    shutting_down = False

    # Save on SIGTERM too, so `kill` and service managers persist the world like Ctrl+C
    # does. A second signal while shutting down must not interrupt the shutdown itself.
    def _terminate(_signum, _frame):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        raise KeyboardInterrupt

    for _name in ("SIGINT", "SIGTERM"):
        try:
            signal.signal(getattr(signal, _name), _terminate)
        except (ValueError, OSError, AttributeError):
            pass

    try:
        srv = Server(args.port, bind=args.bind)
        srv.banner()
        if config.PROXY_MODE:
            print("Proxy mode: ON (WaterdogPE) | encryption: %s" % (
                "off" if config.PROXY_ENCRYPTION is False else "on" if config.ENCRYPTION else "off"), flush=True)
        srv.run()
        print("bye")
    except KeyboardInterrupt:
        print("bye")
    finally:
        if srv is not None:
            try:
                srv.stop()
            except Exception as e:
                print("[ERROR] [Server] shutdown failed: %r" % (e,), flush=True)


if __name__ == "__main__":
    main()
