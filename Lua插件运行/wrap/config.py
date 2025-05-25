import json
from pathlib import Path
from .loosejson import loads

class LumegaPluginConfig:
    def __init__(self, config_str, config_file_path = ""):
        config = {}
        try:
            config = loads(config_str)
            if not isinstance(config, dict):
                config = {}
        except: pass
        self.file_path = Path(config_file_path)
        self.name = config.get("名称", "?")
        self.describe = config.get("描述", "?")
        self.disable = True if config.get("是否禁用") == True else False
        self.source = config.get("来源", "LuaLoader")
        self.config = config.get("配置", {})

    def to_json(self):
        return {
        	"名称": self.name,
        	"描述": self.describe,
        	"是否禁用": self.disable,
        	"来源": self.source,
        	"配置": self.config
        }