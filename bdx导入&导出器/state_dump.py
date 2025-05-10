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


def parse_block_states(states_str: str) -> dict:
    """将状态字符串解析为字典格式"""
    if not states_str or states_str == "{}":
        return {}
    
    # 去除开头和结尾的方括号
    if states_str.startswith("[") and states_str.endswith("]"):
        states_str = states_str[1:-1]
    else:
        return {}
    
    # 分割各个状态
    states_dict = {}
    parts = []
    
    # 处理字符串分割，考虑到JSON中可能包含逗号
    in_quotes = False
    current_part = ""
    
    for char in states_str:
        if char == '"' and (not current_part or current_part[-1] != '\\'):
            in_quotes = not in_quotes
        
        if char == ',' and not in_quotes:
            parts.append(current_part)
            current_part = ""
        else:
            current_part += char
    
    if current_part:
        parts.append(current_part)
    
    # 解析每个状态项
    for part in parts:
        try:
            key_val = part.split("=", 1)
            if len(key_val) != 2:
                continue
                
            key, value = key_val
            
            # 解析键
            try:
                key = json.loads(key)
            except:
                continue
            
            # 对于布尔值特殊处理
            if key in SPECIAL_KTYPE and SPECIAL_KTYPE[key] == bool_func:
                if value == "true":
                    value = True
                elif value == "false":
                    value = False
                else:
                    try:
                        value = json.loads(value)
                    except:
                        continue
            else:
                try:
                    value = json.loads(value)
                except:
                    continue
                    
            states_dict[key] = value
        except:
            continue
    
    return states_dict
