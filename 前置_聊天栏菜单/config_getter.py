DEFAULT_CFG = {
            "help菜单样式": {
                "菜单头": "§r========== §bＴｏｏｌＤｅｌｔａ§r ==========\n§r§d§l❒ §r§d权限: [是否为管理员] [是否为创造] [是否为成员]",
                "菜单列表": " §f< [菜单指令]§f > [参数提示] §7>>> §f§o[菜单功能说明]§r§7",
                "菜单尾": "§r§f============§7[§a[当前页数] §7/ §a[总页数]§7]§f=============\n§r>>> §7输入 .help <页数> 可以跳转到该页",
                "管理选项": {
                    "格式化": "[是否为管理员]",
                    "为管理员": "§r[§a管理选项§l✔§r]",
                    "不为管理员": "§r[§c管理选项§l✘§r]",
                },
                "创造选项": {
                    "格式化": "[是否为创造]",
                    "为创造": "§r[§a创造选项§l✔§r]",
                    "不为创造": "§r[§c创造选项§l✘§r]",
                },
                "成员选项": {
                    "格式化": "[是否为成员]",
                    "为成员": "§r[§a成员选项§l✔§r]",
                    "不为成员": "§r[§c成员选项§l✘§r]",
                },
                "菜单指令配置": {
                    "指令分隔符": " §r§7| ",
                    "指令配色": {
                        "管理": "§a",
                        "成员": "§a",
                    },
                },
                "参数提示配置": {
                    "参数间隔符": " ",
                    "参数提示格式": "[§6[提示词]§r]",
                },
            },
            "指令序号式菜单样式": {
                "菜单头": "§r========== §bＴｏｏｌＤｅｌｔａ§r ==========\n§r§d§l❒ §r§d权限: [是否为管理员] [是否为创造] [是否为成员]",
                "菜单列表": " §b[序号] - §a[菜单指令]§f [参数提示] §7>>> §f§o[菜单功能说明]§r§7",
                "菜单尾": "§7[§a[当前页数] §7/ §a[总页数]§7] §r§7输入 §6-§7/§a+ §f翻到上/下一页 §cq§7退出",
                "菜单退出提示": "❒ §6菜单已退出",
                "管理选项": {
                    "格式化": "[是否为管理员]",
                    "为管理员": "§r[§a管理选项§l✔§r]",
                    "不为管理员": "§r[§c管理选项§l✘§r]",
                },
                "创造选项": {
                    "格式化": "[是否为创造]",
                    "为创造": "§r[§a创造选项§l✔§r]",
                    "不为创造": "§r[§c创造选项§l✘§r]",
                },
                "成员选项": {
                    "格式化": "[是否为成员]",
                    "为成员": "§r[§a成员选项§l✔§r]",
                    "不为成员": "§r[§c成员选项§l✘§r]",
                },
                "菜单指令配置": {
                    "指令分隔符": " §r§7| ",
                    "指令配色": {
                        "管理": "§a",
                        "成员": "§a",
                    },
                },
                "参数提示配置": {
                    "参数间隔符": " ",
                    "参数提示格式": "[§6[提示词]§r]",
                },
            },
            "/help触发词": ["help"],
            "是否启用指令序号式菜单样式": True,
            "被识别为触发词的前缀(不填则为无命令前缀)": [".", "。", "·"],
            "单页内最多显示数": 6,
        }

class DefaultMenuStyle:
    def __init__(self, cfg: dict) -> None:
        formats = cfg["help菜单样式"]
        self.header = formats["菜单头"]
        self.footer = formats["菜单尾"]
        self.content = formats["菜单列表"]
        op_formats = formats["管理选项"]
        self.op_format = op_formats["格式化"]
        self.is_op_format = op_formats["为管理员"]
        self.isnot_op_format = op_formats["不为管理员"]
        creative_formats = formats["创造选项"]
        self.create_format = creative_formats["格式化"]
        self.is_create_format = creative_formats["为创造"]
        self.isnot_create_format = creative_formats["不为创造"]
        self.member_format = formats["成员选项"]["格式化"]
        member_formats = formats["成员选项"]
        self.is_member_format = member_formats["为成员"]
        self.isnot_member_format = member_formats["不为成员"]
        cmd_formats = formats["菜单指令配置"]
        self.cmd_sep = cmd_formats["指令分隔符"]
        self.cmd_color_op = cmd_formats["指令配色"]["管理"]
        self.cmd_color_member = cmd_formats["指令配色"]["成员"]
        arghint_formats = formats["参数提示配置"]
        self.arghint_sep = arghint_formats["参数间隔符"]
        self.arghint_text = arghint_formats["参数提示格式"]


class NBCMenuStyle:
    def __init__(self, cfg: dict):
        formats = cfg["指令序号式菜单样式"]
        self.header = formats["菜单头"]
        self.footer = formats["菜单尾"]
        self.content = formats["菜单列表"]
        self.exit_format = formats["菜单退出提示"]
        op_formats = formats["管理选项"]
        self.op_format = op_formats["格式化"]
        self.is_op_format = op_formats["为管理员"]
        self.isnot_op_format = op_formats["不为管理员"]
        create_formats = formats["创造选项"]
        self.create_format = create_formats["格式化"]
        self.is_create_format = create_formats["为创造"]
        self.isnot_create_format = create_formats["不为创造"]
        member_formats = formats["成员选项"]
        self.member_format = member_formats["格式化"]
        self.is_member_format = member_formats["为成员"]
        self.isnot_member_format = member_formats["不为成员"]
        cmd_formats = formats["菜单指令配置"]
        self.cmd_sep = cmd_formats["指令分隔符"]
        self.cmd_color_op = cmd_formats["指令配色"]["管理"]
        self.cmd_color_member = cmd_formats["指令配色"]["成员"]
        arghint_formats = formats["参数提示配置"]
        self.arghint_sep = arghint_formats["参数间隔符"]
        self.arghint_text = arghint_formats["参数提示格式"]
