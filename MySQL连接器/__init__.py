from tooldelta import Plugin, plugin_entry

global_vars = {}


class MySQLSupport(Plugin):
    name = "MySQL"
    author = "小虫虫"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self.frame.add_console_cmd_trigger(
            ["mysql"],
            "[host], [user], [password], [database], [port]",
            "连接到MySQL服务器",
            self.on_connect,
        )
        self.ListenPreload(self.on_def)

    def on_def(self):
        self.pip = self.GetPluginAPI("pip")
        self.pip.require("pymysql")
        import pymysql

        global_vars["pymysql"] = pymysql
        self.MySQL = MySQLConnector

    def on_connect(self, args):
        mysql = self.MySQL
        host = args[0] if len(args) > 0 else input("请输入 MySQL 主机地址: ")
        user = args[1] if len(args) > 1 else input("请输入 MySQL 用户名: ")
        password = args[2] if len(args) > 2 else input("请输入 MySQL 用户密码: ")
        database = args[3] if len(args) > 3 else input("请输入 MySQL 数据库名: ")
        port = (
            args[4]
            if len(args) > 4
            else input("请输入 MySQL 主机端口(直接回车使用默认端口): ")
        )
        if port == "" or port is None:
            port = 3306
        else:
            port = int(port)
        db = mysql(host, user, password, database, port)
        db.connect()
        while True:
            sql = input("请输入 MySQL 指令(输入 q 以退出): ")
            if sql == "q":
                break
            print(db.tryexec(sql, None, True))
        db.disconnect()


class MySQLConnector:
    def __init__(self, host, user, password, database, port=3306):
        """
        初始化 MySQL 连接器
        Parameters:
            host (str): MySQL 主机地址
            user (str): MySQL 用户名
            password (str): MySQL 用户密码
            database (str): MySQL 数据库名
            port (int): 可选, MySQL 主机端口(不填写则使用 3306 端口)
        Returns:
            None
        """
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.connection = None
        self.cursor = None
        self.pymysql = global_vars["pymysql"]

    def connect(self):
        """
        连接到 MySQL 数据库
        Parameters:
            None
        Returns:
            None
        """
        pymysql = self.pymysql
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
            self.cursor = self.connection.cursor()
        except pymysql.Error as e:
            print(f"Error connecting to MySQL: {e}")
            raise

    def disconnect(self):
        """
        断开与 MySQL 数据库的连接
        Parameters:
            None
        Returns:
            None
        """
        pymysql = self.pymysql
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        self.connection = None
        self.cursor = None

    def tryexec(self, sql, data=None, withres=False):
        """
        执行 SQL 语句, 支持预处理和错误回滚
        Parameters:
            sql (str): SQL 语句
            data (tuple): 可选, 如果需要预处理才需传入
            withres (bool): 可选, 如果需要执行语句的返回值则传入True
        Returns:
            bool, tuple: 若语句失败则返回 False , 否则返回结果或 True
        """
        pymysql = self.pymysql
        try:
            if data:
                self.cursor.execute(sql, data)
            else:
                self.cursor.execute(sql)
            self.connection.commit()
            if withres:
                result = self.cursor.fetchall()
                return result
            return True
        except pymysql.Error as e:
            print(f"Error executing SQL: {e}")
            self.connection.rollback()
            return False

    def set(self, tablename, datadict):
        """
        插入或更新数据(使用了预处理)
        Parameters:
            tablename (str): 表名
            datadict (dict): 需要存储的数据(key 对应列名, value 对应值)
        Returns:
            bool: 若语句失败则返回 False , 否则返回 True
        """
        pymysql = self.pymysql
        self.connect()
        # 构造列名和占位符
        columns = ", ".join(datadict.keys())
        placeholders = ", ".join(["%s"] * len(datadict))
        # 构造更新的部分，使用占位符
        updateparts = ", ".join([f"{key} = %s" for key in datadict.keys()])
        # 构造SQL语句
        sql = f"INSERT INTO {tablename} ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updateparts};"
        # 执行预编译的查询，传入的参数是列表的两次扩展，因为更新部分也需要这些值
        result = self.tryexec(sql, tuple(datadict.values()) * 2)
        self.disconnect()
        return result

    def delete(self, tablename, conditions):
        """
        删除数据
        Parameters:
            tablename (str): 表名
            conditions (dict): 需要删除的数据的条件(key 对应列名, value 对应值)
        Returns:
            int: 影响的行数
        """
        pymysql = self.pymysql
        self.connect()
        # 构造WHERE子句
        where_parts = " AND ".join([f"{key} = %s" for key in conditions.keys()])
        # 构造SQL语句
        sql = f"DELETE FROM {tablename} WHERE {where_parts};"
        # 执行预编译的查询，传入的参数是条件的值组成的元组
        self.tryexec(sql, tuple(conditions.values()))
        # 获取受影响的行数
        affected_rows = self.cursor.rowcount
        self.disconnect()
        return affected_rows

    def get(self, tablename, conditions=None, columns="*"):
        """
        获取数据
        Parameters:
            tablename (str): 表名
            conditions (dict): 可选, 需要查询的数据的条件(key 对应列名, value 对应值, 不填写则查出全部数据)
            columns (str): 可选, 需要查询的列名(不填写则查出全部列的数据)
        Returns:
            bool, tuple: 若语句失败则返回 False , 否则返回结果
        """
        pymysql = self.pymysql
        self.connect()
        # 构造SQL语句
        sql = f"SELECT {columns} FROM {tablename}"
        if conditions:
            where_parts = " AND ".join([f"{key} = %s" for key in conditions.keys()])
            sql += f" WHERE {where_parts}"
        # 执行预编译的查询
        if conditions:
            result = self.tryexec(sql, tuple(conditions.values()), withres=True)
        else:
            result = self.tryexec(sql, withres=True)
        self.disconnect()
        return result


entry = plugin_entry(MySQLSupport, "MySQL")
