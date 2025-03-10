import os
from tooldelta import Plugin, Print, ToolDelta, Utils, TYPE_CHECKING, plugin_entry

from tooldelta.game_utils import getPosXYZ


class SFXPlayer(Plugin):
    name = "音效播放器"
    author = "SuperScript"
    version = (0, 0, 2)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.make_data_path()
        os.makedirs(os.path.join(self.data_path, "midi_backup"), exist_ok=True)
        self.ListenPreload(self.on_def)

    def on_def(self):
        self.sfx = self.GetPluginAPI("MIDI播放器")
        self.intract = self.GetPluginAPI("前置-世界交互")
        self.cb2bot = self.GetPluginAPI("Cb2Bot通信")
        if TYPE_CHECKING:
            from 前置_MIDI播放器 import ToolMidiMixer
            from 前置_世界交互 import GameInteractive
            from 前置_Cb2Bot通信 import TellrawCb2Bot

            self.sfx = self.get_typecheck_plugin_api(ToolMidiMixer)
            self.intract = self.get_typecheck_plugin_api(GameInteractive)
            self.cb2bot = self.get_typecheck_plugin_api(TellrawCb2Bot)
        self.script = self.GetPluginAPI("ZBasic", (0, 0, 2), False)
        if self.script and TYPE_CHECKING:
            from ZBasic_Lang_中文编程 import ToolDelta_ZBasic

            self.script = self.get_typecheck_plugin_api(ToolDelta_ZBasic)
        if self.script:
            self.init_script()
            Print.print_inf("音效播放器: ZBasic插件已装载, 扩展语法已自动增加")
            self.cb2bot.regist_message_cb("sfx.play", self.play_sfx_at)
        self.scan_files()

    def scan_files(self):
        files = []
        for file in os.listdir(self.data_path):
            if file.endswith(".mid"):
                self.sfx.translate_midi_to_seq_file(
                    os.path.join(self.data_path, file),
                    os.path.join(self.data_path, file[:-4] + ".midseq"),
                )
                os.rename(
                    os.path.join(self.data_path, file),
                    os.path.join(self.data_path, "midi_backup", file),
                )
        for file in os.listdir(self.data_path):
            if file.endswith(".midseq"):
                fname = file[:-7]
                self.sfx.load_sound_seq_file(os.path.join(self.data_path, file), fname)
                files.append(fname)
        self.files = files

    def put_cmd_block(self, player: str, args: list[str]):
        # WIP !!!
        fname = args[0]
        if fname.endswith(".mid"):
            fname = fname[:-4]
        if fname not in self.files:
            self.game_ctrl.say_to(player, "§c此音乐文件名不存在!")
            return
        x, y, z = getPosXYZ(player)
        cmd_tellraw = {"rawtext": [{"text": f"{int(x)}"}, {"text": ""}]}

    def play_sfx_at(self, msg: list[str]):
        if len(msg) == 4:
            xp, yp, zp, sfx_fname = msg
            xp = Utils.try_int(xp)
            yp = Utils.try_int(yp)
            zp = Utils.try_int(zp)
            if xp is None or yp is None or zp is None:
                Print.print_war(f"不正确的音效播放请求命令(来自命令方块): {msg}")
            if sfx_fname not in self.files:
                Print.print_war(
                    f"音效播放器: 音效文件 {sfx_fname} 不存在, 无法播放音效"
                )
            else:
                self.sfx.playsound_at_target(sfx_fname, f"@a[x={xp},y={yp},z={zp}]")
        elif len(msg) == 2:
            target, sfx_name = msg
            if sfx_name not in self.files:
                Print.print_war(f"音效播放器: 音效文件 {sfx_name} 不存在, 无法播放音效")
            else:
                self.sfx.playsound_at_target(sfx_name, target)
        return True

    def init_script(self):
        intp = self.script

        def cmd_compile_1(args, reg):
            # 播放音效 <目标:字符串> <MIDI文件名:字符串>
            cmp = intp.parse_syntax_multi(" ".join(args), reg)
            if (
                len(cmp) != 2
                or not (
                    intp.get_type(target := cmp[0])
                    == intp.get_type(fname_syntax := cmp[1])
                    == intp.STRING
                )
                or not isinstance(fname_syntax, intp.ConstPtr)
            ):
                raise intp.CodeSyntaxError(
                    "参数应为 <目标:字符串>; <MIDI文件名:字符串(常量)>"
                )
            fname = fname_syntax.c
            if fname.endswith(".mid"):
                fname = fname[:-4]
            elif fname.endswith(".midseq"):
                fname = fname[:-7]
            if fname not in self.files:
                raise intp.CodeSyntaxError(f"MIDI文件或序列文件 {fname} 未找到")
            return intp.CustomCodeUnit(target, fname)

        def cmd_execute_1(code_args, vmap):
            target = code_args[0].eval(vmap)
            fname = code_args[1]
            self.sfx.playsound_at_target_sync(fname, target)

        def cmd_execute_2(code_args, vmap):
            target = code_args[0].eval(vmap)
            fname = code_args[1]
            self.sfx.playsound_at_target(fname, target)

        intp.register_cmd_syntax("播放音效", cmd_compile_1, cmd_execute_1)
        intp.register_cmd_syntax("异步播放音效", cmd_compile_1, cmd_execute_2)


entry = plugin_entry(SFXPlayer)
