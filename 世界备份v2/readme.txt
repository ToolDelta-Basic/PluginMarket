我们基于差分算法重写了“世界导入”插件，现在我们将具有记录多个时间点的存档的能力。
这意味着，如果你认为可能，你可以记录 前一天、前两天、前三天、…… 的镜像存档，并按照需要生成任意时间点的 MC 存档。
当然，由于我们的改动很大，所以新插件跟旧插件是不兼容的(但是旧插件仍然保留)，但这不意味着之前的存档会作废，你仍然可以用于恢复，只是它与现在所使用的数据库毫无关联。

目前，推荐的参数是每天记录一次新的时间点，然后最多允许出现 7 个时间点。
您可以根据您服务器的实际情况调整，但我们建议是不要将频率设置的比半天一次更大，并且最好不要超过 30 个时间点。

底层时间线的实现的最细颗粒度精确到区块，所以可以不用很担心磁盘读写过大的问题。
另外，由于我们使用单文件数据库储存存档的时间线，所以这将很容易管理数据库文件，至少对于大部分用户而言是这样的。






最后，关于如何将这种数据库恢复为对应的 MC 存档，你需要使用专业的恢复工具，
敬请参阅 https://github.com/TriM-Organization/bedrock-chunk-diff/blob/main/README.md#recover 以了解更多信息。

关于恢复工具：
1. 目前没有提供恢复工具的编译产物，所以需要您自行编译然后使用
2. 这是一个命令行工具，希望提供的功能应该相对全面
3. 我会在之后提供工具的编译产物，届时本文档将会更新以体现这件事

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
        Restore to the world closest to this time (earlier than or equal to the given time). The default value is the current time. (default 1747594226)
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

如果你想深究我们的实现细节，参阅该论文以了解详细信息。
https://github.com/TriM-Organization/bedrock-chunk-diff/blob/main/doc/Sub%20Chunk%20Delta%20Update%20Implements%20Disscussion.pdf





哦，对了，关于“数据库跳过截断调用”和“数据库跳过 fsync 调用”，这适合高级用户使用，以下是它们各自的介绍。

当 no_grow_sync 为 true 时，在数据库增长阶段跳过截断调用。
仅在非 ext3/ext4 系统上将此值设为 true 是安全的。
跳过截断操作可避免硬盘空间的预分配，
并在重映射时绕过 truncate() 和 fsync() 系统调用。
    - 另请参阅：https://github.com/boltdb/bolt/issues/284
默认值为 False。

设置no_sync标志将使数据库在每次提交后跳过fsync()调用。
这在批量向数据库加载数据时非常有用，如果系统故障或数据库损坏，可以重新开始批量加载。切勿在常规使用时设置此标志。
此举并不安全，请谨慎使用。
默认值为 False。

高级用户可以视情况调整这两个参数，如果希望能得到更快的数据库写速度。