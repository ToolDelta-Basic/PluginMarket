# License : Apache-2.0 http://www.apache.org/licenses/
# Author  : xingchen
# Email   : <2042105325@qq.com> <xingchenawa@qq.com>
import gzip
import io
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import uuid
import zipfile
from typing import Any
from urllib.parse import urlparse

import flask
import requests
from lib import yaml
from tooldelta import (
    Builtins,
    Config,
    Frame,
    Plugin,
    Print,
    plugins,
    safe_jump,
    urlmethod,
)
from tooldelta.urlmethod import get_free_port

STD_PLU_CFG = {
    "CQHTTP运行目录": str,
    "CQHTTP运行文件": str,
    "CQHTTP运行UUID": str,
    "CQHTTP自动重启": bool,
    "CQHTTP自动重启最大限次": int,
    "输出CQHTTP输出[可能导致刷屏][如果关闭将会屏蔽CQHTTP成功登陆账号后的消息]": bool,
    "内置签名服务端": bool,
    "签名服务端运行目录": str,
    "SIGN-SERVER自动重启": bool,
    "SIGN-SERVER自动重启最大限次": int,
    "JDK位置": str,
    "Sign-Server配置": dict,
    "端口被占用时随机端口[全局][插件内]": bool,
    "当签名服务端无响应时自动重启": bool,
    "输出签名服务器输出[可能导致刷屏]": bool,
    "CQHTTP事件处理服务端配置": dict,
    "自动重启等待时间[S]": int,
    "群服互通相关配置": dict,
    "仅输出被启用的群消息": bool,
}

DEFAULT_PLU_CFG = {
    "CQHTTP运行目录": os.path.join(os.getcwd(), "插件数据文件", "群服互通", "cq-http"),
    "CQHTTP运行文件": "",
    "CQHTTP运行UUID": uuid.uuid5(uuid.NAMESPACE_DNS, "go-cqhttp").hex,
    "CQHTTP自动重启": True,
    "CQHTTP自动重启最大限次": 3,
    "输出CQHTTP输出[可能导致刷屏][如果关闭将会屏蔽CQHTTP成功登陆账号后的消息]": False,
    "内置签名服务端": True,
    "签名服务端运行目录": "",
    "SIGN-SERVER自动重启": True,
    "SIGN-SERVER自动重启最大限次": 2,
    "JDK位置": "",
    "Sign-Server配置": {
        "host": "127.0.0.1",
        "端口": 8080,
        "key": "114514",
        "share_token": False,
        "auto_register": True,
        "lib版本": "8.9.96",
    },
    "端口被占用时随机端口[全局][插件内]": True,
    "当签名服务端无响应时自动重启": True,
    "输出签名服务器输出[可能导致刷屏]": True,
    "CQHTTP事件处理服务端配置": {"host": "127.0.0.1", "端口": 8087},
    "自动重启等待时间[S]": 10,
    "群服互通相关配置": {
        "管理员账号": "0000000000",
        "启用群列表": [
            {
                "群名称[请注意敏感词]114514快乐群1": "114514000",
                "群名称[请注意敏感词]114514快乐群2": "114514000",
            }
        ],
    },
    "仅输出被启用的群消息": True,
}

CQHTTP_DEF_CFG: str = """
# Not Initial Config
# go-cqhttp 默认配置文件

account: # 账号相关
  uin: 1233456 # QQ账号
  password: '' # 密码为空时使用扫码登录
  encrypt: false  # 是否开启密码加密
  status: 0      # 在线状态 请参考 https://docs.go-cqhttp.org/guide/config.html#在线状态
  relogin: # 重连设置
    delay: 3   # 首次重连延迟, 单位秒
    interval: 3   # 重连间隔
    max-times: 0  # 最大重连次数, 0为无限制

  # 是否使用服务器下发的新地址进行重连
  # 注意, 此设置可能导致在海外服务器上连接情况更差
  use-sso-address: true
  # 是否允许发送临时会话消息
  allow-temp-session: false

  # 数据包的签名服务器列表，第一个作为主签名服务器，后续作为备用
  # 兼容 https://github.com/fuqiuluo/unidbg-fetch-qsign
  # 如果遇到 登录 45 错误, 或者发送信息风控的话需要填入一个或多个服务器
  # 不建议设置过多，设置主备各一个即可，超过 5 个只会取前五个
  # 示例:
  # sign-servers:
  #   - url: 'http://127.0.0.1:8080' # 本地签名服务器
  #     key: "114514"  # 相应 key
  #     authorization: "-"   # authorization 内容, 依服务端设置
  #   - url: 'https://signserver.example.com' # 线上签名服务器
  #     key: "114514"
  #     authorization: "-"
  #   ...
  #
  # 服务器可使用docker在本地搭建或者使用他人开放的服务
  sign-servers:
    - url: '-'  # 主签名服务器地址， 必填
      key: '114514'  # 签名服务器所需要的apikey, 如果签名服务器的版本在1.1.0及以下则此项无效
      authorization: '-'   # authorization 内容, 依服务端设置，如 'Bearer xxxx'
    - url: '-'  # 备用
      key: '114514'
      authorization: '-'

  # 判断签名服务不可用（需要切换）的额外规则
  # 0: 不设置 （此时仅在请求无法返回结果时判定为不可用）
  # 1: 在获取到的 sign 为空 （若选此建议关闭 auto-register，一般为实例未注册但是请求签名的情况）
  # 2: 在获取到的 sign 或 token 为空（若选此建议关闭 auto-refresh-token ）
  rule-change-sign-server: 1

  # 连续寻找可用签名服务器最大尝试次数
  # 为 0 时会在连续 3 次没有找到可用签名服务器后保持使用主签名服务器，不再尝试进行切换备用
  # 否则会在达到指定次数后 **退出** 主程序
  max-check-count: 0
  # 签名服务请求超时时间(s)
  sign-server-timeout: 60
  # 如果签名服务器的版本在1.1.0及以下, 请将下面的参数改成true
  # 建议使用 1.1.6 以上版本，低版本普遍半个月冻结一次
  is-below-110: false
  # 在实例可能丢失（获取到的签名为空）时是否尝试重新注册
  # 为 true 时，在签名服务不可用时可能每次发消息都会尝试重新注册并签名。
  # 为 false 时，将不会自动注册实例，在签名服务器重启或实例被销毁后需要重启 go-cqhttp 以获取实例
  # 否则后续消息将不会正常签名。关闭此项后可以考虑开启签名服务器端 auto_register 避免需要重启
  # 由于实现问题，当前建议关闭此项，推荐开启签名服务器的自动注册实例
  auto-register: false
  # 是否在 token 过期后立即自动刷新签名 token（在需要签名时才会检测到，主要防止 token 意外丢失）
  # 独立于定时刷新
  auto-refresh-token: false
  # 定时刷新 token 间隔时间，单位为分钟, 建议 30~40 分钟, 不可超过 60 分钟
  # 目前丢失token也不会有太大影响，可设置为 0 以关闭，推荐开启
  refresh-interval: 40

heartbeat:
  # 心跳频率, 单位秒
  # -1 为关闭心跳
  interval: 5

message:
  # 上报数据类型
  # 可选: string,array
  post-format: string
  # 是否忽略无效的CQ码, 如果为假将原样发送
  ignore-invalid-cqcode: false
  # 是否强制分片发送消息
  # 分片发送将会带来更快的速度
  # 但是兼容性会有些问题
  force-fragment: false
  # 是否将url分片发送
  fix-url: false
  # 下载图片等请求网络代理
  proxy-rewrite: ''
  # 是否上报自身消息
  report-self-message: false
  # 移除服务端的Reply附带的At
  remove-reply-at: false
  # 为Reply附加更多信息
  extra-reply-data: false
  # 跳过 Mime 扫描, 忽略错误数据
  skip-mime-scan: false
  # 是否自动转换 WebP 图片
  convert-webp-image: false
  # download 超时时间(s)
  http-timeout: 15

output:
  # 日志等级 trace,debug,info,warn,error
  log-level: warn
  # 日志时效 单位天. 超过这个时间之前的日志将会被自动删除. 设置为 0 表示永久保留.
  log-aging: 15
  # 是否在每次启动时强制创建全新的文件储存日志. 为 false 的情况下将会在上次启动时创建的日志文件续写
  log-force-new: true
  # 是否启用日志颜色
  log-colorful: true
  # 是否启用 DEBUG
  debug: false # 开启调试模式

# 默认中间件锚点
default-middlewares: &default
  # 访问密钥, 强烈推荐在公网的服务器设置
  access-token: ''
  # 事件过滤器文件目录
  filter: ''
  # API限速设置
  # 该设置为全局生效
  # 原 cqhttp 虽然启用了 rate_limit 后缀, 但是基本没插件适配
  # 目前该限速设置为令牌桶算法, 请参考:
  # https://baike.baidu.com/item/%E4%BB%A4%E7%89%8C%E6%A1%B6%E7%AE%97%E6%B3%95/6597000?fr=aladdin
  rate-limit:
    enabled: false # 是否启用限速
    frequency: 1  # 令牌回复频率, 单位秒
    bucket: 1     # 令牌桶大小

database: # 数据库相关设置
  leveldb:
    # 是否启用内置leveldb数据库
    # 启用将会增加10-20MB的内存占用和一定的磁盘空间
    # 关闭将无法使用 撤回 回复 get_msg 等上下文相关功能
    enable: true
  sqlite3:
    # 是否启用内置sqlite3数据库
    # 启用将会增加一定的内存占用和一定的磁盘空间
    # 关闭将无法使用 撤回 回复 get_msg 等上下文相关功能
    enable: false
    cachettl: 3600000000000 # 1h

# 连接服务列表
servers:
  # 添加方式，同一连接方式可添加多个，具体配置说明请查看文档
  #- http: # http 通信
  #- ws:   # 正向 Websocket
  #- ws-reverse: # 反向 Websocket
  #- pprof: #性能分析服务器

  - http: # HTTP 通信设置
      address: 0.0.0.0:5700 # HTTP监听地址
      version: 11     # OneBot协议版本, 支持 11/12
      timeout: 5      # 反向 HTTP 超时时间, 单位秒，<5 时将被忽略
      long-polling:   # 长轮询拓展
        enabled: false       # 是否开启
        max-queue-size: 2000 # 消息队列大小，0 表示不限制队列大小，谨慎使用
      middlewares:
        <<: *default # 引用默认中间件
      post:           # 反向HTTP POST地址列表
      - url: ''                # 地址
        secret: ''             # 密钥
        max-retries: 10         # 最大重试，0 时禁用
        retries-interval: 1500 # 重试时间，单位毫秒，0 时立即
      #- url: http://127.0.0.1:5701/ # 地址
      #  secret: ''                  # 密钥
      #  max-retries: 10             # 最大重试，0 时禁用
      #  retries-interval: 1000      # 重试时间，单位毫秒，0 时立即
"""

