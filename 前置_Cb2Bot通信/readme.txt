让命令方块借助 tellraw 向机器人发送数据。

示例:
    放置一个命令方块, 设置内容:
        tellraw @a[tag=robot] {"rawtext":[{"text":"example-trigger"}]}

    编写一个示例的接受函数:
    def _cb(args: list[str]):
        print("I have been called!")
        # print(args)
    然后使用该插件的 api: regist_message_cb("example-trigger", _cb) 注册回调函数
    那么当每次激活命令方块时, 此回调函数都会执行一遍。
    其中, "example-trigger" 这个参数对应 tellraw 第一项的内容。

    Q: 如果需要传递参数怎么办？

    将刚刚的命令方块内容改成:
        tellraw @a[tag=robot] {
            "rawtext":[{
                "text":"example-trigger"
            },{
                "text":"nihao"
            },{
                "selector":"@p"
            },{"score":{
                "name":"@p","objective":"money"
            }}
        ]}
    再将回调函数(只需要改回调):
    def _cb(args: list[str]):
        print("I have been called with:", args)
    假设离此命令方块最近的玩家名为 Art, 他的计分板分数 money 为 99.
    这样, args 就会是一个有三个成员的字符串列表,
        第一项为 "nihao",
        第二项为 "Art",
        第三项为 "99".