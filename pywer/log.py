from . import config

# Set to True at runtime (or config.DEBUG) to get verbose protocol tracing.
verbose = config.DEBUG

def log(tag, msg):
    print("[INFO] [%s] %s" % (tag, msg), flush=True)

def dbg(tag, msg, data=None):
    if not (config.DEBUG or verbose):
        return
    extra = ""
    if data is not None:
        extra = " len=%d %s%s" % (len(data), data[:48].hex(), "..." if len(data) > 48 else "")
    print("[DEBUG] [%s] %s%s" % (tag, msg, extra), flush=True)
