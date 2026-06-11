import math
from typing import Optional, Tuple

from .models import LandData


Position = Tuple[float, float, float]
Bounds = Tuple[Position, Position]


def sphere_intersects_box(
        center: Position,
        radius: float,
        min_pos: Position,
        max_pos: Position) -> bool:
    distance_sq = 0.0
    for i in range(3):
        if center[i] < min_pos[i]:
            distance_sq += (min_pos[i] - center[i]) ** 2
        elif center[i] > max_pos[i]:
            distance_sq += (center[i] - max_pos[i]) ** 2
    return distance_sq <= radius ** 2


def boxes_intersect(
        min_a: Position,
        max_a: Position,
        min_b: Position,
        max_b: Position) -> bool:
    return all(min_a[i] <= max_b[i] and max_a[i] >= min_b[i] for i in range(3))


def box_distance(pos: Position, min_pos: Position, max_pos: Position) -> float:
    distance_sq = 0.0
    for i in range(3):
        if pos[i] < min_pos[i]:
            distance_sq += (min_pos[i] - pos[i]) ** 2
        elif pos[i] > max_pos[i]:
            distance_sq += (pos[i] - max_pos[i]) ** 2
    return math.sqrt(distance_sq)


def bounds_from_center_size(
        center: Position, size: Tuple[int, int, int]) -> Bounds:
    length, height, width = size
    cx, cy, cz = center
    half = (length / 2, height / 2, width / 2)
    return (
        (cx - half[0], cy - half[1], cz - half[2]),
        (cx + half[0], cy + half[1], cz + half[2]),
    )


def distance_to_land(pos: Position, land: LandData) -> float:
    if land.is_box():
        min_pos, max_pos = land.get_bounds()
        return box_distance(pos, min_pos, max_pos)
    x, y, z = pos
    cx, cy, cz = land.center
    return math.sqrt((x - cx) ** 2 + (y - cy) **
                     2 + (z - cz) ** 2) - land.radius


def land_overlaps_candidate(
    land: LandData,
    center: Position,
    radius: int,
    shape: str,
    size: Optional[Tuple[int, int, int]] = None,
) -> bool:
    shape = LandData.normalize_shape(shape)
    if shape == "方形":
        candidate_bounds = bounds_from_center_size(
            center, LandData.normalize_size(size, radius))
        if land.is_box():
            return boxes_intersect(
                candidate_bounds[0],
                candidate_bounds[1],
                *land.get_bounds())
        return sphere_intersects_box(
            land.center,
            land.radius,
            candidate_bounds[0],
            candidate_bounds[1])
    if land.is_box():
        min_pos, max_pos = land.get_bounds()
        return sphere_intersects_box(center, radius, min_pos, max_pos)
    lx, ly, lz = land.center
    return (
        math.sqrt((center[0] - lx) ** 2 + (center[1] - ly) ** 2 + (center[2] - lz) ** 2)  # noqa: E501
        <= radius + land.radius
    )


def box_radius_for_size(size: Tuple[int, int, int]) -> int:
    return max(1, math.ceil(max(size) / 2))
