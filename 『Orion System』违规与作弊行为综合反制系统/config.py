"""『Orion System 猎户座』插件配置加载器"""

from tooldelta import cfg, fmts, TYPE_CHECKING
from typing import ClassVar, Literal, Any
import os

from .utils import OrionUtils

# 仅类型检查用
if TYPE_CHECKING:
    from .__init__ import Orion_System


class OrionConfig:
    """插件配置加载器"""

    # 首次生成的配置
    CONFIG_DEFAULT: ClassVar[dict[str, Any]] = {
        "是否启用控制台封禁/解封系统": True,
        "是否启用游戏内封禁/解封系统": True,
        "控制台封禁系统触发词": ["ban", "封禁"],
        "游戏内封禁系统触发词": ["ban", "封禁"],
        "控制台解封系统触发词": ["unban", "解封"],
        "游戏内解封系统触发词": ["unban", "解封"],
        "--操作员可使用游戏内封禁/解封系统": True,
        "--以下用户无需操作员权限也可使用游戏内封禁/解封系统": ["...", "..."],
        "控制台封禁/解封系统每页显示几项": 20,
        "游戏内封禁/解封系统每页显示几项": 20,
        "游戏内封禁/解封系统等待输入超时时间(秒)": 60,
        "xuid封禁数据存储目录名称": "玩家封禁时间数据(以xuid记录)",
        "设备号封禁数据存储目录名称": "玩家封禁时间数据(以设备号记录)",
        "玩家<设备号/xuid/历史名称>数据存储文件名称": "玩家丨设备号丨xuid丨历史名称丨记录.json",
        "是否自动记录玩家设备号/xuid/历史名称(机器人在玩家登录时需tp至玩家处，若要根据设备号封禁玩家则必须开启该项)": True,
        "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)": 5,
        "反制白名单": ["style_天枢", "Happy2018new", "SkyblueSuper", "YeahBot", "..."],
        "各项反制是否禁用于操作员": True,
        "<<提示>> 以下为游戏内封禁记分板API：可将游戏内指令或命令方块通过记分板接入本封禁系统": None,
        "<<提示>> 您可以通过 /scoreboard players set [玩家名称] [封禁记分板名称] [封禁时间(秒)] 来封禁对应玩家": None,
        "<<提示>> 封禁记分板的分数为封禁时间(秒)；若分数为-1，则永久封禁；若分数为0，仅踢出游戏，不作封禁，玩家可以立即重进": None,
        "<<提示>> 在封禁操作执行完毕后，对应玩家的封禁记分板分数将会重置": None,
        "是否启用游戏内封禁记分板API": True,
        "--游戏内封禁记分板名称": "Ban_System",
        "--游戏内封禁记分板显示名称": "Ban_System",
        "是否隐藏违规行为踢出提示(可将玩家踢出提示转换成***)": False,
        "是否启用机器人IP外进反制": True,
        "是否启用锁服反制(皮肤数据异常检查)": True,
        "是否启用Steve/Alex皮肤反制(可用于反制异常隐身玩家)": False,
        "是否启用4D皮肤反制": False,
        "是否启用账号等级限制": True,
        "服务器准入等级": 1,
        "是否启用网易屏蔽词名称反制": True,
        "--网易屏蔽词名称检测等待时间(秒)": 2,
        "是否启用自定义违禁词名称反制": True,
        "--名称违禁词是否区分大小写英文字母": False,
        "名称违禁词列表": [
            "狂笑",
            "的蛇",
            "写散文",
            "要猫",
            "药猫",
            "妖猫",
            "幺猫",
            "要儿",
            "药儿",
            "妖儿",
            "幺儿",
            "孙政",
            "guiwow",
            "吴旭",
            "旭淳",
            "九重天",
            "五芒星",
            "南宫",
            "北境",
            "共协",
            "XTS",
            "SR",
            "TZRO",
            "STBY",
            "AFR",
            "SWI",
            "EXC",
            "DZR",
            "ATS",
            "WAD",
            "UBSR",
            "FMS",
            "NOVE",
            "生存圈",
            "天庭",
            "天神之庭",
            "Lunar",
            "Hax",
            "白墙",
            "跑路",
            "走路科技",
            "runaway",
            "导入",
            "busj",
            "万花筒",
            "购买",
            "出售",
            "赞助",
            "充值",
            "氪金",
            "炸服",
            "锁服",
            "崩服",
            "毁服",
            "权威",
            "乐子",
            "户籍",
            "社工库",
            "身份证",
            "开盒",
            "恶俗",
            "esu",
        ],
        "是否检查玩家信息与网易MC客户端是否一致(可用于反制外挂篡改游戏内等级)": False,
        "--如果在网易MC客户端无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新”)": False,
        "--如果在网易MC客户端搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏": True,
        "--网易MC客户端检查API响应等待时间(秒)": 10,
        "--网易MC客户端检查API可尝试次数(最后一次尝试依然搜索失败即放弃或踢出)": 3,
        "<<提示>> 如果您需要“禁止游戏内私聊(tell,msg,w命令)”，请将机器人踢出游戏后启用sendcommandfeedback，命令为/gamerule sendcommandfeedback true": None,
        "是否禁止游戏内私聊(tell,msg,w命令)": True,
        "--禁止私聊时是否允许私聊机器人": False,
        "是否禁止游戏内me命令": True,
        "<<提示>> 由于玩家可能通过各种方式绕开发言反制，本插件可以对文本进行以下修饰": None,
        "<<提示>> 例如：在文本修饰完毕后，玩家输入的<, R§aUn§gA.【丨w@a   §cY>将可以被精确识别为<runaway>": None,
        "--发言反制是否删除空格": True,
        "--发言反制是否区分大小写英文字母": False,
        "--发言反制是否删除§染色符号": True,
        "--除上述修饰外，以下内容也会被删除(仅限单个字符)": r"""!"#$£€%‰&'()*+,-./:;<=≠≈≌∈>?@[\]^_`{|}~，。！？；：‘’“”【】（）《》、·—～…・丨￥［］〔〕｛｝＃％＾＊＋＝＿＼｜〈〉＜＞＆•°．""",
        "是否启用发言黑名单词检测": True,
        "发言黑名单词列表": [
            "白墙",
            "跑路",
            "runaway",
            "走路科技",
            "busj",
            "万花筒",
            "苦力怕盒子",
            "炸服",
            "锁服",
            "崩服",
            "毁服",
            "权威",
            "乐子",
            "户籍",
            "社工库",
            "身份证",
            "开盒",
            "恶俗",
            "esu",
        ],
        "发言检测周期(秒)": 10,
        "是否启用周期内发言频率检测": True,
        "周期内发言条数限制": 6,
        "是否启用发言字数检测(单条文本)": True,
        "发言字数限制": 50,
        "是否启用重复消息刷屏检测": True,
        "周期内重复消息刷屏数量限制": 3,
        "<<提示>> 如果您需要在踢出玩家的同时将其封禁，请务必按照以下格式修改配置": None,
        "<<提示>> 封禁时间=-1:永久封禁": None,
        "<<提示>> 封禁时间=0:仅踢出游戏，不作封禁，玩家可以立即重进": None,
        "<<提示>> 封禁时间=86400:封禁86400秒，即1日": None,
        '<<提示>> 封禁时间="0年0月5日6时7分8秒":封禁5日6时7分8秒': None,
        '<<提示>> 封禁时间="10年0月0日0时0分0秒":封禁10年': None,
        "当发现上述违规行为时，是否根据xuid封禁玩家": True,
        "当发现上述违规行为时，是否根据设备号封禁玩家": True,
        "--如果根据设备号封禁玩家，是否同时对其施加xuid封禁(由于每次查询设备号均需要一定时间，推荐开启该项)": True,
        "封禁时间_机器人IP外进反制": -1,
        "封禁时间_锁服反制(皮肤数据异常检查)": -1,
        "封禁时间_Steve/Alex皮肤反制": 0,
        "封禁时间_4D皮肤反制": 0,
        "封禁时间_账号等级限制": 0,
        "封禁时间_网易屏蔽词名称反制": 0,
        "封禁时间_自定义违禁词名称反制": 0,
        "封禁时间_网易MC客户端无法搜索到玩家": 0,
        "封禁时间_网易MC客户端搜到的玩家等级与游戏内等级不同": -1,
        "封禁时间_游戏内私聊(tell,msg,w命令)": 60,
        "封禁时间_游戏内me命令": "0年0月0日0时1分0秒",
        "封禁时间_发言黑名单词检测": "0年0月0日0时0分60秒",
        "封禁时间_发言频率检测": "0年0月0日0时10分0秒",
        "封禁时间_发言字数检测": 60,
        "封禁时间_重复消息刷屏检测": "0年0月0日0时10分0秒",
        "<<提示>> 如果您想要自定义封禁的提示信息，请修改以下配置项": None,
        "<<提示>> 第1项为<控制台信息>，显示在面板上；第2项为<游戏内信息>，默认关闭，会通过/tellraw命令根据填入的目标选择器在游戏内进行广播；第3项为<对玩家信息>，显示给被/kick的玩家": None,
        "<<提示>> 封禁原因中的{}为参数传入部分，从0开始按顺序传入对应参数，如果你不希望显示这些信息，你可以删除它或者修改其中的数字索引": None,
        "<<提示>> 如果你想关闭这项输出，您可以在<提示信息>前面添加NN，禁止直接删除文本！！！禁止随意修改下列文本的顺序，否则可能会显示混乱！！！": None,
        "<<提示>> 关闭输出示例：<§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 可能为崩服机器人，§a正在制裁> → <NN§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 可能为崩服机器人，§a正在制裁>": None,
        "信息_机器人IP外进反制": {
            "控制台": "§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 可能为崩服机器人，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您必须通过 Microsoft 服务身份验证。",
        },
        "信息_锁服反制(皮肤数据异常检查)": {
            "控制台": "§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 可能尝试锁服(皮肤数据异常)，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您必须通过 Microsoft 服务身份验证。",
        },
        "信息_Steve/Alex皮肤反制": {
            "控制台": "§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 皮肤为Steve/Alex，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您尝试使用Steve/Alex皮肤",
        },
        "信息_4D皮肤反制": {
            "控制台": "§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 皮肤为4D皮肤，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您尝试使用4D皮肤",
        },
        "信息_账号等级限制": {
            "控制台": "§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 账号等级({2}级)低于服务器准入等级({3}级)，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您的账号等级({2}级)低于服务器准入等级({3}级)",
        },
        "信息_网易屏蔽词名称反制": {
            "控制台": "§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 名称为网易屏蔽词，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您的名称为网易屏蔽词",
        },
        "信息_自定义违禁词名称反制": {
            "控制台": "§a❀ §b[PlayerList] §c发现 {0} (xuid:{1}) 名称包括本服自定义违禁词({2})，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您的名称包括本服自定义违禁词({2})",
        },
        "信息_网易MC客户端无法搜索到玩家": {
            "控制台": "§a❀ §b[PlayerList] §c由于我们无法在网易MC客户端搜索到玩家 {0} (xuid:{1}) ，§a正在制裁该玩家，§0这可能是由于“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新”等原因导致的",
            "游戏内": ["@a", "NN"],
            "玩家": "您必须通过 Microsoft 服务身份验证。",
        },
        "信息_网易MC客户端搜到的玩家等级与游戏内等级不同": {
            "控制台": "§a❀ §b[PlayerList] §c由于玩家 {0} (xuid:{1}) 的客户端等级({2}级)和游戏内等级({3}级)不匹配，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您必须通过 Microsoft 服务身份验证。",
        },
        "信息_游戏内私聊(tell,msg,w命令)": {
            "控制台": "§a❀ §r[Text] §c发现 {0} (xuid:{1}) 尝试发送私聊(tell,msg,w命令)，§a正在制裁，§b[TextType:{2}]",
            "游戏内": ["@a", "NN"],
            "玩家": "您尝试发送私聊(tell,msg,w命令)",
        },
        "信息_游戏内me命令": {
            "控制台": "§a❀ §r[Text] §c发现 {0} (xuid:{1}) 尝试发送me命令，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您尝试发送me命令",
        },
        "信息_发言黑名单词检测": {
            "控制台": "§a❀ §r[Text] §c发现 {0} (xuid:{1}) 发送的文本触发了黑名单词({2})，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您发送的文本触发了黑名单词({2})",
        },
        "信息_发言频率检测": {
            "控制台": "§a❀ §r[Text] §c发现 {0} (xuid:{1}) 发送文本速度超过限制({2}条/{3}秒)，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您发送文本速度超过限制({2}条/{3}秒)",
        },
        "信息_发言字数检测": {
            "控制台": "§a❀ §r[Text] §c发现 {0} (xuid:{1}) 发送的文本长度超过{2}字符限制，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您发送的文本长度超过{2}字符限制",
        },
        "信息_重复消息刷屏检测": {
            "控制台": "§a❀ §r[Text] §c发现 {0} (xuid:{1}) 连续发送重复文本超出限制({2}条/{3}秒)，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您连续发送重复文本超出限制({2}条/{3}秒)",
        },
        "信息_被封禁玩家进入游戏": {
            "控制台": "§a❀ §b[PlayerList] §c发现玩家 {0} (xuid:{1}) 被封禁，§a正在制裁，封禁时间至：{2}",
            "游戏内": ["@a", "NN"],
            "玩家": "由于{3}，您被系统封禁至：{2}",
        },
        "信息_被封禁设备号进入游戏": {
            "控制台": "§a❀ §b[PlayerList] §c发现设备号 {0} 被封禁(当前登录玩家:{1})，§a正在制裁，封禁时间至：{2}",
            "游戏内": ["@a", "NN"],
            "玩家": "由于{3}，您被系统封禁至：{2}",
        },
        "信息_发现被封禁的在线玩家": {
            "控制台": "§a❀ §6[Warning] §c发现在线玩家 {0} (xuid:{1}) 目前处于封禁状态，可能是趁机器人掉线时进入游戏，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "您必须通过 Microsoft 服务身份验证。",
        },
        "信息_玩家通过记分板被封禁": {
            "控制台": "§a❀ §d[ScoreBoard] §c发现玩家 {0} (xuid:{1}) 通过游戏内封禁记分板被封禁，§a正在制裁",
            "游戏内": ["@a", "NN"],
            "玩家": "游戏内违规行为",
        },
        "<<提示>> 下列提示信息只有<控制台信息>和<游戏内信息>，由于其不涉及/kick，故没有单独的<对玩家信息>": None,
        "信息_置顶消息": {
            "控制台": """§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§l§d❐§f 『§6Orion System §d猎户座§f』 §b违规与作弊行为§e综合§a反制§d系统
§a❀ §b反制外挂の重要提示！
§a❀ §d我们认为 §b外挂可能通过遍历密码或者通过某些BUG §e破解或绕开租赁服的密码 §c我们认为租赁服密码是无效的
§a❀ §d外挂可以在进入游戏时 §e篡改数据包中的等级字段 §c我们认为租赁服等级是无效的
§a❀ §d若您的密码曾被破解 §e只要外挂跟租赁服建立过一次连接 §b租赁服当前IP地址即暴露
§a❀ §d网易的租赁服黑名单仅限于通过正常客户端加入游戏 §e在IP暴露的情况下 §b外挂可能尝试通过IP外进绕过网易黑名单 §c我们认为黑名单是无效的
§a❀ §c只要您的租赁服IP被暴露，外挂可以随意进出您的服务器，如入无人之境，您的密码、等级、黑名单均无效!
§a❀ §b此时您必须尝试重置租赁服IP以防御外挂 §e重置IP的方法为: §b保存当前存档 → 重置存档 → 还原存档
§a❀ §b我们认为仅重启租赁服也可能有效 §e此外 租赁服在正常运行过程中也有可能会定期更新IP
§a❀ §f如果您的租赁服遭到外挂袭击，您必须保护您的租赁服IP不受暴露，设置密码、等级、黑名单均有被绕过的可能，§a故最佳做法是:设置"仅限好友可见"!
§a❀ §e当前NBT虚转实复活风险: §a低风险(暂未发现或未构成流行)
§d✧✦§f§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧
§a❀ §e如果您需要“禁止游戏内私聊(tell,msg,w命令)”，§b请将机器人踢出游戏后启用sendcommandfeedback，命令为/gamerule sendcommandfeedback true""",
            "游戏内": ["@a", "NN"],
        },
        "信息_xuid封禁时长显示": {
            "控制台": "§a❀ §9[Data] §b玩家 {0} (xuid:{1}) §e本次新增封禁时长：{2}秒，§a封禁时间至：{3}",
            "游戏内": ["@a", "NN"],
        },
        "信息_设备号封禁时长显示": {
            "控制台": "§a❀ §9[Data] §b设备号 {0} (当前登录玩家:{1}) §e本次新增封禁时长：{2}秒，§a封禁时间至：{3}",
            "游戏内": ["@a", "NN"],
        },
        "信息_崩服数据包": {
            "控制台": "§a❀ §6[Warning] §e崩服机器人数据: {0}",
            "游戏内": ["@a", "NN"],
        },
        "信息_破损数据包": {
            "控制台": "§a❀ §6[Warning] §e该玩家发送了破损的数据包: {0}",
            "游戏内": ["@a", "NN"],
        },
        "信息_篡改等级包": {
            "控制台": "§a❀ §6[Warning] §e该玩家可能通过外挂篡改游戏内等级: {0}",
            "游戏内": ["@a", "NN"],
        },
        "信息_移除到期xuid数据": {
            "控制台": "§a❀ §9[Data] §b发现玩家 {0} (xuid:{1}) 的封禁已到期，已解除封禁",
            "游戏内": ["@a", "NN"],
        },
        "信息_移除破损xuid数据": {
            "控制台": "§a❀ §9[Data] §6发现 xuid封禁数据 ({0}) 出现损坏，已自动移除",
            "游戏内": ["@a", "NN"],
        },
        "信息_移除到期设备号数据": {
            "控制台": "§a❀ §9[Data] §b发现设备号 {0} 的封禁已到期，已解除封禁",
            "游戏内": ["@a", "NN"],
        },
        "信息_移除破损设备号数据": {
            "控制台": "§a❀ §9[Data] §6发现 设备号封禁数据 ({0}) 出现损坏，已自动移除",
            "游戏内": ["@a", "NN"],
        },
        "信息_设备号快速获取成功": {
            "控制台": "§a❀ §9[Data] §a玩家 {0} 的 设备号(快速获取方式): {1}",
            "游戏内": ["@a", "NN"],
        },
        "信息_设备号快速获取失败": {
            "控制台": "§a❀ §6[Warning] §6获取玩家 {0} 设备号失败(快速获取方式)，这可能是因为玩家使用4D皮肤或Steve/Alex皮肤或玩家为机器人，可能是正常现象，稍后将尝试慢速获取方式",
            "游戏内": ["@a", "NN"],
        },
        "信息_设备号慢速获取成功1": {
            "控制台": "§a❀ §9[Data] §b玩家 {0} 的 设备号(慢速获取方式): {1}",
            "游戏内": ["@a", "NN"],
        },
        "信息_设备号慢速获取成功2": {
            "控制台": "§a❀ §9[Data] §b发现玩家 {0} 通过快速获取方式得到的设备号存在异常，已校正为(慢速获取方式): {1}",
            "游戏内": ["@a", "NN"],
        },
        "信息_设备号慢速获取失败1": {
            "控制台": "§a❀ §5[Error] §c获取玩家 {0} 设备号失败(慢速获取方式)，这可能是因为玩家进服后秒退或者玩家暂未完全进入服务器，当前尝试次数{1}/{2}，这是最后一次尝试",
            "游戏内": ["@a", "NN"],
        },
        "信息_设备号慢速获取失败2": {
            "控制台": "§a❀ §5[Error] §c获取玩家 {0} 设备号失败(慢速获取方式)，这可能是因为玩家进服后秒退或者玩家暂未完全进入服务器，当前尝试次数{1}/{2}，将在1.5秒后再次尝试查询",
            "游戏内": ["@a", "NN"],
        },
        "信息_设备号慢速获取失败3": {
            "控制台": "§a❀ §6[Warning] §6发现玩家 {0} 已退出游戏，终止设备号获取线程(慢速获取方式)",
            "游戏内": ["@a", "NN"],
        },
        "信息_客户端搜索成功": {
            "控制台": "§a❀ §9[Data] §a成功在网易MC客户端搜索到玩家 {0} ，其客户端等级为{1}，游戏内等级为{2}",
            "游戏内": ["@a", "NN"],
        },
        "信息_客户端搜索失败1": {
            "控制台": "§a❀ §5[Error] §c在网易MC客户端搜索玩家 {0} 失败，原因：{1}，当前尝试次数{2}/{3}，这是最后一次尝试",
            "游戏内": ["@a", "NN"],
        },
        "信息_客户端搜索失败2": {
            "控制台": "§a❀ §5[Error] §c在网易MC客户端搜索玩家 {0} 失败，原因：{1}，当前尝试次数{2}/{3}，将在{4}秒后再次尝试搜索",
            "游戏内": ["@a", "NN"],
        },
        "***********************************************************************************************************": None,
        "<<提示>> 猎户座插件附属功能：玩家权限管理器": None,
        "<<提示>> 可用于在玩家进入游戏时自动修改其权限，或者将记分板与玩家权限进行绑定，您可以通过修改对应的记分板分数来自动修改玩家权限": None,
        "是否启用玩家权限管理器": True,
        "玩家权限管理器白名单": [
            "style_天枢",
            "Happy2018new",
            "SkyblueSuper",
            "YeahBot",
            "...",
        ],
        "玩家权限管理器是否禁用于操作员": True,
        "<<提示>> · 放置方块 : 1": None,
        "<<提示>> · 采集方块 : 2": None,
        "<<提示>> · 使用门和开关 : 3": None,
        "<<提示>> · 打开容器 : 4": None,
        "<<提示>> · 攻击玩家 : 5": None,
        "<<提示>> · 攻击生物 : 6": None,
        "<<提示>> · 操作员命令 : 7": None,
        "<<提示>> · 使用传送 : 8": None,
        "<<提示>> 请将上述权限后的数字进行组合，并按照以下格式组成<权限组>": None,
        "<<提示>> 如<正常玩家>为123456，<访客>为空字符串，<操作员>为12345678，<地铁服推荐权限组>为3456": None,
        "是否在进入游戏时自动修改玩家权限": True,
        "进入游戏权限组": "123456",
        "<<提示>> 以下为通过记分板修改玩家权限的配置，格式为<权限组: 记分板分数>": None,
        "<<提示>> 如果您不想受到本插件影响，请勿随意修改本记分板的分数！": None,
        "是否允许通过记分板修改玩家权限": True,
        "权限管理记分板名称": "Permission",
        "权限管理记分板显示名称": "Permission",
        "记分板权限组": {
            "123456": 0,
            "": 1,
            "3456": 2,
        },
        "************************************************************************************************************": None,
        "<<提示>> 为了防止意外事件发生，请谨慎修改下面这几项！": None,
        "<<提示>> <插件数据文件更新按钮>默认为True，当新版本插件首次启动时可能会按照新版本插件的要求更新数据文件的格式，并在插件数据文件更新完毕后自动调整为False": None,
        "插件数据文件更新按钮": True,
        "<<提示>> 以下为<隐藏违规行为踢出提示使用的屏蔽词>，请不要随意修改，除非该屏蔽词失效": None,
        "隐藏违规行为踢出提示使用的屏蔽词": " 加Q",
        "<<提示>> 以下为游戏内封禁记分板和玩家权限管理器记分板的检查周期，您可以自由调整，但为了防止卡顿我们不建议调太短": None,
        "记分板监听器检查周期(秒)": 5,
        "<<提示>> 简约模式: 可一键关闭全部非必要插件输出，使控制台更简洁(如设备号获取失败、客户端搜索失败、崩服数据包等)": None,
        "是否启用简约模式": False,
        "<<提示>> 除非您是插件开发者或调试人员，否则请不要修改下面这两项": None,
        "是否在测试服启用『Orion System』": False,
        "测试服列表": [48285363],
    }
    # 配置格式要求
    CONFIG_STD: ClassVar[dict[str, Any]] = {
        "是否启用控制台封禁/解封系统": bool,
        "是否启用游戏内封禁/解封系统": bool,
        "控制台封禁系统触发词": cfg.JsonList(str, -1),
        "游戏内封禁系统触发词": cfg.JsonList(str, -1),
        "控制台解封系统触发词": cfg.JsonList(str, -1),
        "游戏内解封系统触发词": cfg.JsonList(str, -1),
        "--操作员可使用游戏内封禁/解封系统": bool,
        "--以下用户无需操作员权限也可使用游戏内封禁/解封系统": cfg.JsonList(str, -1),
        "控制台封禁/解封系统每页显示几项": cfg.PInt,
        "游戏内封禁/解封系统每页显示几项": cfg.PInt,
        "游戏内封禁/解封系统等待输入超时时间(秒)": cfg.PNumber,
        "xuid封禁数据存储目录名称": str,
        "设备号封禁数据存储目录名称": str,
        "玩家<设备号/xuid/历史名称>数据存储文件名称": str,
        "是否自动记录玩家设备号/xuid/历史名称(机器人在玩家登录时需tp至玩家处，若要根据设备号封禁玩家则必须开启该项)": bool,
        "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)": cfg.PInt,
        "反制白名单": cfg.JsonList(str, -1),
        "各项反制是否禁用于操作员": bool,
        "是否启用游戏内封禁记分板API": bool,
        "--游戏内封禁记分板名称": str,
        "--游戏内封禁记分板显示名称": str,
        "是否隐藏违规行为踢出提示(可将玩家踢出提示转换成***)": bool,
        "是否启用机器人IP外进反制": bool,
        "是否启用锁服反制(皮肤数据异常检查)": bool,
        "是否启用Steve/Alex皮肤反制(可用于反制异常隐身玩家)": bool,
        "是否启用4D皮肤反制": bool,
        "是否启用账号等级限制": bool,
        "服务器准入等级": cfg.PInt,
        "是否启用网易屏蔽词名称反制": bool,
        "--网易屏蔽词名称检测等待时间(秒)": cfg.PNumber,
        "是否启用自定义违禁词名称反制": bool,
        "--名称违禁词是否区分大小写英文字母": bool,
        "名称违禁词列表": cfg.JsonList(str, -1),
        "是否检查玩家信息与网易MC客户端是否一致(可用于反制外挂篡改游戏内等级)": bool,
        "--如果在网易MC客户端无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新”)": bool,
        "--如果在网易MC客户端搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏": bool,
        "--网易MC客户端检查API响应等待时间(秒)": cfg.PNumber,
        "--网易MC客户端检查API可尝试次数(最后一次尝试依然搜索失败即放弃或踢出)": cfg.PInt,
        "是否禁止游戏内私聊(tell,msg,w命令)": bool,
        "--禁止私聊时是否允许私聊机器人": bool,
        "是否禁止游戏内me命令": bool,
        "--发言反制是否删除空格": bool,
        "--发言反制是否区分大小写英文字母": bool,
        "--发言反制是否删除§染色符号": bool,
        "--除上述修饰外，以下内容也会被删除(仅限单个字符)": str,
        "是否启用发言黑名单词检测": bool,
        "发言黑名单词列表": cfg.JsonList(str, -1),
        "发言检测周期(秒)": cfg.PNumber,
        "是否启用周期内发言频率检测": bool,
        "周期内发言条数限制": cfg.PInt,
        "是否启用发言字数检测(单条文本)": bool,
        "发言字数限制": cfg.PInt,
        "是否启用重复消息刷屏检测": bool,
        "周期内重复消息刷屏数量限制": cfg.PInt,
        "当发现上述违规行为时，是否根据xuid封禁玩家": bool,
        "当发现上述违规行为时，是否根据设备号封禁玩家": bool,
        "--如果根据设备号封禁玩家，是否同时对其施加xuid封禁(由于每次查询设备号均需要一定时间，推荐开启该项)": bool,
        "封禁时间_机器人IP外进反制": (int, str),
        "封禁时间_锁服反制(皮肤数据异常检查)": (int, str),
        "封禁时间_Steve/Alex皮肤反制": (int, str),
        "封禁时间_4D皮肤反制": (int, str),
        "封禁时间_账号等级限制": (int, str),
        "封禁时间_网易屏蔽词名称反制": (int, str),
        "封禁时间_自定义违禁词名称反制": (int, str),
        "封禁时间_网易MC客户端无法搜索到玩家": (int, str),
        "封禁时间_网易MC客户端搜到的玩家等级与游戏内等级不同": (int, str),
        "封禁时间_游戏内私聊(tell,msg,w命令)": (int, str),
        "封禁时间_游戏内me命令": (int, str),
        "封禁时间_发言黑名单词检测": (int, str),
        "封禁时间_发言频率检测": (int, str),
        "封禁时间_发言字数检测": (int, str),
        "封禁时间_重复消息刷屏检测": (int, str),
        "信息_机器人IP外进反制": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_锁服反制(皮肤数据异常检查)": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_Steve/Alex皮肤反制": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_4D皮肤反制": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_账号等级限制": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_网易屏蔽词名称反制": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_自定义违禁词名称反制": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_网易MC客户端无法搜索到玩家": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_网易MC客户端搜到的玩家等级与游戏内等级不同": cfg.AnyKeyValue(
            (str, cfg.JsonList(str, 2))
        ),
        "信息_游戏内私聊(tell,msg,w命令)": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_游戏内me命令": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_发言黑名单词检测": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_发言频率检测": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_发言字数检测": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_重复消息刷屏检测": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_被封禁玩家进入游戏": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_被封禁设备号进入游戏": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_发现被封禁的在线玩家": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_玩家通过记分板被封禁": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_置顶消息": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_xuid封禁时长显示": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_设备号封禁时长显示": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_崩服数据包": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_破损数据包": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_篡改等级包": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_移除到期xuid数据": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_移除破损xuid数据": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_移除到期设备号数据": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_移除破损设备号数据": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_设备号快速获取成功": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_设备号快速获取失败": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_设备号慢速获取成功1": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_设备号慢速获取成功2": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_设备号慢速获取失败1": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_设备号慢速获取失败2": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_设备号慢速获取失败3": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_客户端搜索成功": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_客户端搜索失败1": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "信息_客户端搜索失败2": cfg.AnyKeyValue((str, cfg.JsonList(str, 2))),
        "是否启用玩家权限管理器": bool,
        "玩家权限管理器白名单": cfg.JsonList(str, -1),
        "玩家权限管理器是否禁用于操作员": bool,
        "是否在进入游戏时自动修改玩家权限": bool,
        "进入游戏权限组": (str, int),
        "是否允许通过记分板修改玩家权限": bool,
        "权限管理记分板名称": str,
        "权限管理记分板显示名称": str,
        "记分板权限组": cfg.AnyKeyValue((str, int)),
        "插件数据文件更新按钮": bool,
        "隐藏违规行为踢出提示使用的屏蔽词": str,
        "记分板监听器检查周期(秒)": cfg.PNumber,
        "是否启用简约模式": bool,
        "是否在测试服启用『Orion System』": bool,
        "测试服列表": cfg.JsonList(int, -1),
    }

    def __init__(self, plugin: "Orion_System") -> None:
        """
        初始化插件配置加载器
        Args:
            plugin: 插件实例
        """
        self.plugin = plugin
        self.data_path = plugin.data_path
        self.name = plugin.name
        self.version = plugin.version

    def load_config(self) -> None:
        """加载插件配置文件"""
        try:
            self.config, _ = cfg.get_plugin_config_and_version(
                self.name,
                self.CONFIG_STD,
                self.CONFIG_DEFAULT,
                self.version,
            )
            self.get_parsed_config()
            self.transfer_config()
            self.check_permission_mgr()
            self.concise_mode()
        except cfg.ConfigKeyError as error:
            fmts.print_inf(
                f"§e<『Orion System』违规与作弊行为综合反制系统> §6警告：发现插件配置文件中有{error}，这可能是因为插件本体已更新而插件配置文件未更新，已自动替换为新版配置文件"
            )
            os.remove(f"插件配置文件/{self.name}.json")
            self.load_config()
        except cfg.ConfigValueError as error:
            fmts.print_inf(
                f"§e<『Orion System』违规与作弊行为综合反制系统> §c警告：发现插件配置文件中有{error}，请检查您是否删除或新增了某些配置项的内容导致类型检查不通过，已自动替换为初始配置文件"
            )
            os.remove(f"插件配置文件/{self.name}.json")
            self.load_config()

    def transfer_config(self) -> None:
        """```
        转换一些配置内容，比如：
        1.移除部分配置项(如名称违禁词列表、发言黑名单词列表)中的空字符串
        2.在符合配置要求下，将部分配置项(如名称违禁词列表、发言黑名单词列表)中的英文字母转换为大写
        3.将配置中的封禁时间格式化为0、正整数或Forever
        ```"""
        self.banned_word_list = [x for x in self.banned_word_list if x != ""]
        self.blacklist_word_list = [x for x in self.blacklist_word_list if x != ""]
        if self.is_distinguish_upper_or_lower_in_self_banned_word is False:
            self.banned_word_list = [word.upper() for word in self.banned_word_list]
        if self.is_distinguish_upper_or_lower_on_chat is False:
            self.blacklist_word_list = [
                word.upper() for word in self.blacklist_word_list
            ]
        for attr in list(self.__dict__.keys()):
            if attr.startswith("ban_time_"):
                original_attr = getattr(self, attr, 0)
                formatted = OrionUtils.ban_time_format(original_attr)
                setattr(self, attr, formatted)

    def check_permission_mgr(self) -> None:
        """检查玩家权限管理器配置是否正确"""
        if self.check_permission_mgr_execute(self.enter_permission_group) is False:
            self.config["进入游戏权限组"] = self.CONFIG_DEFAULT["进入游戏权限组"]
        for k, v in self.scoreboard_permission_group.items():
            if self.check_permission_mgr_execute(k) is False:
                self.config["记分板权限组"] = self.CONFIG_DEFAULT["记分板权限组"]
                break
            try:
                int(v)
            except ValueError:
                fmts.print_inf(
                    f"§6警告：玩家权限组格式有误 (记分板分数必须为数字！不能为{v})"
                )
                self.config["记分板权限组"] = self.CONFIG_DEFAULT["记分板权限组"]
                break
        cfg.upgrade_plugin_config(self.name, self.config, self.version)

    @staticmethod
    def check_permission_mgr_execute(string: str | int) -> bool:
        """
        玩家权限管理器检查逻辑
        Args:
            string (str | int): 玩家权限组
        Returns:
            check_result (bool): 检查是否通过，若不通过则自动替换成初始配置
        """
        if string == "":
            return True
        string = str(string)
        allowed_string = set("12345678")
        for c in string:
            if c not in allowed_string:
                fmts.print_inf(
                    f"§6警告：玩家权限组格式有误 (您只能输入1-8之间的数字: {string})"
                )
                return False
        if len(set(string)) != len(string):
            fmts.print_inf(f"§6警告：玩家权限组格式有误 (出现了重复项: {string})")
            return False
        return True

    def concise_mode(self) -> None:
        """简约模式下关闭某些配置项输出"""
        if self.is_concise_mode:
            config = self.config
            concise_list = [
                config["信息_置顶消息"],
                config["信息_崩服数据包"],
                config["信息_破损数据包"],
                config["信息_篡改等级包"],
                config["信息_设备号快速获取失败"],
                config["信息_设备号慢速获取失败1"],
                config["信息_设备号慢速获取失败2"],
                config["信息_设备号慢速获取失败3"],
                config["信息_客户端搜索失败1"],
                config["信息_客户端搜索失败2"],
            ]
            for info in concise_list:
                for k, v in info.items():
                    if isinstance(v, str) and v.startswith("NN") is False:
                        info[k] = "NN" + v
                    elif isinstance(v, list):
                        if isinstance(v[1], str) and v[1].startswith("NN") is False:
                            info[k][1] = "NN" + v[1]
            cfg.upgrade_plugin_config(self.name, config, self.version)

    def get_parsed_config(self) -> None:
        """将配置属性绑定至实例"""
        config = self.config
        self.is_terminal_ban_system: bool = config["是否启用控制台封禁/解封系统"]
        self.is_game_ban_system: bool = config["是否启用游戏内封禁/解封系统"]
        self.terminal_ban_trigger_words: list[str] = config["控制台封禁系统触发词"]
        self.game_ban_trigger_words: list[str] = config["游戏内封禁系统触发词"]
        self.terminal_unban_trigger_words: list[str] = config["控制台解封系统触发词"]
        self.game_unban_trigger_words: list[str] = config["游戏内解封系统触发词"]
        self.is_op_allow_ban_in_game: bool = config["--操作员可使用游戏内封禁/解封系统"]
        self.user_allow_ban_in_game: list[str] = config[
            "--以下用户无需操作员权限也可使用游戏内封禁/解封系统"
        ]
        self.terminal_items_per_page: int = config["控制台封禁/解封系统每页显示几项"]
        self.game_items_per_page: int = config["游戏内封禁/解封系统每页显示几项"]
        self.ban_player_by_game_timeout: int | float = config[
            "游戏内封禁/解封系统等待输入超时时间(秒)"
        ]
        self.xuid_dir: str = config["xuid封禁数据存储目录名称"]
        self.device_id_dir: str = config["设备号封禁数据存储目录名称"]
        self.player_data_file: str = config[
            "玩家<设备号/xuid/历史名称>数据存储文件名称"
        ]
        self.is_get_device_id: bool = config[
            "是否自动记录玩家设备号/xuid/历史名称(机器人在玩家登录时需tp至玩家处，若要根据设备号封禁玩家则必须开启该项)"
        ]
        self.record_device_id_try_time: int = config[
            "--查询玩家设备号可尝试次数(最后一次尝试依然查询失败即放弃)"
        ]
        self.whitelist: list[str] = config["反制白名单"]
        self.ban_ignore_op: bool = config["各项反制是否禁用于操作员"]
        self.is_ban_api_in_game: bool = config["是否启用游戏内封禁记分板API"]
        self.ban_scoreboard_name: str = config["--游戏内封禁记分板名称"]
        self.ban_scoreboard_dummy_name: str = config["--游戏内封禁记分板显示名称"]
        self.is_hide_ban_info: bool = config[
            "是否隐藏违规行为踢出提示(可将玩家踢出提示转换成***)"
        ]
        self.is_detect_bot: bool = config["是否启用机器人IP外进反制"]
        self.is_detect_abnormal_skin: bool = config[
            "是否启用锁服反制(皮肤数据异常检查)"
        ]
        self.is_ban_Steve_or_Alex: bool = config[
            "是否启用Steve/Alex皮肤反制(可用于反制异常隐身玩家)"
        ]
        self.is_ban_4D_skin: bool = config["是否启用4D皮肤反制"]
        self.is_level_limit: bool = config["是否启用账号等级限制"]
        self.server_level: int = config["服务器准入等级"]
        self.is_detect_netease_banned_word: bool = config["是否启用网易屏蔽词名称反制"]
        self.detect_netease_banned_word_timeout: int | float = config[
            "--网易屏蔽词名称检测等待时间(秒)"
        ]
        self.is_detect_self_banned_word: bool = config["是否启用自定义违禁词名称反制"]
        self.is_distinguish_upper_or_lower_in_self_banned_word: bool = config[
            "--名称违禁词是否区分大小写英文字母"
        ]
        self.banned_word_list: list[str] = config["名称违禁词列表"]
        self.is_check_player_info: bool = config[
            "是否检查玩家信息与网易MC客户端是否一致(可用于反制外挂篡改游戏内等级)"
        ]
        self.is_ban_player_if_cannot_search: bool = config[
            "--如果在网易MC客户端无法搜索到该玩家，是否踢出游戏(可能的原因：“本API调用过快”、“玩家为机器人”、“玩家名称为网易屏蔽词”、“玩家在10分钟内改过名字，但数据库暂未更新”)"
        ]
        self.is_ban_player_if_different_level: bool = config[
            "--如果在网易MC客户端搜到的玩家等级与游戏内等级不同(说明遭到外挂篡改)，是否踢出游戏"
        ]
        self.check_player_info_api_timeout: int | float = config[
            "--网易MC客户端检查API响应等待时间(秒)"
        ]
        self.check_player_info_api_try_time: int = config[
            "--网易MC客户端检查API可尝试次数(最后一次尝试依然搜索失败即放弃或踢出)"
        ]
        self.ban_private_chat: bool = config["是否禁止游戏内私聊(tell,msg,w命令)"]
        self.allow_chat_with_bot: bool = config["--禁止私聊时是否允许私聊机器人"]
        self.ban_me_command: bool = config["是否禁止游戏内me命令"]
        self.is_remove_space: bool = config["--发言反制是否删除空格"]
        self.is_distinguish_upper_or_lower_on_chat: bool = config[
            "--发言反制是否区分大小写英文字母"
        ]
        self.is_remove_double_s: bool = config["--发言反制是否删除§染色符号"]
        self.other_remove: str = config[
            "--除上述修饰外，以下内容也会被删除(仅限单个字符)"
        ]
        self.testfor_blacklist_word: bool = config["是否启用发言黑名单词检测"]
        self.blacklist_word_list: list[str] = config["发言黑名单词列表"]
        self.speak_detection_cycle: int | float = config["发言检测周期(秒)"]
        self.speak_speed_limit: bool = config["是否启用周期内发言频率检测"]
        self.max_speak_count: int = config["周期内发言条数限制"]
        self.message_length_limit: bool = config["是否启用发言字数检测(单条文本)"]
        self.max_speak_length: int = config["发言字数限制"]
        self.repeat_message_limit: bool = config["是否启用重复消息刷屏检测"]
        self.max_repeat_count: int = config["周期内重复消息刷屏数量限制"]
        self.is_ban_player_by_xuid: bool = config[
            "当发现上述违规行为时，是否根据xuid封禁玩家"
        ]
        self.is_ban_player_by_device_id: bool = config[
            "当发现上述违规行为时，是否根据设备号封禁玩家"
        ]
        self.jointly_ban_player: bool = config[
            "--如果根据设备号封禁玩家，是否同时对其施加xuid封禁(由于每次查询设备号均需要一定时间，推荐开启该项)"
        ]
        self.ban_time_detect_bot: int | Literal["Forever"] = config[
            "封禁时间_机器人IP外进反制"
        ]
        self.ban_time_detect_abnormal_skin: int | Literal["Forever"] = config[
            "封禁时间_锁服反制(皮肤数据异常检查)"
        ]
        self.ban_time_Steve_or_Alex: int | Literal["Forever"] = config[
            "封禁时间_Steve/Alex皮肤反制"
        ]
        self.ban_time_4D_skin: int | Literal["Forever"] = config["封禁时间_4D皮肤反制"]
        self.ban_time_level_limit: int | Literal["Forever"] = config[
            "封禁时间_账号等级限制"
        ]
        self.ban_time_detect_netease_banned_word: int | Literal["Forever"] = config[
            "封禁时间_网易屏蔽词名称反制"
        ]
        self.ban_time_detect_self_banned_word: int | Literal["Forever"] = config[
            "封禁时间_自定义违禁词名称反制"
        ]
        self.ban_time_if_cannot_search: int | Literal["Forever"] = config[
            "封禁时间_网易MC客户端无法搜索到玩家"
        ]
        self.ban_time_if_different_level: int | Literal["Forever"] = config[
            "封禁时间_网易MC客户端搜到的玩家等级与游戏内等级不同"
        ]
        self.ban_time_private_chat: int | Literal["Forever"] = config[
            "封禁时间_游戏内私聊(tell,msg,w命令)"
        ]
        self.ban_time_me_command: int | Literal["Forever"] = config[
            "封禁时间_游戏内me命令"
        ]
        self.ban_time_testfor_blacklist_word: int | Literal["Forever"] = config[
            "封禁时间_发言黑名单词检测"
        ]
        self.ban_time_speak_speed_limit: int | Literal["Forever"] = config[
            "封禁时间_发言频率检测"
        ]
        self.ban_time_message_length_limit: int | Literal["Forever"] = config[
            "封禁时间_发言字数检测"
        ]
        self.ban_time_repeat_message_limit: int | Literal["Forever"] = config[
            "封禁时间_重复消息刷屏检测"
        ]
        self.info_detect_bot: dict[str, str | list[str]] = config[
            "信息_机器人IP外进反制"
        ]
        self.info_detect_abnormal_skin: dict[str, str | list[str]] = config[
            "信息_锁服反制(皮肤数据异常检查)"
        ]
        self.info_Steve_or_Alex: dict[str, str | list[str]] = config[
            "信息_Steve/Alex皮肤反制"
        ]
        self.info_4D_skin: dict[str, str | list[str]] = config["信息_4D皮肤反制"]
        self.info_level_limit: dict[str, str | list[str]] = config["信息_账号等级限制"]
        self.info_detect_netease_banned_word: dict[str, str | list[str]] = config[
            "信息_网易屏蔽词名称反制"
        ]
        self.info_detect_self_banned_word: dict[str, str | list[str]] = config[
            "信息_自定义违禁词名称反制"
        ]
        self.info_if_cannot_search: dict[str, str | list[str]] = config[
            "信息_网易MC客户端无法搜索到玩家"
        ]
        self.info_if_different_level: dict[str, str | list[str]] = config[
            "信息_网易MC客户端搜到的玩家等级与游戏内等级不同"
        ]
        self.info_private_chat: dict[str, str | list[str]] = config[
            "信息_游戏内私聊(tell,msg,w命令)"
        ]
        self.info_me_command: dict[str, str | list[str]] = config["信息_游戏内me命令"]
        self.info_testfor_blacklist_word: dict[str, str | list[str]] = config[
            "信息_发言黑名单词检测"
        ]
        self.info_speak_speed_limit: dict[str, str | list[str]] = config[
            "信息_发言频率检测"
        ]
        self.info_message_length_limit: dict[str, str | list[str]] = config[
            "信息_发言字数检测"
        ]
        self.info_repeat_message_limit: dict[str, str | list[str]] = config[
            "信息_重复消息刷屏检测"
        ]
        self.info_banned_player: dict[str, str | list[str]] = config[
            "信息_被封禁玩家进入游戏"
        ]
        self.info_banned_device_id: dict[str, str | list[str]] = config[
            "信息_被封禁设备号进入游戏"
        ]
        self.info_find_online_banned: dict[str, str | list[str]] = config[
            "信息_发现被封禁的在线玩家"
        ]
        self.info_ban_by_scoreboard: dict[str, str | list[str]] = config[
            "信息_玩家通过记分板被封禁"
        ]
        self.info_top_message: dict[str, str | list[str]] = config["信息_置顶消息"]
        self.info_xuid_ban_display: dict[str, str | list[str]] = config[
            "信息_xuid封禁时长显示"
        ]
        self.info_device_id_ban_display: dict[str, str | list[str]] = config[
            "信息_设备号封禁时长显示"
        ]
        self.info_collapse_packet: dict[str, str | list[str]] = config[
            "信息_崩服数据包"
        ]
        self.info_broken_packet: dict[str, str | list[str]] = config["信息_破损数据包"]
        self.info_tamper_level_packet: dict[str, str | list[str]] = config[
            "信息_篡改等级包"
        ]
        self.info_delete_expire_xuid: dict[str, str | list[str]] = config[
            "信息_移除到期xuid数据"
        ]
        self.info_delete_broken_xuid: dict[str, str | list[str]] = config[
            "信息_移除破损xuid数据"
        ]
        self.info_delete_expire_device_id: dict[str, str | list[str]] = config[
            "信息_移除到期设备号数据"
        ]
        self.info_delete_broken_device_id: dict[str, str | list[str]] = config[
            "信息_移除破损设备号数据"
        ]
        self.info_quick_get_device_success: dict[str, str | list[str]] = config[
            "信息_设备号快速获取成功"
        ]
        self.info_quick_get_device_fail: dict[str, str | list[str]] = config[
            "信息_设备号快速获取失败"
        ]
        self.info_slow_get_device_success_1: dict[str, str | list[str]] = config[
            "信息_设备号慢速获取成功1"
        ]
        self.info_slow_get_device_success_2: dict[str, str | list[str]] = config[
            "信息_设备号慢速获取成功2"
        ]
        self.info_slow_get_device_fail_1: dict[str, str | list[str]] = config[
            "信息_设备号慢速获取失败1"
        ]
        self.info_slow_get_device_fail_2: dict[str, str | list[str]] = config[
            "信息_设备号慢速获取失败2"
        ]
        self.info_slow_get_device_fail_3: dict[str, str | list[str]] = config[
            "信息_设备号慢速获取失败3"
        ]
        self.info_search_success: dict[str, str | list[str]] = config[
            "信息_客户端搜索成功"
        ]
        self.info_search_fail_1: dict[str, str | list[str]] = config[
            "信息_客户端搜索失败1"
        ]
        self.info_search_fail_2: dict[str, str | list[str]] = config[
            "信息_客户端搜索失败2"
        ]
        self.is_permission_mgr: bool = config["是否启用玩家权限管理器"]
        self.permission_whitelist: list[str] = config["玩家权限管理器白名单"]
        self.permission_ignore_op: bool = config["玩家权限管理器是否禁用于操作员"]
        self.is_change_permission_when_enter: bool = config[
            "是否在进入游戏时自动修改玩家权限"
        ]
        self.enter_permission_group: str | int = config["进入游戏权限组"]
        self.is_change_permission_by_scoreboard: bool = config[
            "是否允许通过记分板修改玩家权限"
        ]
        self.permission_scoreboard_name: str = config["权限管理记分板名称"]
        self.permission_scoreboard_dummy_name: str = config["权限管理记分板显示名称"]
        self.scoreboard_permission_group: dict[str | int, str | int] = config[
            "记分板权限组"
        ]
        self.upgrade_plugin_data_button: bool = config["插件数据文件更新按钮"]
        self.hide_netease_banned_word: str = config["隐藏违规行为踢出提示使用的屏蔽词"]
        self.scoreboard_detect_cycle: int | float = config["记分板监听器检查周期(秒)"]
        self.is_concise_mode: bool = config["是否启用简约模式"]
        self.load_in_trial_server: bool = config["是否在测试服启用『Orion System』"]
        self.trial_server_list: list[int] = config["测试服列表"]

    def upgrade_plugin_data(self) -> None:
        """```
        根据一定要求更新插件数据文件
        ╔══════════════════════════════════════════════════════════════════════════╗
        ║ ██╗   ██╗   ██████╗              ██████╗    █████╗   ████████╗   █████╗  ║
        ║ ███╗  ██║  ██╔═══██╗             ██╔══██╗  ██╔══██╗  ╚══██╔══╝  ██╔══██╗ ║
        ║ ████╗ ██║  ██║   ██║             ██║  ██║  ██║  ██║     ██║     ██║  ██║ ║
        ║ ██╔██╗██║  ██║   ██║             ██║  ██║  ███████║     ██║     ███████║ ║
        ║ ██║ ████║  ██║   ██║             ██║  ██║  ██╔══██║     ██║     ██╔══██║ ║
        ║ ██║  ███║  ╚██████╔╝             ██████╔╝  ██║  ██║     ██║     ██║  ██║ ║
        ║ ╚═╝  ╚══╝   ╚═════╝              ╚═════╝   ╚═╝  ╚═╝     ╚═╝     ╚═╝  ╚═╝ ║
        ╚══════════════════════════════════════════════════════════════════════════╝
        ```"""
        if self.upgrade_plugin_data_button:
            self.config["插件数据文件更新按钮"] = False
            cfg.upgrade_plugin_config(self.name, self.config, self.version)
