from tooldelta import (
    Plugin,
    cfg as config,
    utils,
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
        cfg, cfg_version = config.get_plugin_config_and_version(
            self.name, CONFIG_STD, CONFIG_DEFAULT, self.version
        )
        self.fqcookie = cfg["番茄小说Cookie"]
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_inject)
        self.ListenFrameExit(self.on_frame_exit)

    def on_def(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单")

    def on_inject(self):
        self.chatbar.add_new_trigger(
            ["番茄小说", "fqnovel"], [], "从番茄小说网拉取小说", self.when_fqnovel_on
        )

    def when_fqnovel_on(self, player: Player, args):
        books_name = player.input("§6请输入书名：")
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
        player.show("§6搜索到的书本列表: ")
        for book_info in books_info:
            player.show("  " + book_info)
        player.show("§6请输入序号以选择: ")
        book_no = player.input()
        book_no = utils.try_int(book_no)
        if book_no is None:
            player.show("§c无效输入")
            return
        book_id = books_id[book_no]
        book_info = fqapi.book_id_inquire(book_id)
        title_list = book_info["title_list"]
        item_id_list = book_info["item_id_list"]
        player.show(f"§6共找到了{len(item_id_list)}个结果。")
        while True:
            player.show("§6请输入你需要看的章节号: \n(输入§e退出§6以退出)")
            resp = player.input()
            if resp == "退出" or resp is None:
                break
            elif resp.isdigit():
                resp = int(resp)
                if resp > 0:
                    item_id = item_id_list[resp - 1]
                    title = title_list[resp - 1]
                    article = fqapi.get_content(title, item_id)
                    article = article.split("\n")
                    for paragraph in article:
                        player.show(paragraph)
                        time.sleep(0.1)
                else:
                    player.show("§c无效输入")
            else:
                player.show("§c无效输入")

    def on_frame_exit(self, evt: FrameExit):
        status_code = evt.signal
        reason = evt.reason

        self.print(f"系统已退出 状态码={status_code} 原因={reason}")


entry = plugin_entry(NewPlugin)
