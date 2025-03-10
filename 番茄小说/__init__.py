from tooldelta import (
    Plugin,
    Config,
    game_utils,
    Utils,
    Chat,
    Player,
    FrameExit,
    plugin_entry,
)

import TomatoNovelAPI as fqapi
import time


class NewPlugin(Plugin):
    name = "番茄小说"
    author = "小虫虫"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        CONFIG_STD = {"番茄小说Cookie": str}
        CONFIG_DEFAULT = {
            "番茄小说Cookie": "请填入从番茄小说官网抓去到的Cookie。不填写则用户相关内容不可用。"
        }
        cfg, cfg_version = Config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.fqcookie = cfg["番茄小说Cookie"]
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)
        self.ListenFrameExit(self.on_frame_exit)

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")

    def on_inject(self):
        self.chatbar.add_trigger(
            ["番茄小说", "fqnovel"], None, "从番茄小说网拉取小说", self.when_fqnovel_on
        )

    def when_fqnovel_on(self, playername: str, args):
        self.game_ctrl.say_to(playername, "§6请输入书名: ")
        books_name = game_utils.waitMsg(playername)
        books_list = fqapi.search_books(books_name, 0)
        books_info = []
        books_id = []
        for book_index, book_info in enumerate(books_list):
            book_id = book_info["book_id"]
            book_name = book_info["book_name"]
            book_author = book_info["author"]
            output_book_info = (
                str(book_index) + ". " + book_name + " (" + book_author + "/著)"
            )
            books_info.append(output_book_info)
            books_id.append(book_id)
        self.game_ctrl.say_to(playername, "§6搜索到的书本列表: ")
        for book_info in books_info:
            self.game_ctrl.say_to(playername, "  " + book_info)
        self.game_ctrl.say_to(playername, "§6请输入序号以选择: ")
        book_no = game_utils.waitMsg(playername)
        book_no = Utils.try_int(book_no)
        if book_no == None:
            self.game_ctrl.say_to(playername, "§c无效输入")
            return
        book_id = books_id[book_no]
        book_info = fqapi.book_id_inquire(book_id)
        title_list = book_info["title_list"]
        item_id_list = book_info["item_id_list"]
        self.game_ctrl.say_to(playername, f"§6共找到了{str(len(item_id_list))}个结果。")
        while True:
            self.game_ctrl.say_to(
                playername, "§6请输入你需要看的章节号: \n(输入§e退出§6以退出)"
            )
            resp = game_utils.waitMsg(playername)
            if resp == "退出":
                break
            elif resp.isdigit():
                resp = int(resp)
                if resp > 0:
                    item_id = item_id_list[resp - 1]
                    title = title_list[resp - 1]
                    article = fqapi.get_content(title, item_id)
                    article = article.split("\n")
                    for paragraph in article:
                        self.game_ctrl.say_to(playername, paragraph)
                        time.sleep(0.1)
                else:
                    self.game_ctrl.say_to(playername, "§c无效输入")
            else:
                self.game_ctrl.say_to(playername, "§c无效输入")

    def on_player_join(self, player: Player):
        playername = player.name
        pass

    def on_player_leave(self, player: Player):
        playername = player.name
        pass

    def on_player_message(self, chat: Chat):
        playername = chat.player.name
        msg = chat.msg

        pass

    def on_frame_exit(self, evt: FrameExit):
        status_code = evt.signal
        reason = evt.reason

        self.print(f"系统已退出 状态码={status_code} 原因={reason}")


entry = plugin_entry(NewPlugin)
