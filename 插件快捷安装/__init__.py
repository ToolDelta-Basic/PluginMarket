"""
插件快捷安装 - ToolDelta Demo 插件
实现快捷安装命令: plg add + <插件ID/名称>
支持参数:
  -url <url>  指定自定义插件市场源
  -y          跳过二次确认
"""

from tooldelta import Plugin, plugin_entry
from tooldelta.plugin_market import market
from tooldelta.utils import fmts
from .installer import PluginInstaller


class QuickPluginInstaller(Plugin):
    """
    插件快捷安装工具

    提供命令行快捷安装插件的功能，支持通过插件 ID 或名称搜索并安装
    插件和插件整合包。支持自定义插件市场源和快速安装模式。

    命令格式: plg add <插件名> [-url <URL>] [-y]
    """

    name = "插件快捷安装"
    author = "Q3CC"
    version = (0, 0, 1)
    description = "提供快捷安装插件的命令: plg add <插件ID/名称>"

    def __init__(self, frame):
        super().__init__(frame)
        # 注册插件预加载事件
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        """插件预加载时执行 - 注册控制台命令"""
        # 注册主命令 plg，便于后期扩展其他子命令
        self.frame.add_console_cmd_trigger(
            triggers=["plg", "plugin"],
            arg_hint="<子命令> [参数...]",
            usage="插件管理工具 (使用 'plg' 查看帮助)",
            func=self.plg_command
        )
        # self.print_suc("已注册插件管理命令: plg")

    @staticmethod
    def _parse_install_args(args: list[str]):
        """解析 add 子命令参数"""
        plugin_keyword = None
        custom_url = None
        skip_confirm = False

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-url":
                if i + 1 >= len(args):
                    raise ValueError("选项 -url 需要跟随一个地址")
                custom_url = args[i + 1]
                i += 2
                continue
            if arg == "-y":
                skip_confirm = True
                i += 1
                continue
            if arg.startswith("-"):
                raise ValueError(f"未知选项: {arg}")
            if plugin_keyword is not None:
                raise ValueError("只允许提供一个插件名或 ID")
            plugin_keyword = arg
            i += 1

        return plugin_keyword, custom_url, skip_confirm

    def plg_command(self, args: list[str]):
        """
        plg 主命令处理

        Args:
            args: 命令参数列表
        """
        # 如果没有参数或第一个参数不是已知子命令，显示帮助
        if not args:
            self._show_help()
            return

        subcommand = args[0].lower()

        if subcommand == "add":
            # 调用安装插件功能，传递剩余参数
            self.install_plugin_quick(args[1:])
        else:
            # 未知子命令，显示帮助
            self._show_help()

    @staticmethod
    def _show_help():
        """显示帮助信息"""
        fmts.clean_print("§bplg §7- 插件管理工具")
        fmts.clean_print("")
        fmts.clean_print("§f用法: §bplg §f<子命令> §7[参数...]")
        fmts.clean_print("")
        fmts.clean_print("§6子命令:")
        fmts.clean_print("  §badd §f<插件名>      §7安装插件")
        fmts.clean_print("")
        fmts.clean_print("§6选项 (用于 add):")
        fmts.clean_print("  §b-url §f<URL>       §7自定义插件市场源")
        fmts.clean_print("  §b-y                §7跳过确认")
        fmts.clean_print("")
        fmts.clean_print("§6示例:")
        fmts.clean_print("  §fplg add 聊天栏菜单")
        fmts.clean_print("  §fplg add economy §b-y")
        fmts.clean_print(
            "  §fplg add chatbar §b-url §fhttps://example.com/market"
        )
        fmts.clean_print("")
        fmts.clean_print("§7提示: 安装后使用 §breload §7重载生效")


    def install_plugin_quick(self, args: list[str]):
        """
        快捷安装插件

        Args:
            args: 命令参数列表
        """
        # 解析参数
        try:
            plugin_keyword, custom_url, skip_confirm = (
                self._parse_install_args(args)
            )
        except ValueError as exc:
            fmts.clean_print(f"§c{exc}")
            self._show_help()
            return

        if not plugin_keyword:
            self._show_help()
            return

        original_market_url = market.plugin_market_content_url
        try:
            # 设置插件市场源
            if custom_url:
                if not PluginInstaller.validate_custom_url(custom_url):
                    return

                market.plugin_market_content_url = custom_url
                fmts.clean_print(f"§6使用自定义插件市场源: {custom_url}")

            # 获取插件市场数据
            fmts.clean_print(f"§6正在搜索插件: §f{plugin_keyword}")
            market_tree = market.get_market_tree() or {}
            plugins_section = market_tree.get("MarketPlugins") or {}
            packages_section = market_tree.get("Packages") or {}
            plugin_id_map = market.get_plugin_id_name_map() or {}

            if not plugins_section and not packages_section:
                fmts.clean_print("§c插件市场数据为空或未加载")
                return

            # 搜索插件和整合包
            found_item, found_item_id, is_package = (
                PluginInstaller.search_plugin_or_package(
                    plugin_keyword,
                    plugins_section,
                    packages_section,
                    plugin_id_map
                )
            )

            if not found_item or not found_item_id:
                fmts.clean_print(
                    f"§c未找到插件或整合包: {plugin_keyword}"
                )
                fmts.clean_print("§6提示: 请检查名称或 ID 是否正确")
                return

            # 根据类型处理
            if is_package:
                PluginInstaller.install_package(found_item_id, skip_confirm)
            else:
                PluginInstaller.install_single_plugin(
                    found_item_id,
                    plugin_id_map,
                    found_item,
                    skip_confirm
                )

        except Exception as e:
            import traceback
            fmts.clean_print(f"§c安装插件时出错: {e}")
            fmts.clean_print("§c详细错误:")
            error_trace = traceback.format_exc().replace("\n", "\n§c")
            fmts.clean_print(f"§c{error_trace}")
        finally:
            # 恢复原市场源，避免污染其他命令
            if custom_url:
                market.plugin_market_content_url = original_market_url



# 创建插件入口
entry = plugin_entry(QuickPluginInstaller)
