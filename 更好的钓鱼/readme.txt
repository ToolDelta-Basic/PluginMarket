计分板部分:
鱼竿属性:
鱼竿_钓鱼冷却: 每次钓鱼后设置的冷却
鱼竿_钓鱼爆率: 数值越高越容易钓到高品质物品
鱼竿_物品爆率: 钓到物品类型的权重
鱼竿_生物爆率: 钓到生物类型的权重
鱼竿_结构爆率: 钓到结构类型的权重
鱼竿_连钓次数: 每次钓鱼会钓到几个物品
鱼竿_空钩概率: 每次钓鱼都会有概率空钩, 越高越不容易空钩

玩家属性:
玩家_钓鱼次数: 当前玩家剩余的钓鱼次数，为0则无法钓鱼
玩家_钓鱼冷却: 冷却缩减, 对钓鱼后的冷却百分比缩减
玩家_钓鱼爆率: 与鱼竿属性相同
玩家_物品爆率: 与鱼竿属性相同
玩家_生物爆率: 与鱼竿属性相同
玩家_结构爆率: 与鱼竿属性相同
玩家_连钩数量: 与鱼竿属性相同
玩家_空钩概率: 与鱼竿属性相同
玩家_冷却计时: 用来存储钓鱼冷却

设置部分:
基础爆率: 数值越高越难钓到高品质物品
基础空钩率: 数值越高越容易空钩

如何使用:
给予玩家Cat.Fishing的tag后让玩家私聊机器人发送Cat.Fishing即可钓鱼一次
因此你可以自由的编写钓鱼方式

奖池配置:
在配置对某一类型的命令方块对接开启后
你可以在奖励内添加一个键值, 命令方块对接: True  标签: "喵喵喵"
这样会使原有的给予奖励方式失效，并给玩家添加标签, 你可以设置一条命令链进行处理
开启命令方块对接后 如果奖励设置内存在 "名称": "xxx" 插件会对玩家发送提示, 如果没有则不发送

奖池注意事项: 不要写了品质不填写类型, 不要写了类型不添加奖励

需要的命令:
tellraw @a[tag=robot] {"rawtext":[{"text":"Cat.upScore"},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_冷却计时"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_钓鱼次数"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_钓鱼冷却"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_钓鱼爆率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_物品爆率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_生物爆率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_结构爆率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_空钩概率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_连钓次数"}},{"selector":"@a"},{"score":{"name":"@a","objective":"鱼竿_钓鱼冷却"}},{"selector":"@a"},{"score":{"name":"@a","objective":"鱼竿_钓鱼爆率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"鱼竿_物品爆率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"鱼竿_生物爆率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"鱼竿_结构爆率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"鱼竿_空钩概率"}},{"selector":"@a"},{"score":{"name":"@a","objective":"鱼竿_连钓次数"}},{"selector":"@a"},{"score":{"name":"@a","objective":"玩家_鱼饵属性"}}]}
推荐延迟 20
scoreboard players remove @a[scores={玩家_冷却计时=1..}] 玩家_冷却计时 1
推荐延迟 20