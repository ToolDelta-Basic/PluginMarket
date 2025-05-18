# 聊天栏菜单

---

<div>
<p>此插件通过魔改聊天栏菜单_前置插件实现</p>
<p>安装这个插件无需安装聊天栏菜单_前置插件</p>
<p>也可以和聊天栏菜单_前置插件一起使用</p>
</div>

---

## 聊天栏菜单是什么？
聊天栏菜单是一个可以在聊天栏中显示的菜单，可以通过点击菜单项来执行命令。

---

## 如何使用？
### 安装
放进类插件直接使用就行了

### 配置
在`__init__.py`中修改以下变量为你服务器的配置
```python
CURRENCY_SCOREBOARD = "金币" # 金币计分板
ONLINE_TIME_SCOREBOARD = "§l§b在§e线§d时§a间"  # 在线时间计分板
DEFAULT_HUB_COORDS = [1015, 235, 108]  # 主城坐标
DEFAULT_SHOP_COORDS = [928, 235, -81]  # 商店坐标
HUB_COORDS_FILE = "hub_coords.json"  # 主城坐标文件（可以不管）
SHOP_COORDS_FILE = "shop_coords.json"  # 商店坐标文件（可以不管）
MAX_TRANSFER_AMOUNT = 10000  # 最大转账金额
```

在kimi.py中修改以下变量为你的kimi的api_key
```python
def askai(text):
    # ------------------------------------------------
    api_key = 1234567890  # 请替换成你的Kimi API Key,可以去https://platform.moonshot.cn/docs/guide/start-using-kimi-api获取
    # ------------------------------------------------
```

### 使用
在聊天栏输入`.help`即可打开菜单帮助
