# 定时: 3600
tellraw @a {"rawtext": [{"text": "§e扫地姬 进入了游戏"}] }
sleep 1
tellraw @a {"rawtext": [{"text": "§f<§6扫地姬§f> 30s后就要扫地了， 请保管好掉落物哦"}] }
sleep 20
tellraw @a {"rawtext": [{"text": "§f<§6扫地姬§f> 10s后就要扫地了， 请保管好掉落物哦"}] }
sleep 10
execute as @e[type=minecraft:item] run particle minecraft:basic_flame_particle ~~~
kill @e[type=minecraft:item]
tellraw @a {"rawtext": [{"text": "§f<§6扫地姬§f> 扫地完成~"}] }
sleep 1
tellraw @a {"rawtext": [{"text": "§e扫地姬 退出了游戏"}] }