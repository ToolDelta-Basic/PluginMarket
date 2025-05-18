# 事件: 触发词
# 触发词: 蔡徐坤
execute as [玩家名] at @s run playsound mob.chicken.hurt @s
tellraw [玩家名] {"rawtext":[{"text": "§f不许鸡叫！"}]}