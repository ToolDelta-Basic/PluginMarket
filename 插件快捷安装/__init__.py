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
from urllib.parse import urlparse


class QuickPluginInstaller(Plugin):
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

    def _parse_install_args(self, args: list[str]):
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

    def _show_help(self):
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
        fmts.clean_print("  §fplg add chatbar §b-url §fhttps://example.com/market")
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
            plugin_keyword, custom_url, skip_confirm = self._parse_install_args(args)
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
                url_lower = custom_url.lower()
                if not url_lower.startswith(("http://", "https://")):
                    fmts.clean_print("§c仅支持 http/https 插件市场源")
                    return

                # 安全检查：只允许本地回环地址使用 http，其他必须使用 https
                if url_lower.startswith("http://"):
                    try:
                        parsed = urlparse(custom_url)
                        hostname = parsed.hostname or parsed.netloc.split(':')[0]
                        is_loopback = hostname.lower() in {"localhost", "127.0.0.1", "::1"}
                    except Exception:
                        is_loopback = False

                    if not is_loopback:
                        fmts.clean_print("§c仅支持 https 插件市场源以确保下载安全")
                        fmts.clean_print("§c提示: http 协议仅允许用于 localhost/127.0.0.1")
                        return
                    fmts.clean_print("§e警告: 使用不安全的 http 协议（仅限本地回环地址）")

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
            found_item = None
            found_item_id = None
            is_package = False

            # 1. 在普通插件中搜索 - 通过 ID 精确匹配
            if plugin_keyword in plugin_id_map:
                found_item_id = plugin_keyword
                found_item = plugins_section.get(plugin_keyword)

            # 2. 在普通插件中搜索 - 通过名称模糊搜索
            if not found_item:
                for pid, pname in plugin_id_map.items():
                    if pname and plugin_keyword.lower() in pname.lower():
                        found_item_id = pid
                        found_item = plugins_section.get(pid)
                        break

            # 3. 在普通插件中搜索 - 通过插件数据的名称搜索
            if not found_item:
                for pid, pdata in plugins_section.items():
                    if plugin_keyword.lower() in (pdata.get("name") or "").lower():
                        found_item_id = pid
                        found_item = pdata
                        break

            # 4. 在整合包中搜索 - 通过整合包名称
            if not found_item:
                for pkg_name, pkg_data in packages_section.items():
                    # 整合包名称可能带 [pkg] 前缀，也可能不带
                    pkg_display_name = pkg_name.replace("[pkg]", "").strip()
                    if plugin_keyword.lower() in pkg_display_name.lower():
                        found_item_id = pkg_name if pkg_name.startswith("[pkg]") else f"[pkg]{pkg_name}"
                        found_item = pkg_data
                        is_package = True
                        break

            if not found_item or not found_item_id:
                fmts.clean_print(f"§c未找到插件或整合包: {plugin_keyword}")
                fmts.clean_print("§6提示: 请检查名称或 ID 是否正确")
                return

            # 根据类型处理
            if is_package:
                # 处理整合包
                self._install_package(found_item_id, skip_confirm)
            else:
                # 处理普通插件
                self._install_single_plugin(found_item_id, plugin_id_map, found_item, skip_confirm)

        except Exception as e:
            import traceback
            fmts.clean_print(f"§c安装插件时出错: {e}")
            fmts.clean_print("§c详细错误:")
            fmts.clean_print("§c" + traceback.format_exc().replace("\n", "\n§c"))
        finally:
            # 恢复原市场源，避免污染其他命令
            if custom_url:
                market.plugin_market_content_url = original_market_url

    def _install_single_plugin(self, plugin_id: str, plugin_id_map: dict, found_plugin: dict, skip_confirm: bool):
        """安装单个插件"""
        # 获取插件详细数据
        plugin_data = market.get_plugin_data_from_market(plugin_id)
        if not plugin_data:
            fmts.clean_print(f"§c未能获取插件 {plugin_id} 的详情，安装已取消")
            fmts.clean_print("§6提示: 请检查插件市场源是否正常或插件 ID 是否正确")
            return

        plugin_name = plugin_id_map.get(plugin_id, found_plugin.get("name", plugin_id))

        # 显示插件信息
        fmts.clean_print("§a找到插件:")
        fmts.clean_print(f"  名称: §f{plugin_name}")
        fmts.clean_print(f"  ID: §f{plugin_id}")
        fmts.clean_print(f"  作者: §f{getattr(plugin_data, 'author', '未知')}")
        fmts.clean_print(f"  版本: §f{getattr(plugin_data, 'version_str', '未知')}")
        fmts.clean_print(f"  类型: §f{getattr(plugin_data, 'plugin_type_str', '未知')}")
        fmts.clean_print(f"  描述: §f{getattr(plugin_data, 'description', '暂无')}")

        # 显示前置插件
        if plugin_data.pre_plugins:
            pre_plugins_str = ", ".join([f"{k} v{v}" for k, v in plugin_data.pre_plugins.items()])
            fmts.clean_print(f"  前置插件: §f{pre_plugins_str}")

        # 二次确认
        if not skip_confirm:
            fmts.clean_print("")
            try:
                confirm = input(fmts.clean_fmt("§6是否下载安装此插件? (§aY§6/§cN§6): ")).strip().lower()
            except EOFError:
                fmts.clean_print("§c未收到输入，已取消安装")
                return
            if confirm not in ["y", "yes", "是", "确定", "确认"]:
                fmts.clean_print("§c已取消安装")
                return

        # 下载插件
        fmts.clean_print(f"§6正在下载插件: §f{plugin_name}")
        market.download_plugin(plugin_data)
        fmts.clean_print(f"§a插件 §f{plugin_name} §a安装完成!")
        fmts.clean_print("§6提示: 使用 §breload§6 命令重载插件使其生效")

    def _install_package(self, package_id: str, skip_confirm: bool):
        """安装插件整合包"""
        # 获取整合包详细数据
        package_data = market.get_package_data_from_market(package_id)
        if not package_data:
            fmts.clean_print(f"§c未能获取整合包 {package_id} 的详情，安装已取消")
            fmts.clean_print("§6提示: 请检查插件市场源是否正常或整合包名称是否正确")
            return

        package_name = package_id.replace("[pkg]", "").strip()

        # 显示整合包信息
        fmts.clean_print("§a找到整合包:")
        fmts.clean_print(f"  名称: §f{package_name}")
        fmts.clean_print(f"  作者: §f{getattr(package_data, 'author', '未知')}")
        fmts.clean_print(f"  版本: §f{getattr(package_data, 'version', '未知')}")
        fmts.clean_print(f"  描述: §f{getattr(package_data, 'description', '暂无')}")

        # 获取包含的插件列表
        plugin_id_map = market.get_plugin_id_name_map() or {}
        included_plugins = []
        for pid in getattr(package_data, 'plugin_ids', []):
            if pname := plugin_id_map.get(pid):
                included_plugins.append(pname)
            else:
                included_plugins.append(pid)

        if included_plugins:
            fmts.clean_print("  包含插件:")
            for pname in included_plugins:
                fmts.clean_print(f"    §7- §f{pname}")

        # 二次确认
        if not skip_confirm:
            fmts.clean_print("")
            try:
                confirm = input(fmts.clean_fmt("§6是否下载安装此整合包? (§aY§6/§cN§6): ")).strip().lower()
            except EOFError:
                fmts.clean_print("§c未收到输入，已取消安装")
                return
            if confirm not in ["y", "yes", "是", "确定", "确认"]:
                fmts.clean_print("§c已取消安装")
                return

        # 下载整合包
        fmts.clean_print(f"§6正在下载整合包: §f{package_name}")
        market.download_plugin_package(package_data)
        fmts.clean_print(f"§a整合包 §f{package_name} §a安装完成!")
        fmts.clean_print("§6提示: 使用 §breload§6 命令重载插件使其生效")


# 创建插件入口
entry = plugin_entry(QuickPluginInstaller)
