# ---------------------------------------------------------------- PlayerAuthInputPacket decoding
from ..util.serializer import ByteReader
from .transaction import read_signed_block_pos, read_item_interaction_data
from .flags import (F_PERFORM_ITEM_INTERACTION, F_PERFORM_ITEM_STACK_REQUEST,
                    F_PERFORM_BLOCK_ACTIONS, BA_STOP_BREAK)

def parse_auth_input(body):
    """BedrockProtocol 35.0.3 PlayerAuthInputPacket decodePayload order.

    The item-interaction tail must be decoded exactly: a misparse there shifts every
    following field, which silently breaks the block actions in the same packet.
    """
    r = ByteReader(body)
    d = {"pitch": r.read_float(), "yaw": r.read_float()}
    d["pos"] = (r.read_float(), r.read_float(), r.read_float())
    d["move_x"] = r.read_float(); d["move_z"] = r.read_float(); d["head_yaw"] = r.read_float()
    d["flags"] = r.read_varuint(70)
    d["input_mode"] = r.read_varuint32(); d["play_mode"] = r.read_varuint32(); d["interaction_mode"] = r.read_varuint32()
    d["interact_rot"] = (r.read_float(), r.read_float())
    d["tick"] = r.read_varuint64()
    d["delta"] = (r.read_float(), r.read_float(), r.read_float())
    d["item_use"] = None; d["stack_request"] = None; d["block_actions"] = []

    # PlayerAuthInputFlags::PERFORM_ITEM_INTERACTION = 34
    if flag_set(d["flags"], F_PERFORM_ITEM_INTERACTION):
        d["item_use"] = read_item_interaction_data(r)

    # Item stack requests are used when server-authoritative block breaking is enabled.
    if flag_set(d["flags"], F_PERFORM_ITEM_STACK_REQUEST):
        req_id = r.read_varint32(); n = r.read_varuint32(); acts=[]
        for _ in range(n):
            at = r.read_u8()
            if at == 11:  # MineBlockStackRequestAction
                acts.append((at, r.read_varint32(), r.read_varint32(), r.read_varint32()))
            else:
                # Unknown action cannot be safely skipped without its schema. Stop parsing this optional tail.
                raise ValueError("unsupported ItemStackRequest action %d" % at)
        # ItemStackRequest::read finishes with filterStrings + filterStringCause. Skipping these
        # shifts everything after them - including the block actions in this same packet - and
        # made breaking restart in a loop on a real client.
        for _ in range(r.read_varuint32()): r.read_string()
        r.read_i32()
        d["stack_request"] = (req_id, acts)

    # PlayerBlockActions follow the optional tails when PERFORM_BLOCK_ACTIONS is present.
    if flag_set(d["flags"], F_PERFORM_BLOCK_ACTIONS):
        count = r.read_varint32()
        if count < 0 or count > 100: raise ValueError("too many block actions")
        for _ in range(count):
            action = r.read_varint32()
            if action == BA_STOP_BREAK:  # STOP_BREAK: PlayerBlockActionStopBreak has no payload
                d["block_actions"].append((action, None, 0))
            else:
                pos = read_signed_block_pos(r); face = r.read_varint32()
                d["block_actions"].append((action, pos, face))
    return d

def flag_set(flags, bit): return (flags >> bit) & 1 == 1
def resolve_on_off(flags, start, stop):
    """InGamePacketHandler::resolveOnOffInputFlags: True/False, or None when neither or both flags are set."""
    on, off = flag_set(flags, start), flag_set(flags, stop)
    return on if on != off else None