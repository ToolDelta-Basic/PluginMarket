import json
class Common:
    def __init__(self, omega):
        self.omega = omega
        self.game_data_handler = self.omega.game_data_handler

    def lang_format(self, lang_code, text, *args):
        return "".join([json.loads(text) for text in self.game_data_handler.Handle_Text_Class1({
            "Message": text,
            "Parameters": args
        })])