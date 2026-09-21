"""配置模板与默认配置。

配置在插件构造时读一次。要改配置就改完重载框架, 运行期间不会回头看文件。
"""

from tooldelta.utils import cfg

# 坐标允许写整数或小数
NUM = (int, float)

CFG_STD = {
    "区域": {"角1": cfg.JsonList(NUM, 3), "角2": cfg.JsonList(NUM, 3)},
    "判定容差(格)": cfg.NNNumber,
    "即将上钩提示": str,
    "上钩提示": str,
    "钓获提示": str,
    "跑掉提示": str,
    "全服播报": str,
    "提示持续(秒)": cfg.PNumber,
    "收竿窗口(秒)": cfg.PNumber,
    "清除原版渔获": bool,
    "清除半径(格)": cfg.PNumber,
    "战利品": cfg.JsonList(
        {
            "名称": str,
            "数量": (cfg.PInt, cfg.JsonList(cfg.PInt, 2)),
            "权重": cfg.NNNumber,
            "稀有度": str,
            # 这三个按给法二选一, 都是可选键
            cfg.KeyGroup("物品", "战利品表", "备用物品"): str,
        }
    ),
    "稀有度表": cfg.AnyKeyValue({"颜色": str, "音效": str, "全服播报": bool}),
    "咬钩事件号": cfg.NNInt,
    "即将上钩事件号": cfg.NNInt,
    "机器人停靠": bool,
    # 留空或者写三个坐标
    "机器人停靠坐标": (cfg.JsonList(NUM, 0), cfg.JsonList(NUM, 3)),
    "停靠检查间隔(秒)": cfg.PNumber,
}

CFG_DEFAULT = {
    "区域": {"角1": [0, -4, 67], "角2": [25, 9, -39]},
    # 贴着水边下竿判不进去就调成 1, 各方向各外扩一格
    "判定容差(格)": 0.0,
    "即将上钩提示": "§f§l~ 有动静… §r§7有东西正在靠近你的浮漂",
    "上钩提示": "§b§l▲ 上钩了! §r§8| §7快收竿",
    # 可用占位符: {品质} {稀有度} {名称} {数量} {玩家}
    "钓获提示": "§7钓到了 {品质} {名称} §7x{数量}",
    "跑掉提示": "§8… 它跑了, 再试一次",
    "全服播报": "§b§l[幸运钓鱼] §r§f{玩家} §7钓到了 {品质} {名称}§7!",
    "提示持续(秒)": 2.0,
    "收竿窗口(秒)": 3.0,
    # 服务端自己生成的那条鱼; 不清的话一次收竿拿两份
    "清除原版渔获": True,
    # 半径别调大, 免得把玩家丢在水边的东西一起清了
    "清除半径(格)": 3,
    # 写 "物品" 走 /give; 写 "战利品表" 走 /loot give, 能拿到带真附魔的装备,
    "战利品": [
        {"名称": "§f鳕鱼", "物品": "cod", "数量": 1, "权重": 260, "稀有度": "普通"},
        {"名称": "§f鲑鱼", "物品": "salmon", "数量": 1, "权重": 130, "稀有度": "普通"},
        {"名称": "§f河豚", "物品": "pufferfish", "数量": 1, "权重": 40, "稀有度": "普通"},
        {"名称": "§f热带鱼", "物品": "tropical_fish", "数量": 1, "权重": 30, "稀有度": "普通"},
        {"名称": "§8破烂钓竿", "物品": "fishing_rod", "数量": 1, "权重": 40, "稀有度": "普通"},
        {"名称": "§8木棍", "物品": "stick", "数量": 2, "权重": 40, "稀有度": "普通"},
        {"名称": "§8骨头", "物品": "bone", "数量": 2, "权重": 30, "稀有度": "普通"},
        {"名称": "§a墨囊", "物品": "ink_sac", "数量": 3, "权重": 25, "稀有度": "普通"},
        {"名称": "§b海晶砂粒", "物品": "prismarine_shard", "数量": 2, "权重": 18, "稀有度": "稀有"},
        {"名称": "§b鹦鹉螺壳", "物品": "nautilus_shell", "数量": 1, "权重": 12, "稀有度": "稀有"},
        {"名称": "§b青金石", "物品": "lapis_lazuli", "数量": 4, "权重": 12, "稀有度": "稀有"},
        {"名称": "§b海绵", "物品": "sponge", "数量": 1, "权重": 8, "稀有度": "稀有"},
        {"名称": "§d钻石", "物品": "diamond", "数量": 1, "权重": 5, "稀有度": "史诗"},
        {"名称": "§d神秘宝藏", "战利品表": "loot_tables/gameplay/fishing/treasure.json",
         "备用物品": "enchanted_book", "数量": 1, "权重": 5, "稀有度": "史诗"},
        {"名称": "§d海洋之心", "物品": "heart_of_the_sea", "数量": 1, "权重": 3, "稀有度": "史诗"},
        {"名称": "§6§l附魔金苹果", "物品": "enchanted_golden_apple", "数量": 1, "权重": 2, "稀有度": "传说"},
        {"名称": "§6§l三叉戟", "物品": "trident", "数量": 1, "权重": 1, "稀有度": "传说"},
        {"名称": "§6§l下界之星", "物品": "nether_star", "数量": 1, "权重": 1, "稀有度": "传说"},
    ],
    "稀有度表": {
        "普通": {"颜色": "§f", "音效": "random.pop", "全服播报": False},
        "稀有": {"颜色": "§b", "音效": "random.orb", "全服播报": False},
        "史诗": {"颜色": "§d", "音效": "random.levelup", "全服播报": True},
        "传说": {"颜色": "§6§l", "音效": "mob.enderdragon.growl", "全服播报": True},
    },
    "咬钩事件号": 13,
    "即将上钩事件号": 12,
    # 数据包只覆盖机器人自己的加载范围, 它得一直待在钓鱼区附近
    "机器人停靠": True,
    # 留空 = 钓鱼区水平中心、高度取区域顶上 3 格
    "机器人停靠坐标": [],
    "停靠检查间隔(秒)": 15.0,
}


class Settings:
    "配置的只读视图, 外加几个派生值"

    def __init__(self, data: dict):
        self.data = data

    def __getitem__(self, key: str):
        return self.data[key]

    def region(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        "两个角点整理成 (各轴最小值, 各轴最大值), 已算进容差"
        zone = self.data["区域"]
        a = [float(v) for v in zone["角1"]]
        b = [float(v) for v in zone["角2"]]
        pad = float(self.data["判定容差(格)"])
        lo = tuple(min(a[i], b[i]) - pad for i in range(3))
        hi = tuple(max(a[i], b[i]) + pad for i in range(3))
        return lo, hi  # type: ignore[return-value]

    def in_region(self, pos: tuple[float, float, float]) -> bool:
        lo, hi = self.region()
        return all(lo[i] <= pos[i] <= hi[i] for i in range(3))

    def loot_table(self) -> list[dict]:
        return [e for e in self.data["战利品"] if float(e.get("权重", 0)) > 0]

    def style(self, rarity: str) -> dict:
        return self.data["稀有度表"].get(rarity) or {}

    def dock_point(self) -> tuple[float, float, float]:
        custom = self.data["机器人停靠坐标"]
        if len(custom) >= 3:
            return (float(custom[0]), float(custom[1]), float(custom[2]))
        # 悬在区域顶上, 不会掉水里淹死, 也不挡着玩家; 改了区域坐标它跟着走
        lo, hi = self.region()
        return ((lo[0] + hi[0]) / 2, hi[1] + 3, (lo[2] + hi[2]) / 2)
