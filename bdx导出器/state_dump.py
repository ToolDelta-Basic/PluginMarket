import json


def bool_func(x):
    return ("false", "true")[x]


SPECIAL_KTYPE = {
    "door_hinge_bit": bool_func,
    "brewing_stand_slot_c_bit": bool_func,
    "infiniburn_bit": bool_func,
    "coral_hang_type_bit": bool_func,
    "attached_bit": bool_func,
    "button_pressed_bit": bool_func,
    "open_bit": bool_func,
    "age_bit": bool_func,
    "head_piece_bit": bool_func,
    "color_bit": bool_func,
    "persistent_bit": bool_func,
    "stripped_bit": bool_func,
    "disarmed_bit": bool_func,
    "rail_data_bit": bool_func,
    "brewing_stand_slot_a_bit": bool_func,
    "end_portal_eye_bit": bool_func,
    "update_bit": bool_func,
    "item_frame_photo_bit": bool_func,
    "item_frame_map_bit": bool_func,
    "stability_check": bool_func,
    "covered_bit": bool_func,
    "brewing_stand_slot_b_bit": bool_func,
    "upper_block_bit": bool_func,
    "upside_down_bit": bool_func,
    "triggered_bit": bool_func,
    "output_lit_bit": bool_func,
    "explode_bit": bool_func,
    "allow_underwater_bit": bool_func,
    "wall_post_bit": bool_func,
    "in_wall_bit": bool_func,
    "dead_bit": bool_func,
    "powered_bit": bool_func,
    "suspended_bit": bool_func,
    "occupied_bit": bool_func,
    "toggle_bit": bool_func,
    "drag_down": bool_func,
    "extinguished": bool_func,
    "conditional_bit": bool_func,
    "hanging": bool_func,
    "output_subtract_bit": bool_func,
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
