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

    srv = Server(args.port, bind=args.bind)
    srv.banner()
    if config.PROXY_MODE:
        print("Proxy mode: ON (WaterdogPE) | encryption: %s" % (
            "off" if config.PROXY_ENCRYPTION is False else "on" if config.ENCRYPTION else "off"), flush=True)

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
