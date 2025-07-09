from dataclasses import dataclass
import threading

if 0:
    import nbtlib


@dataclass
class PairChest:
    _structure_unique_id: str

    is_pairlead: bool
    current_pos: tuple[int, int, int]
    another_pos: tuple[int, int, int]

    def set_structure_unique_id(self, structure_unique_id: str):
        self._structure_unique_id = structure_unique_id

    def get_structure_unique_id(self) -> str | None:
        if len(self._structure_unique_id) == 0:
            return None
        return self._structure_unique_id


class ChestCache:
    _mu: threading.Lock
    _cache: dict[
        str,
        dict[tuple[int, int, int], PairChest],
    ]

    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._cache = {}

    def nbt_to_chest(
        self, real_pos: tuple[int, int, int], block_nbt: "nbtlib.tag.Compound"
    ) -> PairChest | None:
        if "forceunpair" in block_nbt and block_nbt["forceunpair"] == 1:
            return None

        if "pairlead" not in block_nbt:
            return None

        return PairChest(
            "",
            block_nbt["pairlead"] == 1,
            real_pos,
            (
                int(block_nbt["pairx"] - block_nbt["x"]) + real_pos[0],
                real_pos[1],
                int(block_nbt["pairz"] - block_nbt["z"]) + real_pos[2],
            ),
        )

    def add_chest(self, requester: str, chest: PairChest):
        with self._mu:
            if requester not in self._cache:
                self._cache[requester] = {}
            self._cache[requester][chest.current_pos] = chest

    def find_chest(
        self, requester: str, oneOfTwoChests: PairChest, find_pairlead: bool
    ) -> PairChest | None:
        with self._mu:
            if requester not in self._cache:
                return None
            if (
                oneOfTwoChests.current_pos not in self._cache[requester]
                or oneOfTwoChests.another_pos not in self._cache[requester]
            ):
                return None

            chest_a = self._cache[requester][oneOfTwoChests.current_pos]
            chest_b = self._cache[requester][oneOfTwoChests.another_pos]

            if find_pairlead:
                if chest_a.is_pairlead:
                    return chest_a
                elif chest_b.is_pairlead:
                    return chest_b
                else:
                    raise Exception("find_chest: Should nerver happened")
            else:
                if not chest_a.is_pairlead:
                    return chest_a
                elif not chest_b.is_pairlead:
                    return chest_b
                else:
                    raise Exception("find_chest: Should nerver happened")

    def remove_chest_and_its_pair(self, requester: str, chest: PairChest):
        with self._mu:
            if requester not in self._cache:
                return
            if chest.current_pos in self._cache[requester]:
                del self._cache[requester][chest.current_pos]
            if chest.another_pos in self._cache[requester]:
                del self._cache[requester][chest.another_pos]
            if len(self._cache[requester]) == 0:
                del self._cache[requester]

    def remove_all_chests(self, requester: str):
        with self._mu:
            if requester in self._cache:
                del self._cache[requester]
