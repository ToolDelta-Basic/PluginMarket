class SafeList(list):
    def __getitem__(self, index):
        try:
            index = int(index)
            value = super().__getitem__(index)
            if isinstance(value, list):
                return SafeList(value)
            elif isinstance(value, dict):
                return SafeDict(value)
            return value
        except:
            return None


class SafeDict(dict):
    def __getitem__(self, key):
        return self.get(key, None)
        try:
            value = self.get(key, None)
            if isinstance(value, list):
                return SafeList(value)
            elif isinstance(value, dict):
                return SafeDict(value)
            return value
        except:
            return None