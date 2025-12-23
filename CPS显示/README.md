# CPS显示

## 概述
通过挥手检测机器人周围玩家CPS并显示在玩家屏幕，也可以作为一个前置插件。检测范围限制在机器人附近。这是一个娱乐插件，不适合反制外挂。

## 配置
- 检测周期秒：CPS = 周期内检测次数 / 检测周期
- 是否显示：是否给玩家发 titleraw 显示 cps
- 显示间隔秒：玩家最短多久刷新一次标题
- 前置空格：调节CPS显示位置
- 颜色前缀：设置显示颜色

## 使用
- 安装插件后大概需要重启机器人才能有效检测
- 作为前置插件：
1.获取：
```python
def on_def(self):
    self.cps = self.GetPluginAPI("CPS显示")
```
2.调用：
```python
# 获取某玩家 cps：
cps_value = self.cps.get_cps("玩家名")

# 获取全部玩家 cps 快照：
all_cps = self.cps.get_all_cps()

# 订阅：当 cps 达到阈值触发回调
def on_high_cps(player_name: str, cps: float):
    # 此处执行
    pass

sub_id = self.cps.subscribe(4.0, on_high_cps, cooldown=1.0)

# 取消订阅：
self.cps.unsubscribe(sub_id)
```
