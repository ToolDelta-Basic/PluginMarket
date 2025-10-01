### 宠物背包清理 文档 by SuperScript
使用方法：
    - 清除所有玩家的宠物背包：
        - 放置一个命令方块输入 `tellraw @a[tag=robot] {"rawtext":[{"text":"clearbag_single"}]}`
        - 激活此命令方块即可清除所有人的宠物背包一次
    - 清除单个玩家的宠物背包：
        - 放置一个命令方块输入 `tellraw @a[tag=robot] {"rawtext":[{"text":"clearbag_single"},{"selector":"玩家目标选择器"}]}`
        - 激活此命令方块即可清除指定玩家背包一次
