# ToolDelta 插件市场 Official
<b>如何使用插件市场？</b>
 - 直接在启动器进入插件市场
 - 在最新版的 ToolDelta 的控制台输入 <code>插件市场</code>

<b>为什么选择插件市场？</b>
 - 共享 ToolDelta 插件
 - 便捷的安装和使用插件
 - 你可以在此发布和分享你所制作的 ToolDelta 插件

<b>NOTE</b>
 - 我们无法保证所有插件的安全性, 请自行检查部分插件有无恶意行为。

<b>如何上传你的插件？</b>
 - 在 <code>Pull Requests</code> 处提交请求即可
 - 将插件文件夹上传到本项目主目录下
 - 在 `market_tree.json` 添加自己的插件信息

<b>上传的插件的规范格式和要求？</b>
 - 允许上传的文件类型: Python脚本, 文本文件(包括Markdown, TXT file等)
 - 插件需要放在 <code>your_plugin_name/</code> 目录下, 主插件文件需要以 `__init__.py` 命名
 - 同时, 你需要在你的插件文件夹下创建一个`datas.json`:
    这是一个标准的`data.json`的例子.
    ```
    {
      "plugin-id": "snowmenu",
      "author": "SuperScript",
      "version": "0.0.6",
      "description": "贴合租赁服原汁原味的雪球菜单！ 可以自定义雪球菜单内容， 同时也是一个API插件.\n§f使用前请先传送到指令区后输入命令§b.snowmenu-init§f初始化雪球菜单命令方块！\n在配置文件内向雪球菜单添加内容。\n0.0.4: 源码内内置API文档",
      "plugin-type": "classic",
      "pre-plugins": {
        "聊天栏菜单": "0.0.1",
        "基本插件功能库": "0.0.7",
        "前置-世界交互": "0.0.2"
      }
    }
    ```
    - "plugin-id" 值: 字符串, 插件英文ID(是不是英文ID都行, 但是以后不能再更改, 是插件特殊标识)
    - "author" 值: 字符串, 作者名
    - "plugin-type" 值:
        - 如果是 原 DotCS 插件: "dotcs"
        - 如果是 ToolDelta 组合式插件: "classic"
        - 如果是 ToolDelta 注入式插件: "injected"
    - "description" 值: 插件的简介(功能摘要)
    - "pre-plugins" 值: 前置插件的ID与最低需求版本的键值对, 都为string, 没有前置插件则为 `{}`, 插件ID可在`plugin_ids_map.json`内查找
    - "version" 值: 插件版本字符串(更新后别人使用插件市场下载你的插件会提示有新版本)
 - 上传内容若会对用户的设备造成损害, 或会盗窃用户信息的插件, <b>将不予通过审核。</b>