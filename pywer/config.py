# Minecraft Bedrock 1.21.50 (protocol 766) server configuration.
"""Server configuration.

Two files are read from the server directory when this module is first imported:

* ``server.properties`` - the short, user facing settings (port, motd, gamemode, seed, ...).
* ``pywer.yml`` - the advanced settings for developers (protocol, terrain, streaming, debugging).

Precedence, lowest to highest: built-in defaults, ``pywer.yml``, ``server.properties``,
then environment variables and command line flags (see :mod:`pywer.server.main`).
Both files are written with their defaults on the first start, so they are always there
to be edited. ``PYWER_CONFIG_DIR`` overrides the directory they are looked up in.
"""

import os
from pathlib import Path

PROPERTIES_FILE = "server.properties"
YAML_FILE = "pywer.yml"
ENV_DIR = "PYWER_CONFIG_DIR"

# A value in server.properties / pywer.yml that is not a valid option only produces a warning;
# a broken file never stops the server from starting.
_WARNINGS = []

# Distinguishes "the user did not set this" from "the user set this to null".
_MISSING = object()


# ------------------------------------------------------------------ option schema
# Every tunable is declared once here. The schema drives the defaults below, the parsing, the
# type checking and the two generated template files, so they can never drift apart.
# (target, kind, key, default, comment, section) - a None section means server.properties.
def _opt(target, kind, key, default, doc, section=None):
    return (target, kind, key, default, doc, section)


# ---- server.properties: the settings an ordinary user is expected to touch
SIMPLE = [
    _opt("PORT", "int", "server-port", 19132, "UDP port the server listens on."),
    _opt("BIND", "str", "server-ip", "0.0.0.0", "Address to bind to (0.0.0.0 = every interface)."),
    _opt("SERVER_TITLE", "str", "motd", "§epywer-v0.9.1dev", "Server name shown in the client's server list."),
    _opt("MAX_PLAYERS", "int", "max-players", 8, "Players allowed at the same time."),
    _opt("GAMEMODE", "int", "gamemode", 0, "0 = survival, 1 = creative."),
    _opt("SEED", "int", "level-seed", 1337, "World seed, used until a world has been saved to world_data/."),
    _opt("MAX_RADIUS", "int", "view-distance", 4, "Chunk radius streamed around each player."),
    _opt("SPAWN_X", "int", "spawn-x", 0, "Fallback spawn X, only used when terrain generation is off."),
    _opt("SPAWN_Y", "int", "spawn-y", 100, "Fallback spawn Y, only used when terrain generation is off."),
    _opt("SPAWN_Z", "int", "spawn-z", 0, "Fallback spawn Z, only used when terrain generation is off."),
]

