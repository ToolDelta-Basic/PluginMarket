# v1.6.0 更新日志 — 纯信道架构 + 服务化 + 分层配置

## 架构

### 框架 = 通信信道
- ChannelHost: 扫描库 → 拓扑排序 → 顺序 mount
- ServiceRegistry: 带 mid 权限 + scope 视图 + 白名单保护
- EventBus: 发布订阅
- 18 个库（12 核心 + 6 可选）

### 服务白名单
- 核心服务（config/audit/security/protocol 等）受保护
- 只有库（libraries/）可首次注册核心服务
- 模块不可覆盖已注册的受保护服务

### 万物皆服务
模块通过 `self.services.get("xxx")` 获取一切能力：
- `protocol` — 常量 + 事件类型
- `audit` — 审计日志
- `security` — 安全工具
- `modules` — 模块管理
- `config` — 分层配置
- `command` — 命令注册
- `message` — 消息发送
- `gatekeeper` — 权限管理

### 分层配置系统
- 权威源: 分层文件（核心.json / 安全.json / 管理.json / 模块/*.json）
- 映射: `配置映射.json` 定义顶层键归属
- 合并视图: `全部配置(只读视图).json` 自动生成
- 外部修改: 5 秒轮询检测 → 拆分同步回分层
- 旧 config.json: 一次性迁移

### 自动依赖安装
- PackageManager 检测缺失的 Python 包
- 自动从镜像源 pip install --target 第三方库/
- 支持清华/阿里云/PyPI 多镜像回退

## 安全
- scope 视图: 模块只能访问 mid >= 自身的服务
- 白名单: 核心服务不可被模块覆盖
- 命令注册校验: 非 root 模块不能注册 min_uid < 自身 mid 的命令

## 统计
- 18 个库全部挂载
- 23/23 模块加载
- 36 条命令注册
- 27 个服务在线
- 0 语法错误

## 删除
- core/host.py（旧 FrameworkHost）
- core/library.py
- 5 个 Bootstrap 文件
- config.json 单文件模式（废弃，自动迁移）
