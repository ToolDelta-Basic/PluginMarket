from tooldelta import Plugin, plugin_entry ,game_utils
import sys

def getItem(target: str, itemName: str, itemSpecialID: int = -1) -> int:
    """
    获取玩家背包内指定的物品的数量
    Args:
        targetName (str): 玩家选择器 / 玩家名
        itemName (str): 物品 ID
        itemSpecialID (int): 物品特殊值，默认值 -1
    """
    game_ctrl = game_utils._get_game_ctrl()
    if (
        (target not in game_ctrl.allplayers)
        and (target != game_ctrl.bot_name)
        and (not target.startswith("@a"))
    ):
        raise ValueError("未找到目标玩家")
    target = game_utils.to_player_selector(target)
    result = game_ctrl.sendwscmd_with_resp(
        f"/clear {target} {itemName} {itemSpecialID} 0"
    )
    if result.OutputMessages[0].Message == "commands.generic.syntax":
        raise ValueError("物品 ID 错误")
    if result.OutputMessages[0].Message == "commands.clear.failure.no.items":
        return 0
    # TODO!!! 租赁服的/clear指令返回会乘以2 再除2(抵消)
    return int(result.OutputMessages[0].Parameters[1])

game_utils.getItem = getItem
sys.modules["tooldelta.game_utils"] = game_utils
class FixGetItemPlugin(Plugin):
    name = "fix_getItem"
    author = "Mono"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
    

entry = plugin_entry(FixGetItemPlugin)