CQHTTP_SIGN_SERVER_LIST = [
    {"url": "https://qsign.wuliya.icu/8978/sign", "key": "wuliya"},
    {"url": "https://qsign.wuliya.icu/8988/sign", "key": "wuliya"},
    {"url": "https://qsign.wuliya.icu/8996/sign", "key": "wuliya"},
    {"url": "http://qsign.angryrabbit.cn/8978", "key": "114514"},
    {"url": "http://qsign.pippi.top", "key": "yui"},
    {"url": "http://1.QSign.icu", "key": "XxxX"},
    {"url": "http://2.QSign.icu", "key": "XxxX"},
    {"url": "http://3.QSign.icu", "key": "XxxX"},
    {"url": "http://4.QSign.icu", "key": "XxxX"},
    {"url": "http://5.QSign.icu", "key": "XxxX"},
]

CQHTTP_EVENT_HANDLE_MSG_PAG: str = """
<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="utf-8">
	<title>ToolDelta plugin - Group service API Back page</title>

	<style type="text/css">

	::selection { background-color: #E13300; color: white; }
	::-moz-selection { background-color: #E13300; color: white; }

	body {
		background-color: #fff;
		margin: 40px;
		font: 13px/20px normal Helvetica, Arial, sans-serif;
		color: #4F5155;
	}

	a {
		color: #003399;
		background-color: transparent;
		font-weight: normal;
	}

	h1 {
		color: #444;
		background-color: transparent;
		border-bottom: 1px solid #D0D0D0;
		font-size: 19px;
		font-weight: normal;
		margin: 0 0 14px 0;
		padding: 14px 15px 10px 15px;
	}

	code {
		font-family: Consolas, Monaco, Courier New, Courier, monospace;
		font-size: 12px;
		background-color: #f9f9f9;
		border: 1px solid #D0D0D0;
		color: #002166;
		display: block;
		margin: 14px 0 14px 0;
		padding: 12px 10px 12px 10px;
	}

	#body {
		margin: 0 15px 0 15px;
	}

	p.footer {
		text-align: right;
		font-size: 11px;
		border-top: 1px solid #D0D0D0;
		line-height: 32px;
		padding: 0 10px 0 10px;
		margin: 20px 0 0 0;
	}

	#container {
		margin: 10px;
		border: 1px solid #D0D0D0;
		box-shadow: 0 0 8px #D0D0D0;
	}
	</style>
</head>
<body>

<div id="container">
	<p class="footer">MSG</p>
</div>

</body>
</html>
"""


