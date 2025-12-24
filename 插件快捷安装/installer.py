"""
插件安装器模块

提供插件和整合包的搜索、安装功能
"""

from tooldelta.plugin_market import market
from tooldelta.utils import fmts
from urllib.parse import urlparse


class PluginInstaller:
    """插件安装器，处理插件和整合包的安装逻辑"""

    @staticmethod
    def validate_custom_url(custom_url: str) -> bool:
        """
        验证自定义 URL 的安全性

        Args:
            custom_url: 自定义插件市场源 URL

        Returns:
            bool: URL 是否有效
        """
        url_lower = custom_url.lower()
        if not url_lower.startswith(("http://", "https://")):
            fmts.clean_print("§c仅支持 http/https 插件市场源")
            return False

        # 安全检查：只允许本地回环地址使用 http
        if url_lower.startswith("http://"):
            try:
                parsed = urlparse(custom_url)
                hostname = parsed.hostname or parsed.netloc.split(':')[0]
                loopback_hosts = {"localhost", "127.0.0.1", "::1"}
                is_loopback = hostname.lower() in loopback_hosts
            except Exception:
                is_loopback = False

            if not is_loopback:
                fmts.clean_print(
                    "§c仅支持 https 插件市场源以确保下载安全"
                )
                fmts.clean_print(
                    "§c提示: http 协议仅允许用于 localhost/127.0.0.1"
                )
                return False
            fmts.clean_print(
                "§e警告: 使用不安全的 http 协议（仅限本地回环地址）"
            )

        return True

    @staticmethod
    def search_plugin_or_package(
        plugin_keyword: str,
        plugins_section: dict,
        packages_section: dict,
        plugin_id_map: dict
    ):
        """
        搜索插件或整合包

        Args:
            plugin_keyword: 搜索关键词
            plugins_section: 插件列表数据
            packages_section: 整合包列表数据
            plugin_id_map: 插件 ID 映射表

        Returns:
            tuple: (found_item, found_item_id, is_package)
        """
        # 1. 在普通插件中搜索 - 通过 ID 精确匹配
        if plugin_keyword in plugin_id_map:
            found_item_id = plugin_keyword
            found_item = plugins_section.get(plugin_keyword)
            if found_item:
                return found_item, found_item_id, False

        # 2. 在普通插件中搜索 - 通过名称模糊搜索
        for pid, pname in plugin_id_map.items():
            if pname and plugin_keyword.lower() in pname.lower():
                found_item = plugins_section.get(pid)
                if found_item:
                    return found_item, pid, False

        # 3. 在普通插件中搜索 - 通过插件数据的名称搜索
        for pid, pdata in plugins_section.items():
            plugin_name = pdata.get("name") or ""
            if plugin_keyword.lower() in plugin_name.lower():
                return pdata, pid, False

        # 4. 在整合包中搜索 - 通过整合包名称
        for pkg_name, pkg_data in packages_section.items():
            # 整合包名称可能带 [pkg] 前缀，也可能不带
            pkg_display_name = pkg_name.replace("[pkg]", "").strip()
            if plugin_keyword.lower() in pkg_display_name.lower():
                if pkg_name.startswith("[pkg]"):
                    pkg_id = pkg_name
                else:
                    pkg_id = f"[pkg]{pkg_name}"
                return pkg_data, pkg_id, True

        return None, None, False

    @staticmethod
    def confirm_installation(prompt_text: str) -> bool:
        """
        请求用户确认安装

        Args:
            prompt_text: 提示文本

        Returns:
            bool: 用户是否确认安装
        """
        fmts.clean_print("")
        try:
            prompt = fmts.clean_fmt(prompt_text)
            confirm = input(prompt).strip().lower()
        except EOFError:
            fmts.clean_print("§c未收到输入，已取消安装")
            return False
        return confirm in ["y", "yes", "是", "确定", "确认"]

    @staticmethod
    def install_single_plugin(
        plugin_id: str,
        plugin_id_map: dict,
        found_plugin: dict,
        skip_confirm: bool
    ):
        """安装单个插件"""
        # 获取插件详细数据
        plugin_data = market.get_plugin_data_from_market(plugin_id)
        if not plugin_data:
            fmts.clean_print(
                f"§c未能获取插件 {plugin_id} 的详情，安装已取消"
            )
            fmts.clean_print(
                "§6提示: 请检查插件市场源是否正常或插件 ID 是否正确"
            )
            return

        plugin_name = plugin_id_map.get(
            plugin_id, found_plugin.get("name", plugin_id)
        )

        # 显示插件信息
        fmts.clean_print("§a找到插件:")
        fmts.clean_print(f"  名称: §f{plugin_name}")
        fmts.clean_print(f"  ID: §f{plugin_id}")
        fmts.clean_print(
            f"  作者: §f{getattr(plugin_data, 'author', '未知')}"
        )
        fmts.clean_print(
            f"  版本: §f{getattr(plugin_data, 'version_str', '未知')}"
        )
        fmts.clean_print(
            f"  类型: §f{getattr(plugin_data, 'plugin_type_str', '未知')}"
        )
        fmts.clean_print(
            f"  描述: §f{getattr(plugin_data, 'description', '暂无')}"
        )

        # 显示前置插件
        if plugin_data.pre_plugins:
            pre_plugins_list = [
                f"{k} v{v}"
                for k, v in plugin_data.pre_plugins.items()
            ]
            pre_plugins_str = ", ".join(pre_plugins_list)
            fmts.clean_print(f"  前置插件: §f{pre_plugins_str}")

        # 二次确认
        if not skip_confirm:
            confirmed = PluginInstaller.confirm_installation(
                "§6是否下载安装此插件? (§aY§6/§cN§6): "
            )
            if not confirmed:
                fmts.clean_print("§c已取消安装")
                return

        # 下载插件
        fmts.clean_print(f"§6正在下载插件: §f{plugin_name}")
        market.download_plugin(plugin_data)
        fmts.clean_print(f"§a插件 §f{plugin_name} §a安装完成!")
        fmts.clean_print("§6提示: 使用 §breload§6 命令重载插件使其生效")

    @staticmethod
    def install_package(package_id: str, skip_confirm: bool):
        """安装插件整合包"""
        # 获取整合包详细数据
        package_data = market.get_package_data_from_market(package_id)
        if not package_data:
            fmts.clean_print(
                f"§c未能获取整合包 {package_id} 的详情，安装已取消"
            )
            fmts.clean_print(
                "§6提示: 请检查插件市场源是否正常或整合包名称是否正确"
            )
            return

        package_name = package_id.replace("[pkg]", "").strip()

        # 显示整合包信息
        fmts.clean_print("§a找到整合包:")
        fmts.clean_print(f"  名称: §f{package_name}")
        fmts.clean_print(
            f"  作者: §f{getattr(package_data, 'author', '未知')}"
        )
        fmts.clean_print(
            f"  版本: §f{getattr(package_data, 'version', '未知')}"
        )
        fmts.clean_print(
            f"  描述: §f{getattr(package_data, 'description', '暂无')}"
        )

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
            confirmed = PluginInstaller.confirm_installation(
                "§6是否下载安装此整合包? (§aY§6/§cN§6): "
            )
            if not confirmed:
                fmts.clean_print("§c已取消安装")
                return

        # 下载整合包
        fmts.clean_print(f"§6正在下载整合包: §f{package_name}")
        market.download_plugin_package(package_data)
        fmts.clean_print(f"§a整合包 §f{package_name} §a安装完成!")
        fmts.clean_print("§6提示: 使用 §breload§6 命令重载插件使其生效")
