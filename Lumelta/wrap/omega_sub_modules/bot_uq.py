class BotUq:
    def __init__(self, omega):
        self.omega = omega
        self.game_ctrl = self.omega.game_ctrl

    def get_bot_name(self):
        return self.game_ctrl.bot_name

    def get_bot_uuid_str(self):
        return self.game_ctrl.players_uuid[self.get_bot_name()]