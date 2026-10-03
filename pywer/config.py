# Minecraft Bedrock 1.21.50 (protocol 766) server configuration.

DEBUG = False          # connection-level debug (hex of important packets)
DEBUG_PACKETS = False  # packet tracing disabled by default; only protocol errors are logged
MAX_PLAYERS = 8
PORT = 19132
PROTOCOL = 766
GAME_VERSION = "1.21.50"
SERVER_TITLE = "§epywer-v0.9.1dev"
ENCRYPTION = True
# ---- proxy (WaterdogPE) support
# PROXY_MODE: the server sits behind a proxy such as WaterdogPE. The proxy already authenticated the
# player, so the login chain is never verified (Pywer is always offline) and the extra fields the
# proxy adds to the client data (Waterdog_IP / Waterdog_XUID) are read. Set via `--proxy` or PYWER_PROXY=1.
PROXY_MODE = False
# Encryption between proxy and server is optional (same machine / private network); None = keep ENCRYPTION.
PROXY_ENCRYPTION = None
COMPRESSION_THRESHOLD = 256
DEFAULT_SPAWN = (0, 100, 0)
GAMEMODE = 0                 # 0 survival, 1 creative
MAX_RADIUS = 4               # chunk radius streamed around each player
CHUNKS_PER_TICK = 4          # new chunks sent per movement packet while streaming
BREAK_INPUT_TIMEOUT = 0.5   # seconds without a CONTINUE_DESTROY_BLOCK before a break is cancelled
TERRAIN = True              # False = old behaviour (empty world, spawn 0,100,0) - use it to check if a problem comes from the terrain
USE_BLOCK_HASHES = True      # network block ids = FNV-1a hash of the block state (see the world blocks module)
SEND_ACTOR_IDS = False       # needs real data files (not in the PocketMine zip); try True later
SEND_BIOME_DEFS = False      # needs real biome_definitions.nbt; try True later
SEND_CREATIVE = True        # needs real creative items; try True later

# ---- world generation
MIN_Y, MAX_Y = -64, 319      # overworld height range of 1.21.50 (sub chunks -4..19)
SEA_LEVEL = 62
SEED = 1337
TREES = True
PLAINS_BIOME = 1             # biome_id_map.json: plains = 1