import bisect
from tooldelta.mc_bytes_packet import sub_chunk_request


def single_dimension_classifier(
    sub_chunks: list[tuple[int, int, int]],
) -> list[tuple[tuple[int, int], list[tuple[int, int, int]]]]:
    result: list[tuple[tuple[int, int], list[tuple[int, int, int]]]] = []
    usc_sort_x: dict[tuple[int, int, int], bool] = {}

    for sub_chunk in sorted(sub_chunks, key=lambda i: i[0]):
        usc_sort_x[sub_chunk] = True

    for sub_chunk in sorted(sub_chunks, key=lambda i: i[2]):
        if sub_chunk not in usc_sort_x:
            continue

        x, z = sub_chunk[0], sub_chunk[2]
        z_start, z_end = z, z + 255
        last_hit_sub_chunks = 0
        matrix: list[tuple[int, list[tuple[int, int]]]] = []

        best_x_start, best_hit_sub_chunks = 0, 0
        best_one: list[tuple[int, list[tuple[int, int]]]] = []
        best_center: tuple[int, int] = (0, 0)

        last_x = 0
        temp: list[tuple[int, int]] = []

        for i in usc_sort_x:
            if i[0] != last_x:
                if len(temp) > 0:
                    temp.sort(key=lambda i: i[1])
                    matrix.append((last_x, temp))
                    temp = []
                last_x = i[0]
            temp.append((i[1], i[2]))
        if len(temp) > 0:
            temp.sort(key=lambda i: i[1])
            matrix.append((last_x, temp))
            temp = []

        x_start, x_end, best_x_start = x - 127, x + 128, x - 127
        left = bisect.bisect_left(matrix, x_start, key=lambda i: i[0])
        right = bisect.bisect_right(matrix, x_end, key=lambda i: i[0])
        for i in matrix[left:right]:
            left = bisect.bisect_left(i[1], z_start, key=lambda i: i[1])
            right = bisect.bisect_right(i[1], z_end, key=lambda i: i[1])
            best_hit_sub_chunks += right - left
            last_hit_sub_chunks = best_hit_sub_chunks

        for x_start in range(x - 126, x + 1):
            hit_sub_chunks, x_end = last_hit_sub_chunks, x_start + 255

            ptr = bisect.bisect_left(matrix, x_start - 1, key=lambda i: i[0])
            sub_matrix = matrix[ptr : ptr + 1][0]
            if sub_matrix[0] == x_start - 1:
                left = bisect.bisect_left(sub_matrix[1], z_start, key=lambda i: i[1])
                right = bisect.bisect_right(sub_matrix[1], z_end, key=lambda i: i[1])
                hit_sub_chunks -= right - left

            ptr = bisect.bisect_right(matrix, x_end, key=lambda i: i[0])
            sub_matrix = matrix[ptr - 1 : ptr][0]
            if sub_matrix[0] == x_end:
                left = bisect.bisect_left(sub_matrix[1], z_start, key=lambda i: i[1])
                right = bisect.bisect_right(sub_matrix[1], z_end, key=lambda i: i[1])
                hit_sub_chunks += right - left

            if hit_sub_chunks > best_hit_sub_chunks:
                best_x_start = x_start
                best_hit_sub_chunks = hit_sub_chunks
            last_hit_sub_chunks = hit_sub_chunks

        x_start, x_end = best_x_start, best_x_start + 255
        left = bisect.bisect_left(matrix, x_start, key=lambda i: i[0])
        right = bisect.bisect_right(matrix, x_end, key=lambda i: i[0])
        for i in matrix[left:right]:
            left = bisect.bisect_left(i[1], z_start, key=lambda i: i[1])
            right = bisect.bisect_right(i[1], z_end, key=lambda i: i[1])
            best_one.append((i[0], i[1][left:right]))
            best_center = (
                (x_start + x_end) // 2 + 1,
                (z_start + z_end) // 2 + 1,
            )

        current_result: list[tuple[int, int, int]] = []

        for i in best_one:
            for j in i[1]:
                sub_chunk_pos = (i[0], j[0], j[1])
                current_result.append(sub_chunk_pos)
                del usc_sort_x[sub_chunk_pos]

        result.append((best_center, current_result))

    return result


def sub_chunk_classifier(
    sub_chunks: list[tuple[int, tuple[int, int, int]]],
) -> list[sub_chunk_request.SubChunkRequest]:
    result: list[sub_chunk_request.SubChunkRequest] = []

    sub_chunks_mapping: dict[int, list[tuple[int, int, int]]] = {}
    for i in sub_chunks:
        if i[0] not in sub_chunks_mapping:
            sub_chunks_mapping[i[0]] = []
        sub_chunks_mapping[i[0]].append(i[1])

    for dim_id, value in sub_chunks_mapping.items():
        for i in single_dimension_classifier(value):
            packet = sub_chunk_request.SubChunkRequest()

            packet.Dimension = dim_id
            packet.SubChunkPosX = i[0][0]
            packet.SubChunkPosY = 0
            packet.SubChunkPosZ = i[0][1]

            for j in i[1]:
                offset = (
                    j[0] - packet.SubChunkPosX,
                    j[1],
                    j[2] - packet.SubChunkPosZ,
                )
                for k in offset:
                    if k > 127 or k < -128:
                        raise Exception("sub_chunk_classifier: Should nerver happened")
                packet.Offsets.append(offset)

            result.append(packet)

    return result
