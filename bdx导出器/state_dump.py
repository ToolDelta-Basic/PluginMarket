import json

SPECIAL_KTYPE = {"conditional_bit": lambda x: ("false", "true")[x]}


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
