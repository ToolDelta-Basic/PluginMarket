# FIRE 配置常量 FIRE
class Config:
    GUILD_LEVELS = [100 * (2 ** i) for i in range(10)]
    GUILD_CREATION_COST = 5000          #创建公会所需的积分
    MAX_GUILD_MEMBERS = 30              #一个公会最多多少人
    GUILD_SCOREBOARD = "money"          #公会积分板块
    GUILD_FUNCTION_VAULT = True         #启用公会仓库功能
    GUILD_FUNCTION_BASE = True          #启用公会据点功能
    GUILD_FUNCTION_DONATION = True      #启用公会捐献功能
    GUILD_FUNCTION_TASKS = True         #启用公会任务功能
    GUILD_FUNCTION_EFFECT = True        #启用公会效果增益功能
    GUILD_FUNCTION_RANKINGS = True      #启用公会排行榜功能
    EXP_PER_ONLINE_MEMBER = 10
    EXP_UPDATE_INTERVAL = 600 
    DAILY_LOGIN_EXP = 5
    DONATION_EXP_RATE = 0.1 
    ITEMS_PER_PAGE = 6
    VAULT_INITIAL_SLOTS = 54
    VAULT_SLOTS_PER_LEVEL = 0  # 不再随等级增加
    DIMENSION_NAMES = {0: "主世界", 1: "地狱", 2: "末地"}
    CACHE_DURATION = 300 
    EFFECTS_CONFIG = {
        "speed": {
            "name": "速度提升",
            "levels": {1: 1, 2: 2},
            "costs": {1: 10, 2: 20}
        },
        "haste": {
            "name": "急迫",
            "levels": {1: 1, 2: 2},
            "costs": {1: 10, 2: 20}
        },
        "strength": {
            "name": "力量",
            "levels": {1: 1, 2: 2},
            "costs": {1: 10, 2: 20}
        },
        # 可以模仿以上格式修改效果
        "resistance": {
            "name": "抗性提升",
            "levels": {1: 1, 2: 2},
            "costs": {1: 10, 2: 20}
        },
        "regeneration": {
            "name": "生命恢复",
            "levels": {1: 1, 2: 2},
            "costs": {1: 10, 2: 20}
        },
        "night_vision": {
            "name": "夜视",
            "levels": {1: 1, 2: 2},
            "costs": {1: 10, 2: 20}
        },
        "jump_boost": {
            "name": "跳跃提升",
            "levels": {1: 1, 2: 2},
            "costs": {1: 10, 2: 20}
        }
    }

    # 批量操作配置
    BATCH_SAVE_INTERVAL = 5
    MAX_BATCH_SIZE = 10

    # 权限配置
    PERMISSIONS = {
        "owner": ["all"], 
        "deputy": ["kick", "invite", "vault", "announce", "task_manage"],
        "elder": ["invite", "vault", "announce", "task_manage"],  
        "member": ["vault"]  
    }

    # 默认物品价值配置
    DEFAULT_ITEM_VALUES = {
        # 基础材料
        "minecraft:diamond": 50,
        "minecraft:emerald": 25,
        "minecraft:gold_ingot": 10,
        "minecraft:iron_ingot": 5,
        "minecraft:copper_ingot": 2,
        "minecraft:coal": 1,
        "minecraft:redstone": 2,
        "minecraft:lapis_lazuli": 3,
        "minecraft:quartz": 2,

        # 稀有材料
        "minecraft:netherite_ingot": 200,
        "minecraft:ancient_debris": 150,
        "minecraft:ender_pearl": 20,
        "minecraft:blaze_rod": 15,
        "minecraft:ghast_tear": 25,
        "minecraft:shulker_shell": 100,
        "minecraft:nautilus_shell": 30,
        "minecraft:heart_of_the_sea": 150,

        # 方块材料
        "minecraft:stone": 1,
        "minecraft:cobblestone": 1,
        "minecraft:dirt": 1,
        "minecraft:sand": 1,
        "minecraft:gravel": 1,
        "minecraft:obsidian": 10,
        "minecraft:crying_obsidian": 15,
        "minecraft:netherrack": 1,
        "minecraft:end_stone": 5,

        # 木材
        "minecraft:oak_log": 2,
        "minecraft:birch_log": 2,
        "minecraft:spruce_log": 2,
        "minecraft:jungle_log": 2,
        "minecraft:acacia_log": 2,
        "minecraft:dark_oak_log": 2,
        "minecraft:oak_planks": 1,
        "minecraft:birch_planks": 1,
        "minecraft:spruce_planks": 1,
        "minecraft:jungle_planks": 1,
        "minecraft:acacia_planks": 1,
        "minecraft:dark_oak_planks": 1,

        # 食物
        "minecraft:apple": 2,
        "minecraft:golden_apple": 20,
        "minecraft:enchanted_golden_apple": 100,
        "minecraft:bread": 3,
        "minecraft:beef": 3,
        "minecraft:cooked_beef": 5,
        "minecraft:porkchop": 3,
        "minecraft:cooked_porkchop": 5,
        "minecraft:chicken": 2,
        "minecraft:cooked_chicken": 4,
        "minecraft:cod": 2,
        "minecraft:cooked_cod": 4,
        "minecraft:salmon": 3,
        "minecraft:cooked_salmon": 5,
        "minecraft:carrot": 1,
        "minecraft:golden_carrot": 8,
        "minecraft:potato": 1,
        "minecraft:baked_potato": 2,

        # 矿物块
        "minecraft:diamond_block": 450,  # 9个钻石
        "minecraft:emerald_block": 225,  # 9个绿宝石
        "minecraft:gold_block": 90,     # 9个金锭
        "minecraft:iron_block": 45,     # 9个铁锭
        "minecraft:copper_block": 18,   # 9个铜锭
        "minecraft:coal_block": 9,      # 9个煤炭
        "minecraft:redstone_block": 18, # 9个红石
        "minecraft:lapis_block": 27,    # 9个青金石
        "minecraft:quartz_block": 18,   # 4个石英
        "minecraft:netherite_block": 1800, # 9个下界合金锭

        # 其他常用物品
        "minecraft:string": 1,
        "minecraft:leather": 3,
        "minecraft:feather": 2,
        "minecraft:gunpowder": 5,
        "minecraft:bone": 2,
        "minecraft:bone_meal": 1,
        "minecraft:spider_eye": 3,
        "minecraft:slime_ball": 8,
        "minecraft:magma_cream": 10,
        "minecraft:wheat": 1,
        "minecraft:wheat_seeds": 1,
        "minecraft:sugar_cane": 2,
        "minecraft:bamboo": 1,
        "minecraft:kelp": 1,
        "minecraft:cactus": 2,
    }

    # 中文物品名称映射表
    CHINESE_ITEM_NAMES = {
        # 基础材料
        "钻石": "minecraft:diamond",
        "绿宝石": "minecraft:emerald",
        "金锭": "minecraft:gold_ingot",
        "铁锭": "minecraft:iron_ingot",
        "铜锭": "minecraft:copper_ingot",
        "煤炭": "minecraft:coal",
        "木炭": "minecraft:charcoal",
        "红石": "minecraft:redstone",
        "青金石": "minecraft:lapis_lazuli",
        "石英": "minecraft:quartz",
        "下界合金锭": "minecraft:netherite_ingot",
        "远古残骸": "minecraft:ancient_debris",
        "下界石英": "minecraft:nether_quartz",

        # 宝石和稀有材料
        "紫水晶碎片": "minecraft:amethyst_shard",
        "紫水晶": "minecraft:amethyst_shard",
        "末影珍珠": "minecraft:ender_pearl",
        "烈焰棒": "minecraft:blaze_rod",
        "恶魂之泪": "minecraft:ghast_tear",
        "潜影贝壳": "minecraft:shulker_shell",
        "鹦鹉螺壳": "minecraft:nautilus_shell",
        "海洋之心": "minecraft:heart_of_the_sea",

        # 方块材料
        "圆石": "minecraft:cobblestone",
        "石头": "minecraft:stone",
        "花岗岩": "minecraft:granite",
        "闪长岩": "minecraft:diorite",
        "安山岩": "minecraft:andesite",
        "深板岩": "minecraft:deepslate",
        "黑石": "minecraft:blackstone",
        "玄武岩": "minecraft:basalt",
        "末地石": "minecraft:end_stone",
        "下界岩": "minecraft:netherrack",
        "灵魂沙": "minecraft:soul_sand",
        "灵魂土": "minecraft:soul_soil",

        # 木材
        "橡木原木": "minecraft:oak_log",
        "白桦原木": "minecraft:birch_log",
        "云杉原木": "minecraft:spruce_log",
        "丛林原木": "minecraft:jungle_log",
        "金合欢原木": "minecraft:acacia_log",
        "深色橡木原木": "minecraft:dark_oak_log",
        "绯红菌柄": "minecraft:crimson_stem",
        "诡异菌柄": "minecraft:warped_stem",
        "橡木木板": "minecraft:oak_planks",
        "白桦木板": "minecraft:birch_planks",
        "云杉木板": "minecraft:spruce_planks",
        "丛林木板": "minecraft:jungle_planks",
        "金合欢木板": "minecraft:acacia_planks",
        "深色橡木木板": "minecraft:dark_oak_planks",

        # 食物
        "苹果": "minecraft:apple",
        "金苹果": "minecraft:golden_apple",
        "附魔金苹果": "minecraft:enchanted_golden_apple",
        "面包": "minecraft:bread",
        "牛肉": "minecraft:beef",
        "熟牛肉": "minecraft:cooked_beef",
        "猪肉": "minecraft:porkchop",
        "熟猪肉": "minecraft:cooked_porkchop",
        "鸡肉": "minecraft:chicken",
        "熟鸡肉": "minecraft:cooked_chicken",
        "羊肉": "minecraft:mutton",
        "熟羊肉": "minecraft:cooked_mutton",
        "鱼": "minecraft:cod",
        "熟鱼": "minecraft:cooked_cod",
        "鲑鱼": "minecraft:salmon",
        "熟鲑鱼": "minecraft:cooked_salmon",
        "胡萝卜": "minecraft:carrot",
        "金胡萝卜": "minecraft:golden_carrot",
        "土豆": "minecraft:potato",
        "烤土豆": "minecraft:baked_potato",
        "甜菜根": "minecraft:beetroot",
        "甜菜汤": "minecraft:beetroot_soup",
        "蘑菇煲": "minecraft:mushroom_stew",
        "兔肉煲": "minecraft:rabbit_stew",

        # 工具和武器材料
        "木棍": "minecraft:stick",
        "线": "minecraft:string",
        "皮革": "minecraft:leather",
        "羽毛": "minecraft:feather",
        "火药": "minecraft:gunpowder",
        "骨头": "minecraft:bone",
        "骨粉": "minecraft:bone_meal",
        "蜘蛛眼": "minecraft:spider_eye",
        "腐肉": "minecraft:rotten_flesh",
        "史莱姆球": "minecraft:slime_ball",
        "岩浆膏": "minecraft:magma_cream",

        # 农作物
        "小麦": "minecraft:wheat",
        "小麦种子": "minecraft:wheat_seeds",
        "南瓜": "minecraft:pumpkin",
        "南瓜种子": "minecraft:pumpkin_seeds",
        "西瓜": "minecraft:melon",
        "西瓜种子": "minecraft:melon_seeds",
        "甘蔗": "minecraft:sugar_cane",
        "竹子": "minecraft:bamboo",
        "海带": "minecraft:kelp",
        "仙人掌": "minecraft:cactus",

        # 染料
        "墨囊": "minecraft:ink_sac",
        "玫瑰红": "minecraft:red_dye",
        "橙色染料": "minecraft:orange_dye",
        "黄色染料": "minecraft:yellow_dye",
        "黄绿色染料": "minecraft:lime_dye",
        "绿色染料": "minecraft:green_dye",
        "青色染料": "minecraft:cyan_dye",
        "淡蓝色染料": "minecraft:light_blue_dye",
        "蓝色染料": "minecraft:blue_dye",
        "紫色染料": "minecraft:purple_dye",
        "品红色染料": "minecraft:magenta_dye",
        "粉红色染料": "minecraft:pink_dye",
        "白色染料": "minecraft:white_dye",
        "淡灰色染料": "minecraft:light_gray_dye",
        "灰色染料": "minecraft:gray_dye",
        "黑色染料": "minecraft:black_dye",
        "棕色染料": "minecraft:brown_dye",

        # 其他常用物品
        "泥土": "minecraft:dirt",
        "草方块": "minecraft:grass_block",
        "沙子": "minecraft:sand",
        "红沙": "minecraft:red_sand",
        "砂砾": "minecraft:gravel",
        "粘土": "minecraft:clay",
        "雪球": "minecraft:snowball",
        "冰": "minecraft:ice",
        "浮冰": "minecraft:packed_ice",
        "蓝冰": "minecraft:blue_ice",
        "黑曜石": "minecraft:obsidian",
        "哭泣的黑曜石": "minecraft:crying_obsidian",
        "基岩": "minecraft:bedrock",
        "海绵": "minecraft:sponge",
        "湿海绵": "minecraft:wet_sponge",

        # 矿物块
        "钻石块": "minecraft:diamond_block",
        "绿宝石块": "minecraft:emerald_block",
        "金块": "minecraft:gold_block",
        "铁块": "minecraft:iron_block",
        "铜块": "minecraft:copper_block",
        "煤炭块": "minecraft:coal_block",
        "红石块": "minecraft:redstone_block",
        "青金石块": "minecraft:lapis_block",
        "石英块": "minecraft:quartz_block",
        "下界合金块": "minecraft:netherite_block",
    }

    # 物品别名映射（支持多种叫法）
    ITEM_ALIASES = {
        "钻": "钻石",
        "diamond": "钻石",
        "钻石锭": "钻石",

        "绿宝": "绿宝石",
        "emerald": "绿宝石",
        "村民币": "绿宝石",
        "翡翠": "绿宝石",

        "金": "金锭",
        "gold": "金锭",
        "黄金": "金锭",
        "金子": "金锭",

        "铁": "铁锭",
        "iron": "铁锭",

        "铜": "铜锭",
        "copper": "铜锭",

        "煤": "煤炭",
        "coal": "煤炭",
        "煤块": "煤炭",

        "红石粉": "红石",
        "redstone": "红石",

        "青金": "青金石",
        "lapis": "青金石",
        "蓝宝石": "青金石",

        "石英晶体": "石英",
        "quartz": "石英",

        "下界合金": "下界合金锭",
        "netherite": "下界合金锭",
        "合金": "下界合金锭",
        "下合金": "下界合金锭",

        "残骸": "远古残骸",
        "ancient_debris": "远古残骸",
        "远古": "远古残骸",

        "橡木": "橡木原木",
        "oak": "橡木原木",
        "白桦": "白桦原木",
        "birch": "白桦原木",
        "云杉": "云杉原木",
        "spruce": "云杉原木",
        "丛林": "丛林原木",
        "jungle": "丛林原木",
        "金合欢": "金合欢原木",
        "acacia": "金合欢原木",
        "深色橡木": "深色橡木原木",
        "dark_oak": "深色橡木原木",

        "苹果": "苹果",
        "apple": "苹果",
        "金苹": "金苹果",
        "golden_apple": "金苹果",
        "附魔苹果": "附魔金苹果",
        "神苹": "附魔金苹果",
        "notch苹果": "附魔金苹果",

        "石": "石头",
        "stone": "石头",
        "泥": "泥土",
        "dirt": "泥土",
        "土": "泥土",
        "沙": "沙子",
        "sand": "沙子",

        "末影珠": "末影珍珠",
        "ender_pearl": "末影珍珠",
        "传送珠": "末影珍珠",
        "烈焰": "烈焰棒",
        "blaze_rod": "烈焰棒",
        "火棒": "烈焰棒",
        "恶魂泪": "恶魂之泪",
        "ghast_tear": "恶魂之泪",
        "鬼泪": "恶魂之泪",
    }

