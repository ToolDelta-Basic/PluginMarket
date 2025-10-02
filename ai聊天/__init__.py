from tooldelta import fmts, plugin_entry, Plugin, Player, cfg, utils
import requests
import json


class NewPlugin(Plugin):
    name = "ai聊天"
    author = "机入"
    version = (0, 0, 3)

    def __init__(self, frame):
        super().__init__(frame)
        # self.data 负责存储每个玩家的对话内容
        self.data = {}
        core = {
            "模型url": "https://api.deepseek.com/chat/completions",
            "密钥": "",
            "回复前缀": "§l[§aai聊天§f]",
        }
        cores = {"模型url": str, "密钥": str, "回复前缀": str}
        config, cfg_version = cfg.get_plugin_config_and_version(
            self.name, cores, core, self.version
        )
        # 获取一些配置文件的信息
        self.apikey = config["密钥"]
        self.url = config["模型url"]
        self.qz = config["回复前缀"]

        self.ListenActive(self.service)

    # 前置 添加菜单信息
    def service(self):
        chatbar = self.GetPluginAPI("聊天栏菜单")
        chatbar.add_new_trigger(
            ["ai", "deepseek"],
            [("内容", str, None)],
            "接入deepseek大模型进行聊天",
            self.deepseek,
            op_only=True,
        )

    @utils.thread_func("ai聊天主线程")
    def deepseek(self, player: Player, args: tuple):
        message = args[0]
        fmts.print_inf(message)
        # 请求头前缀
        if not self.data.get(player.name):
            player.show(
                "[§ealert§f]§l§c No dialog data found. This is just a reminder. Don't panic."
            )
            self.data[player.name] = []

        message_data = self.data[player.name]
        message_data.append({"role": "user", "content": message})
        player.show(f"{self.qz} 正在等待接口响应...")
        data, status = self.deepseek_request(self.data[player.name])

        # 函数返回成功增加对话数据
        if status:
            print(message)
            body = json.loads(data)

            message_body = body["choices"][0]["message"]
            # 添加ai回复消息
            message_data.append(body["choices"][0]["message"])
            print(message_body)
            player.show(self.qz + " " + message_body["content"])
            return
        player.show(f"§l[§cERROR§f] §e{data}")

    # deepseek 服务器状态码解析
    def code(self, zt: int):
        status_code = {
            400: "原因：请求体格式错误",
            401: "原因：API key 错误，认证失败",
            402: "原因：账号余额不足",
            422: "原因: 请求体参数错误",
            429: "原因：请求速率（TPM 或 RPM）达到上限",
            500: "原因：服务器内部故障",
            503: "原因：服务器负载过高",
        }
        return status_code.get(zt)

    # deepseek请求
    def deepseek_request(self, data):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.apikey}",
        }

        data = {"model": "deepseek-chat", "messages": data, "stream": False}

        try:
            request = requests.post(self.url, headers=headers, data=json.dumps(data))
            ztm = self.code(request.status_code)
            # 请求成功输出内容
            if ztm is None:
                return request.text, True

            # code函数返回内容
            return ztm, False
        except requests.RequestException as e:
            return f"网络异常：{e}", False


entry = plugin_entry(NewPlugin)
