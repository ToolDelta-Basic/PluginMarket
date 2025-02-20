import json


def bool_func(x):
    return ("false", "true")[x]


SPECIAL_KTYPE = {
    "conditional_bit": bool_func,
    "upside_down_bit": bool_func,
    "unstable": bool_func,
    "waterlogged": bool_func,
    "powered": bool_func,
    "locked": bool_func,
    "open": bool_func,
    "lit": bool_func,
    "open_bit": bool_func,
    "powered_bit": bool_func,
    "persistent_bit": bool_func,
    "update_bit": bool_func,
    "age_bit": bool_func,
    "end_portal_eye_bit": bool_func,
    "hanging": bool_func,
    "attached_bit": bool_func,
    "dead_bit": bool_func,
    "infiniburn_bit": bool_func,
    "active": bool_func,
    "natural": bool_func,
    "head_piece_bit": bool_func,
    "triggered_bit": bool_func,
}


def to_string(val: str):
    return json.dumps(val)


def to_key(key: str):
    return to_string(key)


def to_val_default(val: str):
    return json.dumps(val)


def dump_block_states(states: dict):
    states_strs = []
    for k, b in states.items():
        k_str = to_key(k)
        if k in SPECIAL_KTYPE:
            states_strs.append(f"{k_str}={SPECIAL_KTYPE[k](b)}")
        else:
            states_strs.append(f"{k_str}={to_string(b)}")
    return "[" + ",".join(states_strs) + "]"
