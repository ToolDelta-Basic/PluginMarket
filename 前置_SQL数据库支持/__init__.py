import base64
import sqlite3
import os
import json
import ast
import hashlib
from typing import Any
from tooldelta import plugins, Plugin

plugins.add_plugin_as_api("SQlite数据库支持")
class DataBaseSqlit(Plugin):
    """数据库操作类, 用于简化数据库操作, 并提供一些常用的数据库操作方法"""
    name = "SQLite数据库操作支持"
    author = "xingchen"
    version = (0, 0, 1)

    def __init__(self, f) -> None:
        super().__init__(f)
        self.__DataBase__: dict = {}
        self.__DataBaseTableStruct__: dict[str, tuple] = {}

    class DataBaseTagIsNull(Exception):...
    class DataBaseOpenError(Exception):...
    class DataBaseNeedStruct(Exception):...
    class DataBaseTableNameIsNull(Exception):...

    class DataBaseTableStruct:
        """
        数据库表结构类, 用于简化数据库表结构的创建
        只需要提供字段名和他的python类型即可，因为ToolDelta会将数据转成统一类型

        Args:
            *args: tuple[str, type], 字段名和他的Python类型
            例: |
                DataBaseTableStruct(("id", int), ("name", str))
        """
        def __init__(self, *args: tuple[str, type]) -> None:
            self.TypeTable: dict = {}
            for tup in args:
                self.__add_value__(*tup)

        def __add_value__(self, name: str, type: type) -> None:
            self.TypeTable[name] = type

    class DataBaseTableCtrl:
        def __init__(self, DataBase, DataBaseTableStruct, Table, Key) -> None:
            self.DataBase = DataBase
            self.DataBaseTableStruct = DataBaseTableStruct
            self.Table = Table
            self.Key = Key
            self.cursor: sqlite3.Cursor = DataBase.cursor()
            self.DataBaseStruct = self.__get_struct__()

        class DataBaseTableSetDataArgsError(Exception):...
        class DataBaseTableGetDataDataLengthError(Exception):...
        class DataBaseTableDataBreakDown(Exception):...
        class DataBaseTableUpdateDataArgsError(Exception):...
        class DataBaseTableRemoveDataArgsError(Exception):...

        def __get_struct__(self) -> Any:
            for Name, Struct in self.DataBaseTableStruct:
                if Name == self.Table:
                    return Struct.TypeTable
            return None

        def set_data(self, *args: Any) -> None:
            """
            新增数据到表中

            Args:
                data (任何类型): 传入数据

            Raises:
                DataBaseTableSetDataArgsError: 参数数量不匹配
            """
            num_placeholders = len(self.DataBaseStruct)
            placeholders = ','.join(['?' for _ in range(num_placeholders)])
            if len(args) != num_placeholders:
                raise self.DataBaseTableSetDataArgsError("参数数量不匹配")

            processed_args = []

            for arg in args:
                base64_arg = base64.b64encode(str(arg).encode('utf-8')).decode('utf-8')
                processed_args.append(self.__encrypt_text__(base64_arg))

            self.cursor.execute(f"INSERT INTO {self.Table} values({placeholders})", processed_args)
            self.cursor.connection.commit()

        def update_data(self, update_values: dict, condition: dict):
            """
            更新表中的数据

            Args:
                update_values (dict): 更新值字典   例: {"name": "xxx"}
                condition (dict): 条件字典
                例:
                    update_values = {"name": "xxx"} # 更新 name 字段为 xxx
                    condition = {"id": 1} # 条件为 id = 1
            """
            processed_update_values = {}
            for key, value in update_values.items():
                base64_value = base64.b64encode(str(value).encode('utf-8')).decode('utf-8')
                processed_update_values[key] = self.__encrypt_text__(base64_value)

            processed_condition = {}
            for key, value in condition.items():
                base64_value = base64.b64encode(str(value).encode('utf-8')).decode('utf-8')
                processed_condition[key] = self.__encrypt_text__(base64_value)

            update_set_clause = ', '.join([f"{key} = ?" for key in processed_update_values.keys()])
            condition_clause = ' AND '.join([f"{key} = ?" for key in processed_condition.keys()])
            sql = f"UPDATE {self.Table} SET {update_set_clause} WHERE {condition_clause}"

            self.cursor.execute(sql, list(processed_update_values.values()) + list(processed_condition.values()))
            self.cursor.connection.commit()

        def remove_data(self, condition: dict) -> None:
            """
            从表中删除数据

            Args:
                condition (dict): 条件字典   例: {"id": 1}

            Raises:
                DataBaseTableRemoveDataArgsError: condition 为空
            """
            if not condition:
                raise self.DataBaseTableRemoveDataArgsError("condition 不能为空")

            where_clause = " AND ".join([f"{key} = ?" for key in condition.keys()])
            where_values = list(condition.values())
            sql = f"DELETE FROM {self.Table} WHERE {where_clause}"

            for arg in where_values:
                base64_arg = base64.b64encode(str(arg).encode('utf-8')).decode('utf-8')
                where_values.remove(arg)
                where_values.append(self.__encrypt_text__(base64_arg))

            self.cursor.execute(sql, where_values)
            self.cursor.connection.commit()

        def get_data(self, idx: int = -1) -> list[dict]:
            """
            从表中获取数据

            Args:
                idx (int, optional): 索引, 默认为 -1, 即获取所有数据

            return:
                list[dict]: 表内所有数据
            """
            self.cursor.execute(f"SELECT * FROM {self.Table}")
            result = []
            for item in self.cursor:
                decoded_item = tuple(base64.b64decode(self.__decrypt_text__(value)).decode('utf-8') for value in item)
                result.append(decoded_item)
            original_item = self.restore_data_format(result) # type: ignore
            if idx == -1:
                return original_item
            else:
                if idx >= len(original_item):
                    raise self.DataBaseTableGetDataDataLengthError("数据长度不匹配!")
                return original_item[idx] # type: ignore

        def restore_data_format(self, data: list[tuple]) -> list[dict]:
            """
            使用 DataBaseStruct 恢复原数据格式

            Args:
                data (list[tuple]): 数据库内的数据

            Raises:
                DataBaseTableDataBreakDown: 数据库结构可能损坏!

            Returns:
                list[dict]: 原数据格式
            """
            try:
                if not self.DataBaseStruct:
                    raise self.DataBaseTableSetDataArgsError("DataBaseStruct is not initialized.")

                restored_data = []
                for row in data:
                    restored_row = {}
                    for idx, (key, value) in enumerate(zip(self.DataBaseStruct.keys(), row)):
                        if self.DataBaseStruct[key] == dict:
                            restored_row[key] = json.loads(value.replace('"', "").replace("'", '"'))
                        elif self.DataBaseStruct[key] == list:
                            restored_row[key] = ast.literal_eval(value.replace('"', "").replace("'", '"'))
                        elif self.DataBaseStruct[key] == tuple:
                            restored_row[key] = eval(value)
                        else:
                            restored_row[key] = self.DataBaseStruct[key](value)
                    restored_data.append(restored_row)
                return restored_data
            except:
                raise self.DataBaseTableDataBreakDown("数据库结构可能损坏!")

        def __encrypt_text__(self, text: str) -> str:
            if not self.Key:
                return text
            password_bytes = self.Key.encode('utf-8')
            sha256 = hashlib.sha256()
            sha256.update(password_bytes)
            text_bytes = text.encode('utf-8')
            encrypted_bytes = bytearray()
            for i in range(len(text_bytes)):
                encrypted_bytes.append(text_bytes[i] ^ sha256.digest()[i % len(sha256.digest())])
            return encrypted_bytes.hex()

        def __decrypt_text__(self, encrypted_text: str) -> str:
            if not self.Key:
                return encrypted_text
            password_bytes = self.Key.encode('utf-8')
            sha256 = hashlib.sha256()
            sha256.update(password_bytes)
            encrypted_bytes = bytearray.fromhex(encrypted_text)
            decrypted_bytes = bytearray()
            for i in range(len(encrypted_bytes)):
                decrypted_bytes.append(encrypted_bytes[i] ^ sha256.digest()[i % len(sha256.digest())])
            return decrypted_bytes.decode('utf-8')

        def Del_Table(self) -> None:
            self.cursor.execute(f"DROP TABLE {self.Table}")

    def OpenDataBase(self, Tag: str = None, Key: str = None, Temp: bool = False) -> None: # type: ignore
        """
        打开一个数据包通过Tag, 若Tag不存在则创建新的数据库

        Args:
            Tag (str, optional): 数据库的标签
            Key (bytes, optional): 数据库的密钥[可选]
            Temp (bool, optional): 是否为临时数据库

        Raises:
            DataBaseTagIsNull: Tag不能为空
            DataBaseOpenError: 数据库打开失败!
        """
        if not Tag:
            raise self.DataBaseTagIsNull("Tag不能为空")
        if not Temp:
            if not os.path.exists(f"数据库文件/{Tag}"):
                os.makedirs(f"数据库文件/{Tag}")
            self.__DataBase__[Tag] = {"Conn": sqlite3.connect(f"数据库文件/{Tag}/DataBase-{Tag}.db", check_same_thread=False),"Key": Key, "IsTemp": False}
        elif Temp: # type: ignore
            self.__DataBase__[Tag] = {"Conn": sqlite3.connect(":memory:", check_same_thread=False), "Key": Key, "IsTemp": True}

        if self.__DataBase__.get(Tag) is None:
            raise self.DataBaseOpenError("数据库打开失败!")

    def OpenDataBaseTable(self, Tag: str, TableName: str, Key: str = None, TableStruct: DataBaseTableStruct = None) -> DataBaseTableCtrl: # type: ignore
        """
        通过Tag打开一个数据库的对应数据包

        Args:
            Tag (str): 数据库的标签
            TableName (str): 数据库的表名
            Key (bytes, optional): 数据库的密钥[可选]

        Raises:
        """
        if not self.__DataBase__.get(Tag):
            raise self.DataBaseTagIsNull("数据库标签不存在!")
        if not TableStruct:
            raise self.DataBaseNeedStruct("数据库结构不能为空!")
        if not TableName:
            raise self.DataBaseTableNameIsNull("数据库表名不能为空!")

        cursor: sqlite3.Cursor = self.__DataBase__[Tag]["Conn"].cursor()
        TableVString: str = ""

        for i in TableStruct.TypeTable:
            TableVString += f"{i} TEXT,"

        cursor.execute(f"CREATE TABLE IF NOT EXISTS {TableName}({TableVString[:-1]})")

        if self.__DataBaseTableStruct__.get(Tag) is None:
            self.__DataBaseTableStruct__[Tag] = [(TableName, TableStruct)] # type: ignore
        else:
            self.__DataBaseTableStruct__[Tag].append((TableName, TableStruct)) # type: ignore

        return self.DataBaseTableCtrl(self.__DataBase__[Tag]["Conn"], self.__DataBaseTableStruct__[Tag], TableName, self.__DataBase__[Tag]["Key"]) # type: ignore

    def CloseDataBase(self, Tag: str) -> None: # type: ignore
        """
        关闭一个数据库

        Args:
            Tag (str): 数据库的标签

        Raises:
            DataBaseTagIsNull: Tag不能为空
        """
        if not Tag:
            raise self.DataBaseTagIsNull("Tag不能为空")

        if self.__DataBase__.get(Tag) is not None:
            self.__DataBase__[Tag]["Conn"].close()
            del self.__DataBase__[Tag]
