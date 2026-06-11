from __future__ import annotations

from typing import Any

from guild_cloud_interop.config import Config


CREATE_GUILD_PROMPT_FALLBACKS = {
    "已有公会提示词": "§c❀ §r你已经有公会了",
    "快捷创建缺少名称提示词": "§a❀ §r请输入公会名称，例如: 公会创建 我的公会",
    "快捷创建名称长度无效提示词": "§c❀ §r公会名必须在2-16个字符之间",
    "创建公会余额不足提示词": (
        "§c❀ §r创建公会需要 §e{consume}§r 点 "
        "§b{scoreboard}§r 计分板积分\n§c❀ §r当前余额: §f{balance}"
    ),
    "创建公会提示词": (
        "§a❀ §r创建公会将消耗 §e{consume} §b{scoreboard} \n"
        "§a❀ §r当前余额: §f{balance}\n"
        "§a❀ §r输入 §a确认§7 继续创建，输入 §cq§7 取消"
    ),
    "创建公会回复超时提示词": "§c❀ §r回复超时，已取消创建公会",
    "创建公会取消提示词": "§c❀ §r已取消创建公会",
    "创建公会输入名称提示词": "§a❀ §r请输入公会名字:\n§a❀ §r要求: 2-20个字符，不能包含特殊符号",
    "创建公会名称无效提示词": "§c❀ §r{error}",
    "创建公会二次余额不足提示词": (
        "§c❀ §r当前 §b{scoreboard}§r 余额不足，"
        "需要 §e{consume}§r，当前 §f{balance}"
    ),
    "创建公会成功提示词": "§a❀ §r已创建公会 §e{guild}",
    "创建公会全服公告提示词": "§a❀ §r§e{player}§r 创建了公会 §e{guild}§r！",
    "创建公会名称已存在提示词": "§c❀ §r该公会名已存在",
    "菜单回复超时提示词": "§c❀ §r回复超时！已退出公会系统",
    "无效指令提示词": "§c❀ §r无效的指令",
    "通用分页为空提示词": "§c❀ §r{title}为空",
    "通用分页超时提示词": "§c❀ §r操作超时",
    "通用分页退出提示词": "§a❀ §r已退出",
    "通用分页无效选择提示词": "§c❀ §r无效的选择",
    "公会列表为空提示词": "§c❀ §r公会列表为空",
    "公会列表分页超时提示词": "§c❀ §r操作超时",
    "公会列表分页退出提示词": "§a❀ §r已退出",
}


def render_prompt(template: str, **values: Any) -> str:
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def render_create_guild_prompt(key: str, **values: Any) -> str:
    return render_config_prompt(key, **values)


def render_config_prompt(key: str, **values: Any) -> str:
    prompt_config = getattr(Config, "PROMPT_CONFIG", {})
    fallback = CREATE_GUILD_PROMPT_FALLBACKS.get(key, "")
    template = fallback
    if isinstance(prompt_config, dict):
        configured = prompt_config.get(key)
        if isinstance(configured, str) and configured:
            template = configured

    values.setdefault("consume", getattr(Config, "GUILD_CREATION_COST", ""))
    values.setdefault("scoreboard", getattr(Config, "GUILD_SCOREBOARD", ""))
    return render_prompt(template, **values)