# ---- pywer.yml: the knobs a developer tunes while working on the server itself
ADVANCED = [
    _opt("ENCRYPTION", "bool", "encryption", True,
         "Encrypt packets with the client. Turn off only to inspect traffic on a trusted network.", "network"),
    _opt("COMPRESSION_THRESHOLD", "int", "compression-threshold", 256,
         "Batch size in bytes above which a packet is zlib compressed.", "network"),
    _opt("PROXY_MODE", "bool", "mode", False,
         "The server sits behind a proxy such as WaterdogPE, which already authenticated the player.", "proxy"),
    _opt("PROXY_ENCRYPTION", "optbool", "encryption", None,
         "Encrypt the proxy connection. null keeps the network.encryption value.", "proxy"),
    _opt("PROTOCOL", "int", "version", 766,
         "Bedrock protocol number. 766 = 1.21.50. Clients on another protocol cannot join.", "protocol"),
    _opt("GAME_VERSION", "str", "game-version", "1.21.50",
         "Game version reported to the client, must match the protocol above.", "protocol"),
    _opt("TERRAIN", "bool", "terrain", True,
         "Generate terrain. False gives an empty world at the spawn below, which isolates terrain bugs.", "world"),
    _opt("MIN_Y", "int", "min-y", -64, "Lowest buildable Y of the overworld.", "world"),
    _opt("MAX_Y", "int", "max-y", 319, "Highest buildable Y of the overworld.", "world"),
    _opt("SEA_LEVEL", "int", "sea-level", 62, "Y of the water surface.", "world"),
    _opt("TREES", "bool", "trees", True, "Generate trees on grass.", "world"),
    _opt("PLAINS_BIOME", "int", "biome", 1, "Biome id sent for every chunk (1 = plains).", "world"),
    _opt("CHUNKS_PER_TICK", "int", "chunks-per-tick", 4,
         "New chunks sent per movement packet while a player is streaming in.", "streaming"),
    _opt("BREAK_INPUT_TIMEOUT", "float", "break-input-timeout", 0.5,
         "Seconds without a continue-destroy-block packet before a block break is cancelled.", "gameplay"),
    _opt("USE_BLOCK_HASHES", "bool", "use-block-hashes", True,
         "Send network block ids as an FNV-1a hash of the block state instead of a palette index.", "gameplay"),
    _opt("SEND_CREATIVE", "bool", "send-creative", True, "Send the creative item list to joining players.", "packets"),
    _opt("SEND_ACTOR_IDS", "bool", "send-actor-ids", False,
         "Send the actor id table. Needs real data files that are not shipped yet.", "packets"),
    _opt("SEND_BIOME_DEFS", "bool", "send-biome-defs", False,
         "Send biome_definitions.nbt. Needs a real file that is not shipped yet.", "packets"),
    _opt("DEBUG", "bool", "connection", False,
         "Log the hex of important packets, so start-up and login can be followed.", "debug"),
    _opt("DEBUG_PACKETS", "bool", "packets", False, "Log every packet id that passes through a session.", "debug"),
]

_OPTIONS = SIMPLE + ADVANCED
DEFAULTS = {target: default for target, _kind, _key, default, _doc, _section in _OPTIONS}

# ------------------------------------------------------------------ value coercion
# YAML keeps 1 and 0 as numbers while a properties file treats them as booleans, so the sets differ.
_BOOL_TRUE = ("true", "yes", "on")
_BOOL_FALSE = ("false", "no", "off")
_PROP_TRUE = ("1",) + _BOOL_TRUE
_PROP_FALSE = ("0",) + _BOOL_FALSE
_NULL = ("", "null", "none", "~")


def _to_bool(text):
    if text in _PROP_TRUE:
        return True
    if text in _PROP_FALSE:
        return False
    raise ValueError("expected true or false, got %r" % (text,))


def _coerce(kind, raw, path, key):
    """Convert a raw text value to the type the option expects, or raise ValueError."""
    if kind == "str":
        return raw
    if isinstance(raw, list):
        raise ValueError("%s: '%s' takes a single value, not a list" % (path, key))
    text = str(raw).strip()
    try:
        if kind == "optbool":
            return None if text.lower() in _NULL else _to_bool(text.lower())
        if kind == "bool":
            return _to_bool(text.lower())
        if kind == "int":
            try:
                return int(text, 0)  # 0x / 0o / 0b prefixes
            except ValueError:
                return int(text)
        if kind == "float":
            return float(text)
    except ValueError as exc:
        raise ValueError("%s: '%s' must be %s (%s)" % (path, key, kind, exc)) from None
    raise ValueError("%s: '%s' has an unknown type %r" % (path, key, kind))


# ------------------------------------------------------------------ server.properties
def parse_properties(text):
    """Parse a ``key=value`` properties file into a lowercased dict.

    ``#`` and ``!`` start a comment, a trailing backslash continues on the next line, and both
    ``=`` and ``:`` separate a key from its value. Every value is kept as text; the schema decides
    how to type it.
    """
    data = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or line[0] in "#!":
            continue
        while line.endswith("\\") and index < len(lines):
            line = line[:-1] + lines[index].strip()
            index += 1
        key, sep, value = line.partition("=")
        if not sep:
            key, sep, value = line.partition(":")
        if not sep:
            _WARNINGS.append("%s: ignoring line without a '=' or ':' -> %r" % (PROPERTIES_FILE, line))
            continue
        data[key.strip().lower()] = value.strip()
    return data


