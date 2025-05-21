我们基于差分算法重写了“世界导入”插件，现在我们将具有记录多个时间点的存档的能力。
这意味着，如果你认为可能，你可以记录 前一天、前两天、前三天、…… 的镜像存档，并按照需要生成任意时间点的 MC 存档。
当然，由于我们的改动很大，所以新插件跟旧插件是不兼容的(但是旧插件仍然保留)，但这不意味着之前的存档会作废，你仍然可以用于恢复，只是它与现在所使用的数据库毫无关联。

目前，推荐的参数是每天记录一次新的时间点，然后最多允许出现 7 个时间点。
您可以根据您服务器的实际情况调整，但我们建议是不要将频率设置的比半天一次更大，并且最好不要超过 30 个时间点。

底层时间线的实现的最细颗粒度精确到区块，所以可以不用很担心磁盘读写过大的问题。
另外，由于我们使用单文件数据库储存存档的时间线，所以这将很容易管理数据库文件，至少对于大部分用户而言是这样的。





如果你希望恢复数据库为 MC 存档并现场导入，请在租赁服发送“.存档恢复”。
当然，这个触发词可以改，在配置文件里面。
然后，如果你不是硬核/专业用户，那么你可以不看后面的部分。





最后，关于如何将这种数据库恢复为对应的 MC 存档，你需要使用专业的恢复工具，
敬请参阅 https://github.com/TriM-Organization/bedrock-chunk-diff/blob/main/README.md#recover 以了解更多信息。

关于恢复工具：
1. 目前已经为恢复工具提供预构建，查看 https://github.com/TriM-Organization/bedrock-chunk-diff/releases 以了解更多信息
2. 这是一个命令行工具，希望提供的功能应该相对全面

目前恢复工具提供了以下 flag
```
  -ensure-exist-one
        If the specified chunk exists in the database but none of the time points on this chunk meet the given time conditions, ensure that at least the closest one can be selected. (default true)
  -max-concurrent int
        The maximum concurrent quantity. Set 0 to disable. Note that set to 1 is slow than when set to 0. (default 4096)
  -no-grow-sync
        Database settings: No grow sync. (default true)
  -no-sync
        Database settings: No Sync. (default true)
  -output string
        The path to output your Minecraft world.
  -path string
        The path of your timeline database.
  -provided-unix-time int
        Restore to the world closest to this time (earlier than or equal to the given time). The default value is the current time.
  -range-dimension int
        Where to find these chunks (only valid when enable use-range flag)
  -range-end-x int
        The ending point X coordinate to be restored.
  -range-end-z int
        The ending point Z coordinate to be restored.
  -range-start-x int
        The starting point X coordinate to be restored.
  -range-start-z int
        The starting point Z coordinate to be restored.
  -use-range
        If you would like recover the part of the world, but not the entire.
```

相应的中文翻译是
```
  -ensure-exist-one
        如果数据库中存在目标区块，但这个区块上的所有时间点都不满足给定的时间限制条件，则确保至少可以得到一个与给定时间限制最接近的时间点。(默认启用)
  -max-concurrent int
        最大并发的线程数量。设置 0 为禁用。注意，设置为 1 比设置为 0 要慢。(默认 4096 并发线程)
  -no-grow-sync
        数据库设置: 跳过截断调用 (默认启用)
  -no-sync
        数据库设置: 跳过 fsync 调用 (默认启用)
  -output string
        MC 存档的输出路径。
  -path string
        数据库的文件路径。
  -provided-unix-time int
        恢复到最接近此时间戳的 MC 存档（早于或等于给定时间）。默认值为当前时间。
  -range-dimension int
        在哪个维度查找需要恢复的区块 (进行 -use-range 启用时有用)
  -range-end-x int
        要恢复区域的终止 X 轴坐标 (方块坐标)
  -range-end-z int
        要恢复区域的终止 Z 轴坐标 (方块坐标)
  -range-start-x int
        要恢复区域的起始 X 轴坐标 (方块坐标)
  -range-start-z int
        要恢复区域的起始 Z 轴坐标 (方块坐标)
  -use-range
        如果你只是想恢复特定矩形区域的区块到 MC 存档，则使用该选项。
```

我们下面有一些例子
```
恢复 world_timeline.db 中的全部区块到 mcworld 文件夹中，并且恢复所用的时间点是最新的那个。
xxx -path world_timeline.db -output mcworld -ensure-exist-one=false

恢复 world_timeline.db 中的全部区块到 mcworld 文件夹中，并且恢复到 2025/05/19 23:44:18 (1747669458) 及以前最新的那个。
xxx -path world_timeline.db -output mcworld -ensure-exist-one=false -provided-unix-time 1747669458

恢复 world_timeline.db 中下界(id=1)的区块到 mcworld 文件夹中，并且只恢复 (0,30) 到 (512,1000) 之间的区块。恢复到的时间点是最新的那个。
xxx -path world_timeline.db -output mcworld -ensure-exist-one=false -use-range=true -range-dimension 1 -range-start-x 0 -range-start-z 30 -range-end-x 512 -range-start-z 1000

恢复 /happy/super.db 中的全部区块到 /lll/my_world 文件夹中，并且恢复到 2025/05/19 23:44:18 及以前最新的那个。
如果某个区块具有时间线但其上的全部时间点都不满足 2025/05/19 23:44:18 及以前的时间限制，则挑选一个距离 2025/05/19 23:44:18 最近的时间点作为恢复用时间点。
xxx -path /happy/super.db -output /lll/my_world -ensure-exist-one=true -provided-unix-time 1747669458
```

如果你想深究我们的实现细节，参阅相应的代码仓库以了解更多信息。
https://github.com/TriM-Organization/bedrock-chunk-diff





哦，对了，关于“数据库跳过截断调用”和“数据库跳过 fsync 调用”，这适合高级用户使用，以下是它们各自的介绍。

当 no_grow_sync 为 true 时，在数据库增长阶段跳过截断调用。
仅在非 ext3/ext4 系统上将此值设为 true 是安全的。
跳过截断操作可避免硬盘空间的预分配，
并在重映射时绕过 truncate() 和 fsync() 系统调用。
    - 另请参阅：https://github.com/boltdb/bolt/issues/284
默认值为不启用。

设置 no_sync 标志将使数据库在每次提交后跳过 fsync() 调用。
这在批量向数据库加载数据时非常有用，如果系统故障或数据库损坏，可以重新开始批量加载。切勿在常规使用时设置此标志。
此举并不安全，请谨慎使用。
默认值为不启用。

高级用户可以视情况调整这两个参数，如果希望能得到更快的数据库写速度。