@plugins.add_plugin
class GroupServerInterworking(Plugin):
    name = "群服互通"
    author = "xingchen"
    version = (0, 0, 5)

    def __init__(self, frame: Frame):
        self.frame: Frame = frame
        self.game_ctrl = frame.get_game_control()
        self.no_join_game_debug = False
        self.base_dir = os.path.join(os.getcwd(), "插件数据文件", self.name)
        self.base_CQHTTP_dir = os.path.join(
            os.getcwd(), "插件数据文件", self.name, "cq-http"
        )
        self.base_SIGN_dir = os.path.join(
            os.getcwd(), "插件数据文件", self.name, "sign-server"
        )
        self.sys_type = platform.system().lower()
        self.sys_machine = platform.machine().lower()
        self.TMPJson = Builtins.TMPJson()
        self.Config, _ = Config.getPluginConfigAndVersion(
            self.name, STD_PLU_CFG, DEFAULT_PLU_CFG, self.version
        )
        self.ConfigPath = os.path.join(os.getcwd(), "插件配置文件", f"{self.name}.json")
        self.TMPJson.loadPathJson(self.ConfigPath, False)
        self.CQHTTPNCC = self.New_CFG_CTL(self.TMPJson, self.ConfigPath)
        self.CQHTTP_MSC = self.MESSAGE_LIST_CTL()
        self.CQHTTP_RES_NUM = {}
        self.SIGN_SERVER_MSC = self.MESSAGE_LIST_CTL()
        self.SIGN_SERVER_RES_NUM = {}
        self.SIGN_SERVER_Lib_ConfigPath: str = os.path.join(
            os.path.join(self.base_SIGN_dir, "unidbg-fetch-qsign-1.1.9"),
            "txlib",
            self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"]["lib版本"],
            "config.json",
        )
        self.SIGN_SERVER_Running = False
        self.CQHTTP_LOGIN_STATUS = False
        self.BOT_JOIN_GAME = False
        self.INITSTATUS = False
        self.CQHTTP_API_PORT: int = get_free_port()
        if self.no_join_game_debug:
            self.on_inject()

    def if_cqhttp_in_dir(self) -> bool:
        return os.path.exists(self.base_CQHTTP_dir) and os.path.exists(
            os.path.join(
                self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行文件"],
            )
        )

    def if_sign_server_in_dir(self) -> bool:
        return os.path.exists(self.base_SIGN_dir) and os.path.exists(
            os.path.join(self.base_SIGN_dir, "unidbg-fetch-qsign-1.1.9")
        )

    def Initialize(self) -> None:
        self.game_ctrl.say_to(
            "@a",
            f'[§bToolDelta控制台§r] 插件 - §e{self.name} - v{".".join(map(str, self.version))}§r 成功被加载!',
        )
        self.Setup_Menu()
        if not self.if_cqhttp_in_dir():
            Print.print_load("CQ-HTTP目录不存在或未安装，开始尝试安装CQ-HTTP...")
            self.install_cqhttp()
        self.IF_CQHTTP_Config()
        if self.TMPJson.read(self.ConfigPath)["配置项"]["内置签名服务端"] is True:
            if not self.if_sign_server_in_dir():
                Print.print_load(
                    "sign-server目录不存在或未安装，开始尝试安装sign-server..."
                )
                self.install_sign_server()
            else:
                if not self.if_jdk_in_jdkdir():
                    if not self.use_in_sys_jdk():
                        if not self.install_jdk_17():
                            raise ValueError("安装JDK失败，请检查网络或权限！")
            self.TMPJson.loadPathJson(self.SIGN_SERVER_Lib_ConfigPath)
            self.IF_SIGN_SERVER_Config()
            if self.TMPJson.read(self.ConfigPath)["配置项"]["内置签名服务端"] is True:
                Print.print_suc(
                    "根据配置项，已启用内置签名服务端，插件将优先启动签名服务端！"
                )
                # self.Process_Run_SIGN_SERVER()
                threading.Thread(
                    target=self.Process_Run_SIGN_SERVER, name="SIGN-SERVER运行线程"
                ).start()
                self.IF_PRE_SIGN_SERVER_RUNNING(timeout=4)
                threading.Thread(
                    target=self.Handle_SIGN_SERVER_Message,
                    name="SIGN-SERVER消息处理主线程",
                ).start()
        os.system(f"chmod 777 {self.base_dir}")
        Print.print_load("正在启动 CQHTTP-事件上报服务器...")
        self.CQHTTPEHCore = self.CQHTTPEventHandleCore(self)
        threading.Thread(
            target=self.CQHTTPEHCore.Initialize, name="CQHTTP-事件上报服务端运行线程"
        ).start()
        self.WAIT_CQHTTP_EVENT_HANDLE_CORE_RUNNING()
        Print.print_suc("CQHTTP-事件上报服务端成功启动!")
        self.SET_SIGN_SERVER()
        self.SET_EVENT_HANDLE_SERVER()
        self.SET_CQHTTP_API_PORT()
        self.CQHTTPNCC.save_new_cfg()
        # self.Process_Run_CQHTTP()
        self.WAIT_SIGN_SERVER_RUNNING()
        threading.Thread(target=self.Process_Run_CQHTTP, name="CQ-HTTP运行线程").start()
        self.IF_PRE_CQHTTP_RUNNING(timeout=4)
        threading.Thread(
            target=self.Handle_CQHTTP_Message, name="CQ-HTTP消息处理主线程"
        ).start()
        self.SMTC = self.Send_Message_To_CQHTTP(self.CQHTTP_API_PORT)
        self.INITSTATUS = True

    def on_inject(self) -> None:
        self.BOT_JOIN_GAME = True
        self.Initialize()

    def if_jdk_in_jdkdir(self) -> bool:
        if os.path.exists(
            os.path.join(self.base_SIGN_dir, "JDK-bin")
        ) or os.path.exists(self.TMPJson.read(self.ConfigPath)["配置项"]["JDK位置"]):
            return True
        return False

    def if_is_jdkdir(self) -> bool:
        if not self.if_jdk_in_jdkdir():
            return False
        if os.path.exists(
            os.path.join(self.base_SIGN_dir, "JDK-bin", "java")
        ) or os.path.exists(
            os.path.join(
                self.TMPJson.read(self.ConfigPath)["配置项"]["JDK位置"], "bin", "java"
            )
        ):
            return True
        if os.path.exists(
            os.path.join(self.base_SIGN_dir, "JDK-bin", "bin", "java")
        ) or os.path.exists(
            os.path.join(
                self.TMPJson.read(self.ConfigPath)["配置项"]["JDK位置"], "bin", "java"
            )
        ):
            return True
        return False

    def use_in_sys_jdk(self) -> bool:
        if self.sys_type == "windows":
            raise Exception("该函数不支持Windows系统调用！")
        try:
            versionMsg = subprocess.check_output("java --version", shell=True).decode(
                "utf-8"
            )
            which_java = (
                subprocess.check_output("which java", shell=True).decode("utf-8")
            ).replace("\n", "")
            if (
                "not found" in versionMsg
                or "不是内部或外部命令，也不是可运行的程序或批处理文件。" in versionMsg
            ):
                return False
            if not os.path.exists("/usr/bin/java") and len(which_java) < 6:
                return False
            if "command not found" not in versionMsg:
                jdk_path = self.resolve_symlink(which_java)
                if jdk_path is None:
                    return False
                jdk_path = self.extract_path_with_bin(jdk_path)
                old = self.TMPJson.read(self.ConfigPath)
                old["配置项"]["JDK位置"] = jdk_path
                self.TMPJson.write_as_tmp(self.ConfigPath, old)
                self.reload_PathJson(self.ConfigPath)
                Print.print_suc(f"将使用系统内已存在的JDK {jdk_path}")
                return True
            return False
        except Exception:
            return False

    def extract_path_with_bin(self, input_str) -> str | None:
        bin_index = input_str.find("bin")
        if bin_index != -1:
            path_with_bin = input_str[: bin_index + 3]
            path = os.path.dirname(path_with_bin)
            return path
        else:
            return None

    def if_file_run_permissions(self, file_path) -> bool:
        if not os.path.exists(file_path):
            return False
        if os.access(file_path, os.W_OK):
            return True
        else:
            return False

    def resolve_symlink(self, path) -> str | None:
        if os.path.exists(path):
            if os.path.islink(path):
                link_target = os.readlink(path)
                if os.path.isabs(link_target):
                    return self.resolve_symlink(link_target)
                else:
                    link_dir = os.path.dirname(path)
                    resolved_target = os.path.normpath(
                        os.path.join(link_dir, link_target)
                    )
                    return self.resolve_symlink(resolved_target)
            else:
                return path
        else:
            return None

    def install_jdk_17(self) -> bool:
        try:
            if self.sys_machine == "x86_64":
                sys_machine = "x64"
            elif self.sys_machine == "amd64":
                sys_machine = "x64"
            if sys_machine not in ["aarch64", "x64"]:
                raise ValueError("暂不支持该系统架构，无法安装该架构jdk")
            if self.sys_type == "windows":
                raise ValueError("内置签名服务端暂不支持Windows系统")
            jdk17_url: str = f"https://download.oracle.com/java/17/latest/jdk-17_linux-{sys_machine}_bin.tar.gz"
            if not os.path.exists(
                os.path.join(self.base_SIGN_dir, jdk17_url.split("/")[-1])
            ):
                if not self.if_jdk_in_jdkdir():
                    if not os.path.exists(
                        os.path.join(
                            self.base_SIGN_dir, urlparse(jdk17_url).path.split("/")[-1]
                        )
                    ):
                        Print.print_war(
                            "未检测到JDK，将尝试自动安装JDK，开始安装JDK..."
                        )
                        try:
                            urlmethod.download_file_singlethreaded(
                                jdk17_url,
                                os.path.join(
                                    self.base_SIGN_dir,
                                    urlparse(jdk17_url).path.split("/")[-1],
                                ),
                            )
                        except Exception as e:
                            raise ValueError(
                                f"无法正常下载JDK压缩包文件，请自行前往[https://www.oracle.com/cn/java/technologies/downloads/#jdk17-linux]下载对应文件放置于{self.base_SIGN_dir}目录下。{e}"
                            )
            if ".zip" in jdk17_url.split("/")[-1]:
                if self.extract_archive(
                    os.path.join(self.base_SIGN_dir, jdk17_url.split("/")[-1]),
                    os.path.join(self.base_SIGN_dir, "jdk-17"),
                ):
                    os.remove(
                        os.path.join(self.base_SIGN_dir, jdk17_url.split("/")[-1])
                    )
                    old = self.TMPJson.read(self.ConfigPath)
                    old["配置项"]["JDK位置"] = os.path.join(
                        self.base_SIGN_dir, "jdk-17"
                    )
                    self.TMPJson.write_as_tmp(self.ConfigPath, old)
                    self.reload_PathJson(self.ConfigPath)
            if os.path.exists(self.TMPJson.read(self.ConfigPath)["配置项"]["JDK位置"]):
                Print.print_suc("成功安装JDK，已自动配置 JDK位置 在插件配置中！")
                return True
        except Exception as e:
            Print.print_err(
                f"安装JDK失败，您可以手动安装(使用Linux的包管理器安装后修改插件配置文件)或将插件配置文件的JDK位置指向您已安装的地址。{e}"
            )
            return False
        return True

    def install_sign_server(self) -> bool:
        try:
            os.makedirs(self.base_SIGN_dir, exist_ok=True)
            if self.sys_machine == "x86_64":
                sys_machine = "x64"
            elif self.sys_machine == "amd64":
                sys_machine = "x64"
            if sys_machine not in ["aarch64", "x64"]:
                old = self.TMPJson.read(self.ConfigPath)
                old["配置项"]["内置签名服务端"] = False
                self.TMPJson.write_as_tmp(self.ConfigPath, old)
                self.reload_PathJson(self.ConfigPath)
                raise ValueError("暂不支持该系统架构，将禁用置签名服务端！")
            if not self.if_jdk_in_jdkdir():
                if not self.use_in_sys_jdk():
                    if not self.install_jdk_17():
                        raise ValueError("安装JDK失败，请检查网络或权限！")
            if self.sys_type == "windows":
                raise ValueError("内置签名服务端暂不支持Windows系统")
            sign_server_url: str = "https://github.com/CikeyQi/unidbg-fetch-qsign-shell/releases/download/1.1.9/unidbg-fetch-qsign-1.1.9.zip"
            if not os.path.exists(
                os.path.join(self.base_SIGN_dir, sign_server_url.split("/")[-1])
            ):
                fast_url = urlmethod.test_site_latency(
                    {
                        "url": sign_server_url,
                        "mirror_url": urlmethod.format_mirror_url(sign_server_url),
                    }
                )[0]
                Print.print_load(
                    f"已确认最优下载线路 [URL: {fast_url[0]} Speed: {fast_url[1]}]，开始下载..."
                )
                try:
                    urlmethod.download_file_singlethreaded(
                        urlmethod.githubdownloadurl_to_rawurl(fast_url[0]),
                        os.path.join(
                            self.base_SIGN_dir,
                            urlparse(fast_url[0]).path.split("/")[-1],
                        ),
                    )
                except Exception as e:
                    raise ValueError(
                        f"无法正常下载sign-server服务端文件，请自行前往[https://github.com/CikeyQi/unidbg-fetch-qsign-shell/releases/tag/1.1.9]下载对应文件放置于{os.path.join(self.base_SIGN_dir, 'JDK-bin')}目录下。{e}"
                    )
            if ".zip" in sign_server_url.split("/")[-1]:
                if self.extract_archive(
                    os.path.join(self.base_SIGN_dir, sign_server_url.split("/")[-1]),
                    self.base_SIGN_dir,
                ):
                    os.remove(
                        os.path.join(self.base_SIGN_dir, sign_server_url.split("/")[-1])
                    )
            os.chmod(
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
                    "bin",
                    "unidbg-fetch-qsign",
                ),
                0o777,
            )
            if not os.path.exists(
                self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"]
            ):
                raise ValueError("签名服务端安装失败，请检查配置文件或自行安装。")
            Print.print_suc("成功安装sign-server服务端！")
        except Exception as e:
            Print.print_war(f"尝试安装sign-server服务端失败，请检查网络或权限！{e}")
            return False
        return True

    def is_port_open(self, port) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return (
                s.connect_ex(
                    (
                        self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"][
                            "host"
                        ],
                        port,
                    )
                )
                == 0
            )

    def get_sign_server_port(self) -> int:
        if not self.is_port_open(
            self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"]["端口"]
        ):
            return self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"][
                "端口"
            ]
        Print.print_war(
            f"您所指定的签名服务端运行端口[{self.TMPJson.read(self.ConfigPath)['配置项']['Sign-Server配置']['端口']}]已被占用，将为您随机一个可用端口！"
        )
        for i in range(1000, 65535):
            if not self.is_port_open(i):
                return i
        raise ValueError("没有可用端口")

    def reload_PathJson(self, CFGPath: str) -> bool:
        return (
            True
            if self.TMPJson.unloadPathJson(CFGPath)
            and self.TMPJson.loadPathJson(CFGPath, False)
            else False
        )

    def use_lib_info(self) -> bool:
        try:
            shutil.copyfile(
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
                    "txlib",
                    self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"][
                        "lib版本"
                    ],
                    "android_pad.json",
                ),
                os.path.join(self.base_CQHTTP_dir, "data", "versions", "6.json"),
            )
            shutil.copyfile(
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
                    "txlib",
                    self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"][
                        "lib版本"
                    ],
                    "android_phone.json",
                ),
                os.path.join(self.base_CQHTTP_dir, "data", "versions", "1.json"),
            )
            return True
        except Exception:
            return False

    def IF_SIGN_SERVER_Config(self) -> Any:
        if self.TMPJson.read(self.ConfigPath)["配置项"][
            "端口被占用时随机端口[全局][插件内]"
        ]:
            self.sign_server_port = self.get_sign_server_port()
        else:
            self.sign_server_port = self.TMPJson.read(self.ConfigPath)["配置项"][
                "Sign-Server配置"
            ]["端口"]
        Print.print_suc(f"签名服务端将使用端口: {self.sign_server_port}")
        if self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"] == "":
            old = self.TMPJson.read(self.ConfigPath)
            old["配置项"]["签名服务端运行目录"] = os.path.join(
                self.base_SIGN_dir, "unidbg-fetch-qsign-1.1.9"
            )
            self.TMPJson.write_as_tmp(self.ConfigPath, old)
            self.reload_PathJson(self.ConfigPath)
        if not os.path.exists(
            os.path.join(
                self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
                "txlib",
                self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"][
                    "lib版本"
                ],
            )
        ):
            raise ValueError(
                f"签名服务端配置文件异常，签名服务端不存在版本为 [{self.TMPJson.read(self.ConfigPath)['配置项']['Sign-Server配置']['lib版本']}] 的lib！"
            )
        if not os.path.exists(
            os.path.join(
                self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
                "txlib",
                self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"][
                    "lib版本"
                ],
                "config.json",
            )
        ):
            raise ValueError(
                f"签名服务端配置文件异常，签名服务端在lib版本[{self.TMPJson.read(self.ConfigPath)['配置项']['Sign-Server配置']['lib版本']}] 中未找到config.json文件！"
            )
        lib_config = self.TMPJson.read(self.SIGN_SERVER_Lib_ConfigPath)
        lib_config["server"]["host"] = self.TMPJson.read(self.ConfigPath)["配置项"][
            "Sign-Server配置"
        ]["host"]
        lib_config["server"]["port"] = self.sign_server_port
        lib_config["share_token"] = self.TMPJson.read(self.ConfigPath)["配置项"][
            "Sign-Server配置"
        ]["share_token"]
        lib_config["key"] = self.TMPJson.read(self.ConfigPath)["配置项"][
            "Sign-Server配置"
        ]["key"]
        lib_config["auto_register"] = self.TMPJson.read(self.ConfigPath)["配置项"][
            "Sign-Server配置"
        ]["auto_register"]
        self.TMPJson.write_as_tmp(self.SIGN_SERVER_Lib_ConfigPath, lib_config)
        self.reload_PathJson(self.SIGN_SERVER_Lib_ConfigPath)
        self.use_lib_info()

    def IF_CQHTTP_Config(self) -> Any:
        try:
            if self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行文件"] == "":
                old = self.TMPJson.read(self.ConfigPath)
                old["配置项"]["CQHTTP运行文件"] = os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行UUID"],
                )
                self.TMPJson.write_as_tmp(self.ConfigPath, old)
                self.reload_PathJson(self.ConfigPath)
            if (
                os.path.exists(
                    os.path.join(
                        self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                        "config.yml",
                    )
                )
                is True
                and len(
                    open(
                        os.path.join(
                            self.TMPJson.read(self.ConfigPath)["配置项"][
                                "CQHTTP运行目录"
                            ],
                            "config.yml",
                        ),
                        encoding="utf-8",
                    ).read()
                )
                >= 256
                and "# Not Initial Config\n"
                not in open(
                    os.path.join(
                        self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                        "config.yml",
                    ),
                    encoding="utf-8",
                ).read()
            ):
                return
            config_yml = open(
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                    "config.yml",
                ),
                "w+",
                encoding="utf-8",
            )
            Print.print_load("CQ-HTTP首次启动需要生成配置文件")
            config_yml.write(CQHTTP_DEF_CFG)
            config_yml.close()
            Print.print_load(
                f"请设置文件 §6{os.path.join(self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录'], 'config.yml')}§r §d的配置，修改完成后将第一行的'#Not Initial Config'删除，修改成功后将自动进行下一步！"
            )
            while True:
                if (
                    "# Not Initial Config\n"
                    not in open(
                        os.path.join(
                            self.TMPJson.read(self.ConfigPath)["配置项"][
                                "CQHTTP运行目录"
                            ],
                            "config.yml",
                        ),
                        encoding="utf-8",
                    ).read()
                ):
                    break
                time.sleep(0.25)
        except Exception as e:
            Print.print_war(
                f"写入配置到文件或检测文件头部内容时出现异常，请检查配置文件或自行修改。{e}"
            )
            raise ValueError(
                f"写入配置到文件或检测文件头部内容时出现异常，请检查配置文件或自行修改。{e}"
            )

    def install_cqhttp(self):
        try:
            os.makedirs(self.base_CQHTTP_dir, exist_ok=True)
            if self.sys_machine == "x86_64":
                sys_machine = "amd64"
            elif self.sys_machine == "aarch64":
                sys_machine = "arm64"
            else:
                sys_machine = self.sys_machine
            cqhttp_url = (
                f"https://github.com/Mrs4s/go-cqhttp/releases/download/v1.2.0/go-cqhttp_{self.sys_type}_{sys_machine}.exe"
                if self.sys_type == "windows"
                else f"https://github.com/Mrs4s/go-cqhttp/releases/download/v1.2.0/go-cqhttp_{self.sys_type}_{sys_machine}.tar.gz"
            )
            if not os.path.exists(
                os.path.join(self.base_CQHTTP_dir, cqhttp_url.split("/")[-1])
            ):
                fast_url = urlmethod.test_site_latency(
                    {
                        "url": cqhttp_url,
                        "mirror_url": urlmethod.format_mirror_url(cqhttp_url),
                    }
                )[0]
                Print.print_load(
                    f"已确认最优下载线路 [URL: {fast_url[0]} Speed: {fast_url[1]}]，开始下载..."
                )
                try:
                    urlmethod.download_file_singlethreaded(
                        urlmethod.githubdownloadurl_to_rawurl(fast_url[0]),
                        os.path.join(
                            self.base_CQHTTP_dir,
                            (
                                "go-cqhttp.exe"
                                if self.sys_type == "windows"
                                else cqhttp_url.split("/")[-1]
                            ),
                        ),
                    )
                except Exception as e:
                    raise ValueError(
                        f"无法正常下载CQ-HTTP可执行文件，请自行前往[https://github.com/Mrs4s/go-cqhttp/releases]下载对应文件放置于{self.base_CQHTTP_dir}目录下。{e}"
                    )
            if ".tar.gz" in cqhttp_url.split("/")[-1]:
                if self.extract_archive(
                    os.path.join(self.base_CQHTTP_dir, cqhttp_url.split("/")[-1]),
                    self.base_CQHTTP_dir,
                ):
                    os.remove(
                        os.path.join(self.base_CQHTTP_dir, cqhttp_url.split("/")[-1])
                    )
                    os.remove(os.path.join(self.base_CQHTTP_dir, "LICENSE"))
                    os.remove(os.path.join(self.base_CQHTTP_dir, "README.md"))
            old = self.TMPJson.read(self.ConfigPath)
            old["配置项"]["CQHTTP运行文件"] = (
                f'{old["配置项"]["CQHTTP运行UUID"]}.exe'
                if self.sys_type == "windows"
                else old["配置项"]["CQHTTP运行UUID"]
            )
            self.TMPJson.write_as_tmp(self.ConfigPath, old)
            os.rename(
                os.path.join(
                    old["配置项"]["CQHTTP运行目录"],
                    ("go-cqhttp.exe" if self.sys_type == "windows" else "go-cqhttp"),
                ),
                os.path.join(
                    old["配置项"]["CQHTTP运行目录"], old["配置项"]["CQHTTP运行文件"]
                ),
            )
            os.chmod(
                os.path.join(
                    old["配置项"]["CQHTTP运行目录"], old["配置项"]["CQHTTP运行文件"]
                ),
                0o777,
            )
            if not os.path.exists(
                os.path.join(
                    old["配置项"]["CQHTTP运行目录"], old["配置项"]["CQHTTP运行文件"]
                )
            ):
                raise ValueError("CQ-HTTP安装失败，请检查配置文件或自行安装。")
            Print.print_suc("成功安装CQ-HTTP！")
            self.reload_PathJson(self.ConfigPath)
        except Exception as e:
            Print.print_war(
                f"尝试安装CQ-HTTP失败，可寻求他人帮助或自行安装并修改配置文件: {e}"
            )
            raise ValueError(
                f"尝试安装CQ-HTTP失败，可寻求他人帮助或自行安装并修改配置文件: {e}"
            )

    def check_string_in_list(self, string: str, list: list) -> bool:
        for element in list:
            if element in string:
                return True
        return False

    def extract_archive(self, archive_path: str, extract_dir: str) -> bool:
        """解压压缩归档

        Args:
            archive_path (str): 压缩包路径
            extract_dir (str): 解压目录

        Returns:
            bool: 是否成功
        """
        try:
            if archive_path.endswith(".zip"):
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif archive_path.endswith(".tar.gz") or archive_path.endswith(".tgz"):
                with tarfile.open(archive_path, "r:gz") as tar_ref:
                    tar_ref.extractall(extract_dir)
            elif archive_path.endswith(".tar"):
                with tarfile.open(archive_path, "r") as tar_ref:
                    tar_ref.extractall(extract_dir)
            elif archive_path.endswith(".gz"):
                with gzip.open(archive_path, "rb") as gz_ref:
                    with open(
                        os.path.join(extract_dir, os.path.basename(archive_path)[:-3]),
                        "wb",
                    ) as f_out:
                        shutil.copyfileobj(gz_ref, f_out)
            else:
                return False  # 不支持的压缩格式
            return True
        except Exception as err:
            print(f"Error extracting archive: {err}")
            return False

    class New_CFG_CTL:
        def __init__(self, TMPJson: Any, ConfigPath: str) -> None:
            self.TMPJson: Any = TMPJson
            self.ConfigPath: str = ConfigPath
            self.OLD_CFG: io.TextIOWrapper
            self.NEW_CFG: io.TextIOWrapper
            self.OLD_CFG_DATA: dict
            threading.Thread(
                target=self.wait_yml_create, name="wait_yml_create"
            ).start()

        def wait_yml_create(self, timeout: int = 600) -> Any:
            run_time = 0
            while run_time <= timeout:
                if run_time > timeout:
                    raise ValueError(
                        "CQ-HTTP 配置文件生成超时，请检查配置文件是否正确生成。"
                    )
                if (
                    os.path.exists(
                        os.path.join(
                            self.TMPJson.read(self.ConfigPath)["配置项"][
                                "CQHTTP运行目录"
                            ],
                            "config.yml",
                        )
                    )
                    and len(
                        open(
                            os.path.join(
                                self.TMPJson.read(self.ConfigPath)["配置项"][
                                    "CQHTTP运行目录"
                                ],
                                "config.yml",
                            ),
                            encoding="utf-8",
                        ).read()
                    )
                    > 256
                ):
                    self.open_read_cfg()
                    return True
                run_time += 0.5
                time.sleep(0.5)

        def open_read_cfg(self) -> None:
            self.OLD_CFG: io.TextIOWrapper = open(
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                    "config.yml",
                ),
                encoding="utf-8",
            )
            self.NEW_CFG: io.TextIOWrapper = open(
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                    "TmpCFG.yml",
                ),
                "w+",
                encoding="utf-8",
            )
            self.OLD_CFG_DATA: dict = self.load_old_cfg()

        def if_open_init(self) -> None:
            while self.OLD_CFG is None or self.NEW_CFG is None:
                if not self.OLD_CFG or not self.NEW_CFG:
                    time.sleep(0.1)
                else:
                    break

        def load_old_cfg(self) -> dict:
            try:
                self.if_open_init()
                result = yaml.load(self.OLD_CFG, Loader=yaml.FullLoader)
                if isinstance(result, dict):
                    return result
                raise ValueError("CQ-HTTP配置文件读取失败！")
            except Exception as e:
                os.remove(
                    os.path.join(
                        self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                        "config.yml",
                    )
                )
                Print.print_err(
                    f"读取CQ-HTTP配置文件时出现异常，将删除配置文件，您可以在下次启动时重新配置文件！{e}"
                )
                return {}

        def set_cfg_item(self, key: str, value: Any) -> bool:
            self.if_open_init()
            try:
                self.OLD_CFG_DATA[key] = value
                return True
            except Exception:
                return False

        def get_cfg_item(self, key: str) -> Any:
            self.if_open_init()
            try:
                return self.OLD_CFG_DATA[key]
            except Exception:
                return None

        def save_new_cfg(self) -> None:
            try:
                self.if_open_init()
                yaml.dump(
                    self.OLD_CFG_DATA,
                    self.NEW_CFG,
                    default_flow_style=False,
                    sort_keys=False,
                    encoding="utf-8",
                )
                self.close_cfg()
            except Exception as e:
                Print.print_err(f"保存CQ-HTTP配置文件时出现异常！{e}")
                return

        def add_cfg_item(self, key1: str, value: Any, key2: Any | None = None) -> bool:
            try:
                if key2 is not None:
                    if isinstance(self.OLD_CFG_DATA[key1][key2], list):
                        self.OLD_CFG_DATA[key1][key2].append(value)
                    elif isinstance(self.OLD_CFG_DATA[key1][key2], dict):
                        self.OLD_CFG_DATA[key1][key2].update(value)
                    else:
                        self.OLD_CFG_DATA[key1][key2] = value
                    return True
                else:
                    if isinstance(self.OLD_CFG_DATA[key1], list):
                        self.OLD_CFG_DATA[key1].append(value)
                    elif isinstance(self.OLD_CFG_DATA[key1], dict):
                        self.OLD_CFG_DATA[key1].update(value)
                    else:
                        self.OLD_CFG_DATA[key1] = value
                    return True
            except Exception as e:
                raise ValueError(f"向CQ-HTTP配置文件添加值时出现异常！{e}")

        def get_all_cfg(self) -> dict:
            return self.OLD_CFG_DATA

        def set_all_cfg(self, data: dict) -> dict:
            self.OLD_CFG_DATA = data
            return self.OLD_CFG_DATA

        def close_cfg(self) -> None:
            self.OLD_CFG.close()
            self.NEW_CFG.close()

    def SET_SIGN_SERVER(self) -> list[str] | None:
        """获取可用签名服务器

        Returns:
            list: 可用签名服务器数据 [{"URL": "https://qsign.wuliya.icu/8978/sign", "key": "wuliya"}, {"URL": "https://qsign.wuliya.icu/8988/sign", "key": "wuliya"}, {"URL": "https://qsign.wuliya.icu/8996/sign", "key": "wuliya"}, {"URL": "http://qsign.angryrabbit.cn/8978", "key": "114514"}, {"URL": "http://qsign.pippi.top", "key": "yui"}, {"URL": "http://1.QSign.icu", "key": "XxxX"}, {"URL": "http://2.QSign.icu", "key": "XxxX"}, {"URL": "http://3.QSign.icu", "key": "XxxX"}, {"URL": "http://4.QSign.icu", "key": "XxxX"}]
        """
        ON_SERVICE_SIGN_SERVER: list = []
        if not self.TMPJson.read(self.ConfigPath)["配置项"]["内置签名服务端"]:
            for SERVER in CQHTTP_SIGN_SERVER_LIST:
                try:
                    res = requests.get(SERVER["URL"], timeout=4)
                    if json.loads(res.text)["code"] == 200:
                        ON_SERVICE_SIGN_SERVER.append(SERVER)
                except Exception:
                    continue

            self.CQHTTPNCC.add_cfg_item(
                "account", "sign-servers", ON_SERVICE_SIGN_SERVER
            )
            return ON_SERVICE_SIGN_SERVER
        else:
            self.CQHTTPNCC.add_cfg_item(
                key1="account",
                key2="sign-servers",
                value={
                    "url": f"http://127.0.0.1:{self.TMPJson.read(self.ConfigPath)['配置项']['Sign-Server配置']['端口']}",
                    "key": self.TMPJson.read(self.ConfigPath)["配置项"][
                        "Sign-Server配置"
                    ]["key"],
                    "authorization": "-",
                },
            )
            return None

    def SET_EVENT_HANDLE_SERVER(self) -> bool:
        try:
            self.old_cfg: dict = self.CQHTTPNCC.get_all_cfg()
            self.old_cfg["servers"][0]["http"]["post"][0]["url"] = (
                f"http://{self.CQHTTPEHCore.CoreCFG['host']}:{self.CQHTTPEHCore.CoreCFG['port']}/"
            )
            self.CQHTTPNCC.set_all_cfg(self.old_cfg)
            return True
        except Exception:
            return False

    def SET_CQHTTP_API_PORT(self) -> bool:
        try:
            self.old_cfg: dict = self.CQHTTPNCC.get_all_cfg()
            self.old_cfg["servers"][0]["http"]["address"] = (
                f"0.0.0.0:{self.CQHTTP_API_PORT}"
            )
            self.CQHTTPNCC.set_all_cfg(self.old_cfg)
            return True
        except Exception:
            return False

    def Setup_Menu(self) -> None:
        self.frame.add_console_cmd_trigger(
            ["GS", "群服"],
            "[参数]/[参数] [参数]",
            "群服互通 控制台命令",
            self.Handle_Menu_Cmd,
        )
        Print.print_suc("群服互通 控制台菜单 已加载！")

    def Handle_Menu_Cmd(self, args: list[str]) -> None:
        try:
            if len(args) >= 1:
                match args[0]:
                    case "help":
                        Print.print_inf(
                            "§a群服互通 帮助菜单:§r\nhelp - 显示此帮助菜单\ninclude [文件路径]/[文件名] - 导入bdx文件内容到租赁服"
                        )
                    case "输入":
                        if len(args) <= 1:
                            Print.print_err(
                                "参数长度错误，请提供正确的参数，使用(群服 help)获得帮助。"
                            )
                            return
                        if not self.cqhttp_proc:
                            Print.print_err(
                                "CQ-HTTP 未启动，请先启动CQ-HTTP再使用该功能!"
                            )
                        if self.cqhttp_proc.poll() is not None:
                            Print.print_err(
                                "CQ-HTTP 未启动，请先启动CQ-HTTP再使用该功能!"
                            )
                        if len(args) == 2:
                            try:
                                if self.cqhttp_proc.stdin is None:
                                    raise ValueError("进程的标准输入不可用")
                                self.cqhttp_proc.stdin.write(args[1].encode("utf-8"))
                                self.cqhttp_proc.stdin.write(b"\n")
                                self.cqhttp_proc.stdin.flush()
                            except subprocess.TimeoutExpired as e:
                                Print.print_err(f"输入超时!{e}")
                    case "停止运行签名服务器":
                        if not self.sign_server_proc:
                            Print.print_err(
                                "SIGN-SERVER 未启动，请先启动SIGN-SERVER再使用该功能!"
                            )
                        if self.sign_server_proc.poll() is not None:
                            Print.print_err(
                                "SIGN-SERVER 未启动，请先启动SIGN-SERVER再使用该功能!"
                            )

                    case "删除插件配置文件":
                        if os.path.exists(self.ConfigPath):
                            os.remove(self.ConfigPath)
                            if not os.path.exists(self.ConfigPath):
                                Print.print_suc(
                                    "插件配置文件已成功删除，您需要重启ToolDelta重新生成配置文件，否则插件运行将会出现问题！"
                                )
                                safe_jump(out_task=True)
                            else:
                                Print.print_err("插件配置文件未被正确的被删除")
                        else:
                            Print.print_err("插件配置文件不存在，无法删除！")
                    case _:
                        Print.print_err(
                            "参数错误，请提供正确的参数，使用(群服 help)获得帮助。"
                        )
            else:
                Print.print_err("参数错误，请提供正确的参数，使用(群服 help)获得帮助。")
        except FileNotFoundError or ValueError as e:
            Print.print_err(str(e))

    def Process_Run_SIGN_SERVER(self):
        env = os.environ.copy()
        env["JAVA_HOME"] = self.TMPJson.read(self.ConfigPath)["配置项"]["JDK位置"]
        if not self.if_file_run_permissions(
            os.path.join(
                self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
                "bin",
                "unidbg-fetch-qsign",
            )
        ):
            os.chmod(
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
                    "bin",
                    "unidbg-fetch-qsign",
                ),
                0o777,
            )
        self.sign_server_proc = subprocess.Popen(
            [
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
                    "bin",
                    "unidbg-fetch-qsign",
                ),
                f'--basePath={os.path.join(self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"], "txlib", self.TMPJson.read(self.ConfigPath)["配置项"]["Sign-Server配置"]["lib版本"])}',
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.TMPJson.read(self.ConfigPath)["配置项"]["签名服务端运行目录"],
            env=env,
        )

    def Process_Run_CQHTTP(self):
        if not self.if_file_run_permissions(
            os.path.join(
                self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行文件"],
            )
        ):
            os.chmod(
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行文件"],
                ),
                0o777,
            )
        self.cqhttp_proc = subprocess.Popen(
            [
                os.path.join(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
                    self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行文件"],
                ),
                "-c",
                "TmpCFG.yml",
                "-faststart",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP运行目录"],
        )

    @plugins.add_packet_listener([9])
    def listenner(self, packet: dict):
        self.WAIT_FRAME_INIT_STATUS()
        self.enabled_groups: list = [
            value
            for d in self.TMPJson.read(self.ConfigPath)["配置项"]["群服互通相关配置"][
                "启用群列表"
            ]
            for value in d.values()
        ]
        match packet["TextType"]:
            case 1:
                SourceName: str = packet["SourceName"]
                Message: str = packet["Message"]
                for gid in self.enabled_groups:
                    self.SMTC.send_group_message(
                        int(gid), f"[群服互通] [{SourceName}]: {Message}"
                    )
        return False

    class MESSAGE_LIST_CTL:
        def __init__(self):
            self.MESSAGE_LIST: list = []

        def append_msg(self, msg: str):
            if len(self.MESSAGE_LIST) >= 1000:
                self.MESSAGE_LIST.clear()
            self.MESSAGE_LIST.append(msg)

        def get_err_msg(self, llen=5) -> list:
            return (
                self.MESSAGE_LIST[-llen:]
                if len(self.MESSAGE_LIST) >= llen
                else self.MESSAGE_LIST
            )

        def clear_msg(self):
            self.MESSAGE_LIST.clear()

        def get_msg_len(self):
            return len(self.MESSAGE_LIST)

        def remove_msg(self, index: int):
            if index < len(self.MESSAGE_LIST):
                self.MESSAGE_LIST.pop(index)

    def Handle_SIGN_SERVER_Message(self) -> Any:
        def if_sign_server_normal(interval: int = 60) -> None:
            while True:
                if not self.SIGN_SERVER_Running:
                    time.sleep(5)
                    continue
                try:
                    rep = requests.get(
                        f"http://{self.TMPJson.read(self.ConfigPath)['配置项']['Sign-Server配置']['host']}:{self.TMPJson.read(self.ConfigPath)['配置项']['Sign-Server配置']['端口']}",
                        timeout=5,
                    )
                    if not rep.status_code == 200:
                        Print.print_war(
                            '签名服务器无响应，将根据配置项 "当签名服务端无响应时自动重启": True自动重启签名服务器'
                        )
                        self.sign_server_proc.kill()
                except Exception:
                    Print.print_war(
                        '签名服务器无响应，将根据配置项 "当签名服务端无响应时自动重启": True自动重启签名服务器'
                    )
                    self.sign_server_proc.kill()
                if (
                    not self.SIGN_SERVER_RES_NUM[
                        time.strftime("%Y-%m-%d-%H", time.localtime())
                    ]
                    <= self.TMPJson.read(self.ConfigPath)["配置项"][
                        "SIGN-SERVER自动重启最大限次"
                    ]
                ):
                    Print.print_war("SIGN-SERVER 在短时间内多次重启，将停止自动重启")
                    return
                Print.print_war(
                    f"SIGN-SERVER 进程已退出，将在 {self.TMPJson.read(self.ConfigPath)['配置项']['自动重启等待时间[S]']} 秒后尝试重启..."
                )
                time.sleep(
                    self.TMPJson.read(self.ConfigPath)["配置项"]["自动重启等待时间[S]"]
                )
                self.Process_Run_SIGN_SERVER()
                self.IF_PRE_SIGN_SERVER_RUNNING(timeout=2)
                self.SIGN_SERVER_MSC.clear_msg()
                Builtins.createThread(
                    SIGN_SERVER_Handle_Message_Fuc, usage="SIGN-SERVER消息处理"
                )
                time.sleep(interval)

        def SIGN_SERVER_Handle_Message_Fuc():
            self.SIGN_SERVER_RES_NUM.setdefault(
                time.strftime("%Y-%m-%d-%H", time.localtime()), 0
            )
            self.SIGN_SERVER_RES_NUM[
                time.strftime("%Y-%m-%d-%H", time.localtime())
            ] += 1
            OUTMSG: bool = self.TMPJson.read(self.ConfigPath)["配置项"][
                "输出签名服务器输出[可能导致刷屏]"
            ]
            if self.sign_server_proc is None or self.sign_server_proc.stdout is None:
                if not self.TMPJson.read(self.ConfigPath)["配置项"][
                    "SIGN-SERVER自动重启"
                ]:
                    raise ValueError("SIGN-SERVER 进程未启动")
            while True:
                try:
                    if self.sign_server_proc.stdout is None:
                        raise ValueError("CQHTTP标准输出不可用")
                    rec_msg = (
                        self.sign_server_proc.stdout.readline()
                        .decode("utf-8")
                        .strip("\n")
                    )
                except ValueError as e:
                    self.SIGN_SERVER_Running = False
                    raise ValueError(
                        f"SIGN_SERVER 进程已退出，最后得到的消息为：{self.SIGN_SERVER_MSC.get_err_msg()} {e}"
                    )
                self.SIGN_SERVER_MSC.append_msg(rec_msg)
                if self.sign_server_proc.poll() is not None:
                    raise ValueError(
                        f"SIGN_SERVER 进程已退出，最后得到的消息为：{self.SIGN_SERVER_MSC.get_err_msg()}"
                    )
                match rec_msg:
                    case _:
                        if "[main] DEBUG" in rec_msg:
                            continue
                        if "INFO ktor.application - Responding" in rec_msg:
                            self.SIGN_SERVER_Running = True
                            Print.print_suc(f"§d[SIGN-SERVER]§r §a{rec_msg}§r")
                            continue
                        if not OUTMSG:
                            continue
                        if len(rec_msg) <= 2:
                            continue
                        Print.print_inf(f"§d[SIGN-SERVER]§r {rec_msg}")

        Builtins.createThread(
            SIGN_SERVER_Handle_Message_Fuc, usage="SIGN-SERVER消息处理"
        )
        # if self.TMPJson.read(self.ConfigPath)["配置项"]["当签名服务端无响应时自动重启"]:
        #     Builtins.createThread(if_sign_server_normal, usage="签名服务器端状态检测")
        if self.TMPJson.read(self.ConfigPath)["配置项"]["SIGN-SERVER自动重启"]:
            Print.print_suc(
                "将遵循配置项 'SIGN-SERVER自动重启': True 将在SIGN_SERVER进程退出时自动重启!"
            )
            while True:
                if (
                    self.sign_server_proc is None
                    or self.sign_server_proc.poll() is not None
                    and self.TMPJson.read(self.ConfigPath)["配置项"][
                        "SIGN-SERVER自动重启"
                    ]
                ):
                    if (
                        not self.SIGN_SERVER_RES_NUM[
                            time.strftime("%Y-%m-%d-%H", time.localtime())
                        ]
                        <= self.TMPJson.read(self.ConfigPath)["配置项"][
                            "SIGN-SERVER自动重启最大限次"
                        ]
                    ):
                        Print.print_war(
                            "SIGN-SERVER 在短时间内多次重启，将停止自动重启"
                        )
                        return
                    Print.print_war(
                        f"SIGN-SERVER 进程已退出，将在 {self.TMPJson.read(self.ConfigPath)['配置项']['自动重启等待时间[S]']} 秒后尝试重启..."
                    )
                    time.sleep(
                        self.TMPJson.read(self.ConfigPath)["配置项"][
                            "自动重启等待时间[S]"
                        ]
                    )
                    self.Process_Run_SIGN_SERVER()
                    self.IF_PRE_SIGN_SERVER_RUNNING(timeout=2)
                    self.SIGN_SERVER_MSC.clear_msg()
                    Builtins.createThread(
                        SIGN_SERVER_Handle_Message_Fuc, usage="SIGN-SERVER消息处理"
                    )
                time.sleep(5)

    def Handle_CQHTTP_Message(self) -> Any:
        def CQHTTP_Handle_Message_Fuc():
            self.CQHTTP_RES_NUM.setdefault(
                time.strftime("%Y-%m-%d-%H", time.localtime()), 0
            )
            self.CQHTTP_RES_NUM[time.strftime("%Y-%m-%d-%H", time.localtime())] += 1
            if self.cqhttp_proc is None or self.cqhttp_proc.stdout is None:
                raise ValueError("CQ-HTTP 进程未启动")
            enabled_groups: list[str] = self.TMPJson.read(self.ConfigPath)["配置项"][
                "群服互通相关配置"
            ]["启用群列表"]
            while True:
                try:
                    rec_msg = (
                        self.cqhttp_proc.stdout.readline().decode("utf-8").strip("\n")
                    )
                except ValueError as e:
                    self.CQHTTP_LOGIN_STATUS = False
                    if not self.TMPJson.read(self.ConfigPath)["配置项"][
                        "CQHTTP自动重启"
                    ]:
                        raise ValueError(
                            f"CQ-HTTP 进程已退出，最后得到的消息为：{self.CQHTTP_MSC.get_err_msg()} {e}"
                        )
                self.CQHTTP_MSC.append_msg(rec_msg)
                if self.cqhttp_proc.poll() is not None:
                    raise ValueError(
                        f"CQ-HTTP 进程已退出，最后得到的消息为：{self.CQHTTP_MSC.get_err_msg()}"
                    )
                match rec_msg:
                    # case '请输入你需要的编号(0-9)，可输入多个，同一编号也可输入多个(如: 233)':
                    #     Print.print_inf(f"§d[CQ-HTTP]§r {rec_msg}")
                    #     self.cqhttp_proc.stdin.write(b"0")
                    case _:
                        if (
                            not self.TMPJson.read(self.ConfigPath)["配置项"][
                                "输出CQHTTP输出[可能导致刷屏][如果关闭将会屏蔽CQHTTP成功登陆账号后的消息]"
                            ]
                            and self.CQHTTP_LOGIN_STATUS
                        ):
                            continue
                        if self.TMPJson.read(self.ConfigPath)["配置项"][
                            "仅输出被启用的群消息"
                        ]:
                            if "收到来自频道" in rec_msg or "收到群" in rec_msg:
                                if not self.check_string_in_list(
                                    rec_msg, enabled_groups
                                ):
                                    continue
                        if "检查更新完成. 当前已运行最新版本." in rec_msg:
                            self.CQHTTP_LOGIN_STATUS = True
                        Print.print_inf(f"§d[CQ-HTTP]§r {rec_msg}")
                # if "[INFO]: 按 Enter 继续...." in rec_msg:
                #     self.cqhttp_proc.stdin.write(b"\n")
                #     # self.cqhttp_proc.communicate(timeout=1)
                # if "请输入(1 - 2)：" in rec_msg:
                #     self.cqhttp_proc.stdin.write(b"1\n")
                #     self.cqhttp_proc.communicate(timeout=1)

        Builtins.createThread(CQHTTP_Handle_Message_Fuc, usage="CQ-HTTP消息处理")
        if self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP自动重启"]:
            Print.print_suc(
                "将遵循配置项 'CQHTTP自动重启': True 将在CQHTTP进程退出时自动重启!"
            )
            while True:
                if (
                    self.cqhttp_proc is None
                    or self.cqhttp_proc.poll() is not None
                    and self.TMPJson.read(self.ConfigPath)["配置项"]["CQHTTP自动重启"]
                ):
                    try:
                        if (
                            not self.CQHTTP_RES_NUM[
                                time.strftime("%Y-%m-%d-%H", time.localtime())
                            ]
                            <= self.TMPJson.read(self.ConfigPath)["配置项"][
                                "CQHTTP自动重启最大限次"
                            ]
                        ):
                            Print.print_war(
                                "CQ-HTTP 在短时间内多次重启，将停止自动重启"
                            )
                            return
                    except Exception:
                        pass
                    Print.print_war(
                        f"CQ-HTTP 进程已退出，将在 {self.TMPJson.read(self.ConfigPath)['配置项']['自动重启等待时间[S]']} 秒后尝试重启..."
                    )
                    time.sleep(
                        self.TMPJson.read(self.ConfigPath)["配置项"][
                            "自动重启等待时间[S]"
                        ]
                    )
                    self.Process_Run_CQHTTP()
                    self.IF_PRE_CQHTTP_RUNNING(timeout=2)
                    self.CQHTTP_MSC.clear_msg()
                    Builtins.createThread(
                        CQHTTP_Handle_Message_Fuc, usage="CQ-HTTP消息处理"
                    )
                time.sleep(5)

    def IF_PRE_CQHTTP_RUNNING(self, timeout: int = 10) -> None:
        run_time = 0
        while run_time <= timeout:
            if timeout > timeout:
                raise ValueError(
                    f"CQ-HTTP 启动超时，请自行寻求帮助 启动参数 {os.path.join(self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录'], self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行文件'])} -h TmpCFG.yml 工作目录 {self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录']}"
                )
            try:
                if self.cqhttp_proc.poll() is None:
                    return
            except AttributeError:
                pass
            run_time += 0.5
            time.sleep(0.5)

    def IF_PRE_SIGN_SERVER_RUNNING(self, timeout: int = 10) -> None:
        run_time = 0
        while run_time <= timeout:
            if timeout > timeout:
                raise ValueError(
                    f"SIGN-SERVER 启动超时，请自行寻求帮助 启动参数 {os.path.join(self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录'], self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行文件'])} -h TmpCFG.yml 工作目录 {self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录']}"
                )
            try:
                if self.sign_server_proc.poll() is None:
                    return
            except AttributeError:
                pass
            run_time += 0.5
            time.sleep(0.5)

    def WAIT_SIGN_SERVER_RUNNING(self, timeout: int = 40) -> None:
        run_time = 0
        while run_time <= timeout:
            if timeout > timeout:
                raise ValueError(
                    f"SIGN-SERVER 启动超时，请自行寻求帮助 启动参数 {os.path.join(self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录'], self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行文件'])} -h TmpCFG.yml 工作目录 {self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录']}"
                )
            try:
                if self.SIGN_SERVER_Running is True:
                    return
            except AttributeError:
                pass
            run_time += 0.5
            time.sleep(0.5)

    def WAIT_FRAME_INIT_STATUS(self, timeout: int = 120) -> None:
        run_time = 0
        while run_time <= timeout:
            if timeout > timeout:
                raise ValueError("群服互通初始化超时，请自行寻求帮助!")
            try:
                if self.INITSTATUS is True:
                    return
            except AttributeError:
                pass
            run_time += 0.5
            time.sleep(0.5)

    def WAIT_CQHTTP_EVENT_HANDLE_CORE_RUNNING(self, timeout: int = 40) -> None:
        run_time = 0
        while run_time <= timeout:
            if timeout > timeout:
                raise ValueError(
                    f"SIGN-SERVER 启动超时，请自行寻求帮助 启动参数 {os.path.join(self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录'], self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行文件'])} -h TmpCFG.yml 工作目录 {self.TMPJson.read(self.ConfigPath)['配置项']['CQHTTP运行目录']}"
                )
            try:
                if (
                    requests.post(
                        f"http://{self.CQHTTPEHCore.CoreCFG['host']}:{self.CQHTTPEHCore.CoreCFG['port']}/api/status",
                        timeout=4,
                    ).status_code
                    == 200
                ):
                    return
            except AttributeError:
                pass
            except Exception:
                pass
            run_time += 0.5
            time.sleep(0.5)

    def get_keys_by_value_in_list(self, list_of_dicts, value) -> str:
        matching_keys = []
        for d in list_of_dicts:
            for key, val in d.items():
                if val == value:
                    matching_keys.append(key)
        if len(matching_keys) == 0:
            return "None"
        return matching_keys[0]

    class CQHTTPEventHandleCore:
        CoreVersion: tuple = (0, 0, 1)

        def __init__(self, PluginFrame: "GroupServerInterworking") -> None:
            self.PFEnv = PluginFrame
            self.CoreCFG: dict = {
                "host": self.PFEnv.TMPJson.read(self.PFEnv.ConfigPath)["配置项"][
                    "CQHTTP事件处理服务端配置"
                ]["host"],
                "port": self.get_port(),
            }
            self.ApiApp: flask.Flask = flask.Flask(
                f"CQHTTPEventHandleCore - v{'.'.join(map(str, self.CoreVersion))}"
            )
            log = logging.getLogger("werkzeug")
            log.setLevel(logging.ERROR)
            self.enabled_groups: list = [
                value
                for d in self.PFEnv.TMPJson.read(self.PFEnv.ConfigPath)["配置项"][
                    "群服互通相关配置"
                ]["启用群列表"]
                for value in d.values()
            ]

        def Initialize(self) -> Any:
            self.SetupCoreRoute()
            self.RunCore()
            # self.Send_Message_To_CQHTTP

        def SetupCoreRoute(self) -> Any:
            @self.ApiApp.route("/", methods=["POST", "GET"])
            def MainHandle():
                if flask.request.method == "POST":
                    data = flask.request.get_json()
                    if data.get("message_type") == "private":
                        uid = str(data.get("sender").get("user_id"))
                        message = data.get("raw_message")
                        nickname = data.get("sender").get("nickname")
                        Print.print_inf(
                            f"收到来自 {nickname}({uid}) 的私聊消息: {message}"
                        )
                    if data.get("message_type") == "group":
                        gid = str(data.get("group_id"))
                        uid = str(data.get("sender").get("user_id"))
                        nickname = data.get("sender").get("nickname")
                        message = data.get("message")
                        if self.PFEnv.TMPJson.read(self.PFEnv.ConfigPath)["配置项"][
                            "仅输出被启用的群消息"
                        ]:
                            if gid in self.enabled_groups:
                                Print.print_inf(
                                    f"收到来自群聊 {gid} 中 {uid}({nickname}) 的消息: {message}"
                                )
                        else:
                            Print.print_inf(
                                f"收到来自群聊 {gid} 中 {uid}({nickname}) 的消息: {message}"
                            )
                        if gid in self.enabled_groups:
                            if self.PFEnv.BOT_JOIN_GAME:
                                self.PFEnv.game_ctrl.say_to(
                                    "@a",
                                    "[§b群服互通§r][§b来自群("
                                    + self.PFEnv.get_keys_by_value_in_list(
                                        self.PFEnv.TMPJson.read(self.PFEnv.ConfigPath)[
                                            "配置项"
                                        ]["群服互通相关配置"]["启用群列表"],
                                        gid,
                                    )
                                    + ") 的消息§r] §3"
                                    + message
                                    + "§r",
                                )
                elif flask.request.method == "GET":
                    return CQHTTP_EVENT_HANDLE_MSG_PAG.replace(
                        "MSG", "The CQHTTP event reporting server is running properly."
                    ), 200
                return CQHTTP_EVENT_HANDLE_MSG_PAG.replace(
                    "MSG",
                    "The CQHTTP event escalation server processes your form content.",
                ), 200

            @self.ApiApp.route("/api/status", methods=["POST", "GET"])
            def ReturnCoreStauts():
                return CQHTTP_EVENT_HANDLE_MSG_PAG.replace("MSG", "Status 200."), 200

            @self.ApiApp.errorhandler(404)
            def page_not_found(e):
                return CQHTTP_EVENT_HANDLE_MSG_PAG.replace(
                    "MSG", f"You have accessed an API that does not exist.Error: {e}"
                ), 404

            @self.ApiApp.errorhandler(500)
            def server_error_found(e):
                return CQHTTP_EVENT_HANDLE_MSG_PAG.replace(
                    "MSG",
                    f"Server exception, please contact the developer to fix!.Error: {e}",
                ), 500

            @self.ApiApp.errorhandler(Exception)
            def page_error_found(e):
                return CQHTTP_EVENT_HANDLE_MSG_PAG.replace(
                    "MSG",
                    f"Server exception, please contact the developer to fix!.Error: {e}",
                ), 500

        def RunCore(self) -> None:
            self.ApiApp.run(host=self.CoreCFG["host"], port=self.CoreCFG["port"])

        def get_port(self) -> int:
            if not self.PFEnv.is_port_open(
                self.PFEnv.TMPJson.read(self.PFEnv.ConfigPath)["配置项"][
                    "CQHTTP事件处理服务端配置"
                ]["端口"]
            ):
                return self.PFEnv.TMPJson.read(self.PFEnv.ConfigPath)["配置项"][
                    "CQHTTP事件处理服务端配置"
                ]["端口"]
            Print.print_war(
                f"您所指定的CQHTTP-事件上报服务端运行端口[{self.PFEnv.TMPJson.read(self.PFEnv.ConfigPath)['配置项']['CQHTTP事件处理服务端配置']['端口']}]已被占用，将为您随机一个可用端口！"
            )
            for i in range(5000, 65535):
                if not self.PFEnv.is_port_open(i):
                    return i
            raise Exception("所有端口都不可用")

    class Send_Message_To_CQHTTP:
        def __init__(self, port: int = 5700) -> None:
            self.CQHTTP_API_URL: str = f"http://127.0.0.1:{port}"

        def send_group_message(
            self, group_id: int, message: str, auto_escape: bool = True
        ) -> None:
            requests.post(
                f"{self.CQHTTP_API_URL}/send_msg",
                params={
                    "message_type": "group",
                    "group_id": group_id,
                    "message": message,
                    "auto_escape": auto_escape,
                },
            )
