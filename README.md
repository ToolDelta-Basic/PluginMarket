# ToolDelta 插件市场 Official

**ToolDelta 插件市场** 是 **[ToolDelta](https://github.com/ToolDelta-Basic/ToolDelta)** 的官方插件市场源。
现在已经拥有 **131 个插件**、 **3 个整合包** 了！

**如何使用插件市场？**
  - 直接在启动器进入插件市场
  - 在最新版的 ToolDelta 的控制台输入 `插件市场`

**为什么选择插件市场？**
  - 共享 ToolDelta 插件
  - 便捷的安装和使用插件
  - 你可以在此发布和分享你所制作的 ToolDelta 插件

**插件上传**

  - **如何上传你的插件？**
      - 在 `Pull Requests` 处提交请求即可
      - 将插件文件夹上传到本项目主目录下
      - 不需要修改其他地方 如 `market_tree.json`，工作流会自动更新这些文件。

  - **上传的插件的规范格式和要求？**
      - 允许上传的文件类型: Python脚本， 文本文件(包括Markdown, TXT file等)
      - 插件需要放在 `your_plugin_name/` 目录下, 主插件文件需要以 `__init__.py` 命名
      - 同时, 你需要在你的插件文件夹下创建一个`datas.json`:
          这是一个标准的`datas.json`的例子：
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
          - "author" 值：字符串， 作者名
          - "plugin-type" 值：
              - 如果是 ToolDelta 组合式插件: "classic"
          - "description" 值：插件的简介(功能摘要)
          - "pre-plugins" 值：前置插件的ID与最低需求版本的键值对, 都为string, 没有前置插件则为 `{}`， 插件ID可在`plugin_ids_map.json`内查找
          - "version" 值：插件版本字符串(更新后别人使用插件市场下载你的插件会提示有新版本)
      - 上传内容若会对用户的设备造成损害， 或会盗窃用户信息的插件， **将不予通过审核。**

**插件整合包上传**

整合包包含了插件文件的链接、插件配置文件甚至插件数据文件。

你可以依靠其来分享你的 ToolDelta 环境。

- **如何上传你的插件？**
      - 在 `Pull Requests` 处提交请求即可
      - 将插件整合包文件夹上传到本项目主目录下
      - 不需要修改其他地方 如 `market_tree.json`，工作流会自动更新这些文件。

  - **上传的整合包的规范格式和要求？**
      - 整合包文件夹名以 [pkg] 开头
      - 如果上传内容包含插件配置，那么在整合包下创建一个 `插件配置文件` 文件夹，并把你需要上传的那部分插件配置文件放进去
          - 会**覆盖**掉用户原有的同名配置！
      - 如果上传内容包含插件数据，那么在整合包下创建一个 `插件数据文件` 文件夹，并把你需要上传的那部分插件数据文件夹放进去
          - 会**覆盖**掉用户原有的同名数据文件！
      - 同时, 你需要在你的插件文件夹下创建一个`datas.json`:
          这是一个标准的`datas.json`的例子：
          ```
          {
            "plugin-ids": [
                "聊天栏菜单",
                "自定义聊天栏菜单",
                "入服欢迎",
                "better-announcebar",
                "gobang_game",
                "choose-song"
            ],
            "description": "入门ToolDelta的插件包， 提供了ToolDelta的经典插件集",
            "author": "SuperScript",
            "version": "0.0.2"
          }
          ```
          - "plugin-id" 值: 字符串, 插件英文ID(是不是英文ID都行, 但是以后不能再更改, 是插件特殊标识)
          - "author" 值：字符串， 作者名
          - "plugin-type" 值：
              - 如果是 ToolDelta 组合式插件: "classic"
          - "description" 值：插件的简介(功能摘要)
          - "pre-plugins" 值：前置插件的ID与最低需求版本的键值对, 都为string, 没有前置插件则为 `{}`， 插件ID可在`plugin_ids_map.json`内查找
          - "version" 值：插件版本字符串(更新后别人使用插件市场下载你的插件会提示有新版本)
      - 上传内容若会对用户的设备造成损害， 或会盗窃用户信息的插件， **将不予通过审核。**