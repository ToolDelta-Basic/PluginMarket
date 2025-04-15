import json
import os
from tooldelta import Plugin, fmts, utils, constants, plugin_entry


class PluginCreator(Plugin):
    name = "类式插件创建器"
    author = "ToolDelta"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.make_data_path()
        self.ListenPreload(self.on_def)

    def on_def(self):
        self.frame.add_console_cmd_trigger(
            ["create", "创建插件"], None, "创建一个类式插件", self.create_plugin
        )

    def create_plugin(self, args: list[str]):
        pname = ""
        if len(args) == 1:
            pname = args[0]
        while 1:
            if pname := (pname or input(fmts.fmt_info("请输入插件名: ")).strip()):
                plugin_dir_path = os.path.join(
                    constants.TOOLDELTA_PLUGIN_DIR,
                    constants.TOOLDELTA_CLASSIC_PLUGIN,
                    pname,
                )
                if os.path.isdir(plugin_dir_path):
                    fmts.print_war("已有重命名插件")
                    pname = ""
                    continue
                break
            else:
                fmts.print_war("插件名不能留空")
                pname = ""
        plugin_id = (
            input(fmts.fmt_info("请输入插件的唯一标识ID(回车键则使用名字作为ID): "))
            or pname
        )
        while 1:
            pdesc = input(fmts.fmt_info("请输入插件简介: "))
            if pdesc.strip():
                break
            fmts.print_war("插件描述不能留空")
        while 1:
            latest_data = utils.safe_json.read_from_plugin(self.name, "数据信息", {})
            if not latest_data:
                pauthor = input(
                    fmts.fmt_info("请输入作者名 (下一次会自动填充): ")
                ).strip()
                if pauthor == "":
                    fmts.print_war("作者名不能留空")
                    continue
                latest_data = {"author": pauthor}
                utils.safe_json.write_to_plugin(self.name, "数据信息", latest_data)
                break
            else:
                pauthor = latest_data["author"]
                break
        ver_1, ver_2, ver_3 = (0, 0, 1)
        while 1:
            try:
                ver_1, ver_2, ver_3 = (
                    int(i)
                    for i in (
                        input(fmts.fmt_info("请输入插件版本号(默认 0.0.1): "))
                        or "0.0.1"
                    ).split(".")
                )
                break
            except Exception:
                fmts.print_err("错误的版本号格式, 应为 x.x.x")
        modules = {
            "0": ("cfg", "配置文件的读取等"),
            "1": ("game_utils", "游戏内信息获取有关"),
            "2": ("utils", "实用方法合集"),
            "3": ("fmts", "格式化彩色输出"),
            "4": ("TYPE_CHECKING", "类型检查常量"),
        }
        fmts.print_inf("\n".join(f"{k}: {v[0]} ({v[1]})" for k, v in modules.items()))
        resp = input(
            fmts.fmt_info("需要用到以上哪些模块(输入连续数字, 如024, 回车键跳过): ")
        )
        extend_modules = [v[0] for k in resp if (v := modules.get(k))]
        if is_api_plugin := (
            input(
                fmts.fmt_info("需要将你的插件作为 API 插件吗(§ay§r=是, §6其他§r=否): ")
            ).strip()
            == "y"
        ):
            api_name = ""
            while 1:
                if api_name := (
                    input(
                        fmts.fmt_info("请输入插件的 API 名(回车则默认和插件名相同): ")
                    )
                    or pname
                ).strip():
                    break
        config_block = (
            "        CONFIG_STANDARD = {\n"
            '            "整数示例": int,\n'
            '            "小数示例": float,\n'
            '            "嵌套示例": {\n'
            '                "字符串示例": str,\n'
            "            }\n"
            "        }\n"
            "        CONFIG_DEFAULT = {\n"
            '            "整数示例": int,\n'
            '            "小数示例": float,\n'
            '            "嵌套示例": {\n'
            '                "字符串示例": str,\n'
            "            }\n"
            "        }\n"
        )
        plugin_body = (
            "from tooldelta import Plugin, plugin_entry, Player, Chat, FrameExit"
            + (f", {', '.join(i for i in extend_modules)}" if extend_modules else "")
            + "\n\n"
            "class NewPlugin(Plugin):\n"
            f'    name = "{pname}"\n'
            f'    author = "{pauthor}"\n'
            f"    version = ({ver_1}, {ver_2}, {ver_3})\n\n"
            "    def __init__(self, frame):\n"
            "        super().__init__(frame)\n"
            + (config_block if "Config" in extend_modules else "")
            + "\n"
            "    def on_def(self):\n"
            "        pass\n\n"
            "    def on_player_join(self, player: Player):\n"
            '        self.print(f"{player.name} 进入游戏")\n\n'
            "    def on_player_leave(self, player: Player):\n"
            '        self.print(f"{player.name} 退出游戏")\n\n'
            "    def on_player_message(self, chat: Chat):\n"
            '        self.print(f"{chat.player.name} 说: {chat.msg}")\n\n'
            "    def on_frame_exit(self, evt: FrameExit):\n"
            '        self.print(f"系统已退出 状态码={evt.signal} 原因={evt.reason}")\n\n'
            "entry = plugin_entry"
            + ("(NewPlugin)" if not is_api_plugin else f'(NewPlugin, "{api_name}")')
        )
        datafile_body = {
            "author": pauthor,
            "version": f"{ver_1}.{ver_2}.{ver_3}",
            "plugin-type": "classic",
            "description": pdesc,
            "pre-plugins": {},
            "plugin-id": plugin_id,
            "enabled": True,
        }
        os.makedirs(plugin_dir_path)
        with open(
            os.path.join(plugin_dir_path, "__init__.py"), "w", encoding="utf-8"
        ) as f:
            f.write(plugin_body)
        with open(
            os.path.join(plugin_dir_path, "datas.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(datafile_body, f, indent=2, ensure_ascii=False)
        fmts.print_suc(f"插件创建完成, 位于 {plugin_dir_path}")
        fmts.print_suc("输入 §breload §r可使其生效")


entry = plugin_entry(PluginCreator)
