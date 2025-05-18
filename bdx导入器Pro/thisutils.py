def render_bar(
    current: float, total: float, left_color: str, right_color: str, length: int = 90
):
    render_blocks = ["", "▍", "▌", "▋", "▊", "▉"]  # "▍", "▌", "▋", "▊", "▉"
    biggest_block_len_max = length // 6
    biggest_block_eq = len(render_blocks) - 1
    progress1 = current / total
    prgs = int(biggest_block_len_max * biggest_block_eq * progress1)
    prgs_rest = biggest_block_len_max * biggest_block_eq - prgs
    square_count, render_block_index = divmod(prgs, biggest_block_eq)
    square_rest_count, render_block_rest_index = divmod(prgs_rest, biggest_block_eq)
    output_1 = "ࡇ" * square_count + render_blocks[render_block_index]
    output_rest = "ࡇ" * square_rest_count + render_blocks[render_block_rest_index]
    final_output = left_color + output_1 + right_color + output_rest
    return final_output
