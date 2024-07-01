import os, shutil

from tooldelta import Print

Print.print_inf("正在尝试升级 ToolDelta")
os.system("pip install --upgrade tooldelta")
Print.print_suc("升级已完成, 升级插件已自动卸载")
shutil.rmtree("插件文件/ToolDelta类式插件/源码升级ToolDelta")

raise SystemExit