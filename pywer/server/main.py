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


def make_shutdown_handler():
    """SIGINT/SIGTERM handler for a server that is already tearing down.

    First signal: start a clean shutdown (plugins, scheduler, workers, world saves).

    Every later signal is an operator saying "this shutdown is stuck, get me out".
    It must never be swallowed: the handler restores the default disposition for that
    signal, so the *next* Ctrl+C terminates the process even when we are parked inside
    C code where a Python handler cannot run at all, and it raises immediately so the
    frame that is already wedged starts unwinding instead of waiting for it to return.
    """
    state = {"shutting_down": False}

    def handler(signum, _frame):
        if not state["shutting_down"]:
            state["shutting_down"] = True
            raise KeyboardInterrupt
        try:
            signal.signal(signum, signal.SIG_DFL)
        except (ValueError, OSError):
            pass
        raise KeyboardInterrupt

    handler.state = state
    return handler


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

    # Save on SIGTERM too, so `kill` and service managers persist the world like Ctrl+C
    # does. A second signal while shutting down is an escape hatch, not something to drop.
    handler = make_shutdown_handler()
    for _name in ("SIGINT", "SIGTERM"):
        try:
            signal.signal(getattr(signal, _name), handler)
        except (ValueError, OSError, AttributeError):
            pass

    try:
        srv = Server(args.port, bind=args.bind)
        srv.banner()
        if config.PROXY_MODE:
            print("Proxy mode: ON (WaterdogPE) | encryption: %s" % (
                "off" if config.PROXY_ENCRYPTION is False else "on" if config.ENCRYPTION else "off"), flush=True)
        srv.run()
    except KeyboardInterrupt:
        pass
    finally:
        if srv is not None:
            try:
                srv.stop()
            except Exception as e:
                print("[ERROR] [Server] shutdown failed: %r" % (e,), flush=True)
            # Printed only after persistence has finished, so the console never says
            # "bye" and then logs the save that was still running underneath it.
            print("bye")


if __name__ == "__main__":
    main()