# ------------------------------------------------------------------ pywer.yml
def _strip_comment(line):
    """Remove a trailing ``#`` comment, leaving ``#`` alone inside quotes or in the middle of a word."""
    out = []
    quote = ""
    for char in line:
        if quote:
            out.append(char)
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#" and (not out or out[-1] in " \t"):
            break
        out.append(char)
    return "".join(out).rstrip()


def _parse_yaml_scalar(text):
    """Turn one YAML scalar into a Python value: int, float, bool, None, list or str."""
    text = text.strip()
    if not text:
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_parse_yaml_scalar(part) for part in inner.split(",")] if inner else []
    low = text.lower()
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False
    if low in _NULL:
        return None
    try:
        return int(text, 0)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def parse_yaml(text):
    """Parse the subset of YAML that pywer.yml needs into nested dicts and lists.

    Supported: nested mappings by indentation, block lists (``- item``) and inline lists
    (``[a, b]``), ``#`` comments, ``key: value`` pairs, and the scalars int / float / bool / null /
    quoted string / plain string. Not supported: anchors, multi-line scalars and inline mappings -
    they are not needed by the schema and are reported as errors instead of being misread.
    """
    lines = []
    for number, raw in enumerate(text.splitlines(), 1):
        body = _strip_comment(raw)
        if body.strip():
            lines.append((number, len(body) - len(body.lstrip(" ")), body.strip()))

    root = {}
    stack = [(-1, root)]  # (indent, container)
    index = 0
    while index < len(lines):
        number, indent, body = lines[index]
        if body == "-" or body.startswith("- "):
            container = stack[-1][1]
            if not isinstance(container, list):
                raise ValueError("line %d: list item without a list above it" % number)
            container.append(_parse_yaml_scalar(body[1:].strip()))
            index += 1
            continue
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not isinstance(parent, dict):
            raise ValueError("line %d: expected 'key: value', got %r" % (number, body))
        key, sep, rest = body.partition(":")
        if not sep:
            raise ValueError("line %d: expected 'key: value', got %r" % (number, body))
        key = key.strip()
        rest = rest.strip()
        if rest:
            parent[key] = _parse_yaml_scalar(rest)
        else:
            following = lines[index + 1] if index + 1 < len(lines) else None
            if following is not None and following[1] > indent:
                if following[2] == "-" or following[2].startswith("- "):
                    child = []
                else:
                    child = {}
                parent[key] = child
                stack.append((indent, child))
            else:
                parent[key] = None  # a key with nothing under it is null, not an empty section
        index += 1
    return root


def _dig(data, section, key):
    """Read ``section.key`` out of a parsed config mapping.

    Returns _MISSING when the key is absent, so an explicit ``encryption: null`` can be told
    apart from a line the user simply did not write.
    """
    node = data.get(section) if section else data
    if not isinstance(node, dict) or key not in node:
        return _MISSING
    return node[key]


