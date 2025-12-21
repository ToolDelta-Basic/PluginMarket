local omega = require("omega")
local json = require("json")
--- @type Coromega
local coromega = require("coromega").from(omega)

-- 如果你需要调试请将下面一段解除注释，关于调试的方法请参考文档
-- local dbg = require('emmy_core')
-- dbg.tcpConnect('localhost', 9966)
-- print("waiting...")
-- for i=1,1000 do -- 调试器需要一些时间来建立连接并交换所有信息
--     -- 如果始终无法命中断点，你可以尝试将 1000 改的更大
--     print(".")
-- end
-- print("end")

threading = import("threading")
psutil = import("psutil")
os = import("os")
pid = os.getpid()
process = psutil.Process(pid)

coromega:when_called_by_terminal_menu({
    triggers = { "线程" },
    argument_hint = "",
    usage = "获取Python总线程数量",
}):start_new(function(input)
    coromega:print("当前线程数量为：" .. tostring(threading.active_count()))
end)

coromega:when_called_by_terminal_menu({
    triggers = { "内存" },
    argument_hint = "",
    usage = "获取Python总内存占用",
}):start_new(function(input)
    coromega:print("当前内存占用为：" .. tostring(string.format("%.2f" , process.memory_info() / (1024 * 1024))) .. "MB")
end)

coromega:run()