# ------------------------------------------------------------------ template rendering
def _yaml_value(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or text.lower() in _BOOL_TRUE + _BOOL_FALSE + _NULL:
        return '"%s"' % text
    try:
        float(text)
        return '"%s"' % text
    except ValueError:
        pass
    if any(char in text for char in ":#{}[],&*?|-<>=!%@`\"'\n\t") or text != text.strip():
        return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')
    return text


def render_properties():
    """Build the text of a server.properties holding every default."""
    lines = [
        "# server.properties - Pywer server settings",
        "#",
        "# One 'key=value' per line. '#' starts a comment. Values are case sensitive, keys are not.",
        "# Delete a line to fall back to the default shown here.",
        "",
    ]
    for target, _kind, key, default, doc, _section in SIMPLE:
        lines.append("# %s" % doc)
        lines.append("%s=%s" % (key, default))
        lines.append("")
    return "\n".join(lines)


def render_yaml():
    """Build the text of a pywer.yml holding every default."""
    lines = [
        "# pywer.yml - Pywer advanced configuration",
        "#",
        "# Settings for people working on the server itself. server.properties is the file to edit",
        "# for everyday play; this one is for protocol, world generation, streaming and debugging.",
        "# Values are 'key: value', grouped by section. '#' starts a comment.",
        "# Delete a line to fall back to the default shown here.",
        "",
    ]
    section = None
    for target, _kind, key, default, doc, name in ADVANCED:
        if name != section:
            section = name
            lines.append("%s:" % name)
        lines.append("  # %s" % doc)
        lines.append("  %s: %s" % (key, _yaml_value(default)))
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ loading
def _search_dirs():
    dirs = []
    override = os.environ.get(ENV_DIR)
    if override:
        dirs.append(Path(override))
    dirs.append(Path.cwd())
    # A source checkout keeps the files next to the package, so `python -m pywer` from anywhere
    # still finds them.
    dirs.append(Path(__file__).resolve().parent.parent)
    return dirs


def _find(name):
    for directory in _search_dirs():
        path = directory / name
        if path.is_file():
            return path
    return None


def _write_templates():
    """Create a missing config file with the defaults, in the server directory."""
    directory = Path(os.environ.get(ENV_DIR) or Path.cwd())
    for name, render in ((PROPERTIES_FILE, render_properties), (YAML_FILE, render_yaml)):
        path = directory / name
        if path.exists():
            continue
        try:
            path.write_text(render(), encoding="utf-8")
        except OSError as exc:
            print("[WARN] [Config] could not create %s: %s" % (path, exc), flush=True)


def _apply(text, name, entries, read):
    """Apply one parsed config file onto DEFAULTS, warning about anything it gets wrong."""
    for target, kind, key, _default, _doc, section in entries:
        raw = read(text, section, key)
        if raw is _MISSING:
            continue
        try:
            DEFAULTS[target] = _coerce(kind, raw, name, "%s:%s" % (section, key) if section else key)
        except ValueError as exc:
            _WARNINGS.append(str(exc))


def load():
    """Read both config files into DEFAULTS. Called once when this module is imported."""
    _write_templates()
    path = _find(YAML_FILE)
    if path is not None:
        try:
            _apply(parse_yaml(path.read_text(encoding="utf-8")), YAML_FILE, ADVANCED, _dig)
        except (OSError, ValueError) as exc:
            _WARNINGS.append("ignoring %s: %s" % (path, exc))
    path = _find(PROPERTIES_FILE)
    if path is not None:
        try:
            _apply(parse_properties(path.read_text(encoding="utf-8")), PROPERTIES_FILE, SIMPLE, _dig)
        except (OSError, ValueError) as exc:
            _WARNINGS.append("ignoring %s: %s" % (path, exc))


def as_dict():
    """The effective configuration, in declaration order."""
    return {target: DEFAULTS[target] for target, _kind, _key, _default, _doc, _section in _OPTIONS}


def reload():
    """Re-read both config files. Values that were changed on the module at runtime are lost."""
    DEFAULTS.clear()
    DEFAULTS.update({target: default for target, _kind, _key, default, _doc, _section in _OPTIONS})
    _WARNINGS.clear()
    load()
    _publish()
    return DEFAULTS


def _publish():
    """Expose the effective configuration as module attributes (config.PORT, config.MAX_Y, ...)."""
    values = as_dict()
    values["DEFAULT_SPAWN"] = (values.pop("SPAWN_X"), values.pop("SPAWN_Y"), values.pop("SPAWN_Z"))
    globals().update(values)
    for warning in _WARNINGS:
        print("[WARN] [Config] %s" % warning, flush=True)
    _WARNINGS.clear()


load()
_publish()
