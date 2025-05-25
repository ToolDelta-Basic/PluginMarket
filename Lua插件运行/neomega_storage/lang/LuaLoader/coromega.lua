--module("coromega", package.seeall)
local json = require("json")
local _no_coro=function(...) error("currently not set, must run inside a coroutine") end
local _current_coro_session_resume = _no_coro
_coro_running=false
local _ud2lua = function(...) error("currently not set") end

-- 一个 Session 运行在一个独立的协程中，它的生命周期是一个协程的生命周期
-- 在一个 Session 中, 需要回调的部分通过 coroutine.yield() 交出控制权
-- 并当回调完成后, 通过 session.resume() 恢复控制权
-- 进而完成一个回调的过程, 但是看起来像是同步的
--- @class Session
local Session = { _cname = "Session" }

--- @return Session
local function newSession()
    local session = {}
    setmetatable(session, { __index = Session })
    session.resume = function(...)
        local last_coro_resume = _current_coro_session_resume
        local last_coro_running= _coro_running
        _current_coro_session_resume = session.resume
        _coro_running=true
        local ok, err = coroutine.resume(session.co, ...)
        _current_coro_session_resume = last_coro_resume
        _coro_running=last_coro_running
        if not ok then error(("lua 协程内函数错误:\n%s"):format(err)) end
    end
    return session
end


-- 一个 SessionFactory 用于创建 Session
-- 例如，当菜单被唤起时，SessionFactory 会创建一个 Session
--- @class SessionFactory
local SessionFactory = { _cname = "SessionFactory" }

--- @return SessionFactory
local function newSessionFactory()
    local instance = {}
    setmetatable(instance, { __index = SessionFactory })
    return instance
end

--- 启动一个新协程，并使用传入的参数在协程中执行 SessionFactory 内的 coro_fn
--- @param ... any coro_fn 的参数
function SessionFactory:on_new_session(...)
    local session = newSession()
    local args = { ... }
    session.co = coroutine.create(function()
        if self.result_handle ~= nil then
            self.result_handle(self.coro_fn(unpack(args)))
        else
            self.coro_fn(unpack(args))
        end
    end)
    session.resume()
end

--- 设定当 coro_fn 执行完成之后的额外处理函数，可为空
--- @param handle nil|function 处理函数
function SessionFactory:on_result(handle)
    self.result_handle = handle
    return self
end

--- 设定当条件满足时会在新协程中执行的函数
--- @param coro_fn function 条件满足时在新协程中执行的函数
function SessionFactory:start_new(coro_fn)
    self.coro_fn = coro_fn
    return self
end

-- below are omega apis that not included in Coromega
-- since they are no need to be wrapped, just use them directly

-- block convert api

-- local blocks = omega.blocks
-- local nbt = blocks.new_nbt()
-- local blockName, blockData, found = blocks.rtid_to_legacy_block(rtid)
-- local javaBlock, found = blocks.rtid_to_legacy_block(rtid)
-- local rtid, found = blocks.legacy_block_to_rtid(blockName, blockData)
-- local rtid, found = blocks.java_str_to_rtid(javaBlock)
-- TODO block state to rtid

-- structure and canvas api

-- local structures = omega.structures
-- local structure = structures.open_or_create_structure(path)
-- local canvas = structure.new_canvas()
-- structure.copy(source_structure, target_structure, source_start_pos, source_end_pos, offset)
-- local start_pos = structure/canvas:get_start_pos()
-- starutre/canvas:set_start_pos(pos)
-- local end_pos = structure/canvas:get_end_pos()
-- starutre/canvas:set_end_pos(pos)
-- local must_block_state = structure/canvas:get_must_block_state()
-- starutre/canvas:set_must_block_state(must_block_state)
-- starutre/canvas:apply_alter_to_blocks(
--     start_pos, end_pos,
--     alter_fn,
--     option_ignore_air_block, option_ignore_nbt_block, option_ignore_normal_block
-- )

-- canvas artists api

-- local canvas_artists = omega.canvas_artists
-- canvas_artists.map_art(canvas, image_file, apply_dither, xsize, zsize)

-- 对 omega 的所有函数进行重新封装
-- 屏蔽异步回调的细节, 使得看起来像是同步的
--- @class Coromega:CorOmegaField
local Coromega = { _cname = "Coromega" }

-- omega.common api wrapper
--- 生成一个 uuid string
--- @return string
function Coromega:uuid() return self.omega.common.uuid_string() end

--- 翻译特定字符串
--- @param input string
--- @param type string|nil
--- @return string,boolean
function Coromega:translate(input, type) return self.omega.common.translate(input, type) end

--- 翻译为游戏内文本
--- @param langCode number 语言代号, 0: zh_CN
--- @param input string 输入文本
--- @param ... any 可变参数，用于替换文本中的占位符（如 %s）
--- @return string,boolean
function Coromega:lang_format(langCode, input, ...) return self.omega.common.lang_format(langCode, input, ...) end


-- omega.c_common_exts api wrapper
function Coromega:_debug_c_print_int(a, b) return self.omega.c_common_exts._c_print_int(a, b) end

-- omega.system api wrapper
local translator = {
    [type(nil)] = function(rv) return "nil" end,
    ["number"] = function(rv)
        if math.floor(rv) < rv then
            return string.format("%0.3f", rv)
        else
            return tostring(rv)
        end
    end,
    ["table"] = function(rv)
        return json.loose_encode(rv)
    end,
    ["userdata"] = function(rv)
        return "userdata:" .. json.loose_encode(ud2lua(rv))
    end,
    ["string"] = function(rv) return rv end
}

--- 将一个包含任意数量任意类型的输入列表转变为 string
--- @param args any[] 包含任意数量任意类型的输入列表
--- @return string
local function element_to_str(args)
    local assambled_str = ""
    for i = 1, #args, 1 do
        local v = args[i]
        local tr = translator[type(v)]
        if not tr then tr = tostring end
        local sv = tr(v)
        if i ~= 1 then
            assambled_str = assambled_str .. " " .. sv
            -- self.omega.system.color_trans_print(" " .. sv)
        else
            assambled_str = assambled_str .. sv
            -- self.omega.system.color_trans_print(sv)
        end
    end
    return assambled_str
end

--- 在终端显示信息
--- @vararg any
--- @return nil
function Coromega:print(...)
    self.omega.system.print(element_to_str({ ... }) .. "\n")
end

--- 将信息中的颜色代码转换为终端可显示的形式
--- @vararg any
--- @return nil
function Coromega:sprint(...)
    return self.omega.system.sprint(element_to_str({ ... }) .. "\n")
end

--- 记录日志
--- @vararg any
--- @return nil
function Coromega:log(...)
    self.omega.system.log(element_to_str({ ... }))
end

--- 在终端显示信息并记录日志
--- @vararg any
---  @return nil
function Coromega:log_and_print(...)
    self.omega.system.log_and_print(element_to_str({ ... }))
end

--- 以 DEBUG(最低级别) 在终端显示信息或记录日志
--- 会试图使内容尽量可读，即使包含不可转为字符串的内容，
--- 默认不会显示或记录日志，除非在配置中将 DEBUG 的显示级别设为终端或日志
--- 显示和日志的前缀将包含 [DEBUG]
--- @vararg any
--- @return nil
function Coromega:debug_out(...)
    self.omega.system.debug_out(element_to_str({ ... }))
end

--- 以 INFO(较低级别) 在终端显示信息或记录日志
--- 默认在终端显示并记录日志，除非调整框架配置中的 INFO 显示级别 (在最后几行)
--- 显示和日志不包含前缀
--- @vararg any
--- @return nil
function Coromega:info_out(...)
    self.omega.system.info_out(element_to_str({ ... }))
end

--- 以 SUCCESS 级别在终端显示信息或记录日志
--- 添加绿色的修饰，默认在终端显示并记录日志，除非调整框架配置中的 Success 显示级别 (在最后几行)
--- @vararg any
--- @return nil
function Coromega:success_out(...)
    self.omega.system.success_out(element_to_str({ ... }))
end

--- 以 WARNING 级别在终端显示信息或记录日志
--- 添加黄色的修饰，默认在终端显示并记录日志，除非调整框架配置中的 Warning 显示级别 (在最后几行)
--- @vararg any
--- @return nil
function Coromega:warning_out(...)
    self.omega.system.warning_out(element_to_str({ ... }))
end

--- 以 ERROR 级别在终端显示信息或记录日志
--- 添加红色的修饰，默认在终端显示并记录日志，除非调整框架配置中的 Error 显示级别 (在最后几行)
--- @vararg any
--- @return nil
function Coromega:error_out(...)
    self.omega.system.error_out(element_to_str({ ... }))
end

--- 从终端获取输入, hint 为输入前的提示
--- @param hint string 输入前的提示
--- @param timeout number|nil 超时设置
--- @return string
function Coromega:backend_input(hint, timeout)
    if hint == nil then
        hint = ""
    end
    self.omega.system.color_trans_print(hint)
    local enclusure_resume = _current_coro_session_resume
    self.omega.system.input(function(input_line_with_return)
        local trimed_input_line = input_line_with_return:gsub("\n$", ""):gsub("\r$", "")
        enclusure_resume(trimed_input_line)
    end, timeout)
    return coroutine.yield()
end

--- 从终端获取输入, hint 为输入前的提示
--- @param hint string 输入前的提示
--- @param timeout number|nil 超时设置
--- @return string
function Coromega:input(hint, timeout) return self:backend_input(hint, timeout) end

--- 获得 获取操作系统和架构信息，例如 "linux-amd64"
--- @return string
function Coromega:os() return self.omega.system.os() end

--- 获取当前目录
--- @return string
function Coromega:current_dir() return self.omega.system.cwd() end

--- 创建目录
--- @param path string 路径
--- @return nil
function Coromega:make_dir(path) return self.omega.system.make_dir(path) end

--- 获取当前时间 单位秒 (unix time)
--- @return number
function Coromega:now() return self.omega.system.now() end

--- 获取当前时间 单位秒 (unix time)
--- @return number
function Coromega:now_unix() return self.omega.system.now() end

--- 获取插件启动时间,返回从插件启动开始的时间,单位秒
--- @return number
function Coromega:now_since_start() return self.omega.system.now_since_start() end

--- 创建临时目录 这个目录会在 omega 框架退出时或重启时自动删除
--- 由 neomega 保证这个目录内文件有可执行权限和其他权限
--- > 安卓的 Download 目录，即 neomega 在安卓上的默认目录没有可执行权限
--- @return string
function Coromega:make_temp_dir() return self.omega.system.temp_dir() end

--- 睡眠（休眠、暂停） 一个协程，time 为睡眠时间 单位秒。当时间过短时，可能会因为系统原因导致 sleep 时间不精确
--- @param time number
--- @return nil
function Coromega:sleep(time)
    if _coro_running then
        local enclusure_resume = _current_coro_session_resume
        self.omega.system.sleep(time, enclusure_resume)
        return coroutine.yield()
    else 
        self.omega.system.block_sleep(time)
    end
end

--- 主动停止一个协程,直到被其他协程恢复,需要配合 get_resume 使用
--- @return ...any
function Coromega:pause()
    return coroutine.yield()
end

--- 获得当前协程的恢复句柄，需要将返回值配合 coroutine.resume
--- global_on_ret = coromega:get_resume()
--- local ret = coromega:pause() 此时此协程停止，直到获得返回
--- print(ret) -- 1
--- 在其他协程中:
--- global_on_ret(1) 此时 coromega:pause() 的协程恢复
--- @return function
function Coromega:get_resume()
    local enclusure_resume = _current_coro_session_resume
    return enclusure_resume
end

-- omega.cmds api wrapper

--- 以 wo 身份发送 setting command 命令 没有返回值，部分指令使用此方法发送是无效的
--- @param cmd string 命令字符串
function Coromega:send_wo_cmd(cmd) self.omega.cmds.send_wo_cmd(cmd) end

--- 以 websocket 身份发送命令 当 get_result 为 true 时 ,会返回命令执行结果 否则返回 nil
--- @param cmd string 命令字符串
--- @param get_result boolean 是否等待并返回命令结果
--- @param timeout number 超时
--- @return table|nil
function Coromega:send_ws_cmd(cmd, get_result, timeout)
    if get_result then
        local enclusure_resume = _current_coro_session_resume
        self.omega.cmds.send_ws_cmd_with_resp(cmd, function(result)
            enclusure_resume(_ud2lua(result:user_data()))
        end, timeout)
        return coroutine.yield()
    else
        self.omega.cmds.send_ws_cmd(cmd)
    end
end

--- 以 player 身份发送命令 当 get_result 为 true 时 ,会返回命令执行结果 否则返回 nil
--- @param cmd string 命令字符串
--- @param get_result boolean 是否等待并返回命令结果
--- @param timeout number 超时
--- @return table|nil
function Coromega:send_player_cmd(cmd, get_result, timeout)
    if get_result then
        local enclusure_resume = _current_coro_session_resume
        self.omega.cmds.send_player_cmd_with_resp(cmd, function(result)
            enclusure_resume(_ud2lua(result:user_data()))
        end, timeout)
        return coroutine.yield()
    else
        self.omega.cmds.send_player_cmd(cmd)
    end
end

--- 发送网易魔法指令 当 get_result 为 true 时 ,会返回命令执行结果 否则返回 nil
--- @param cmd string 命令字符串
--- @param get_result boolean 是否等待并返回命令结果
--- @param timeout number 超时
--- @return table|nil
function Coromega:send_ai_cmd(cmd, get_result, timeout)
    local bot_runtime_id = self.omega.botUq.get_bot_runtime_id()
    if get_result then
        local enclusure_resume = _current_coro_session_resume
        self.omega.cmds.send_ai_cmd_with_resp(bot_runtime_id, cmd, function(result)
            enclusure_resume(_ud2lua(result:user_data()))
        end, timeout)
        return coroutine.yield()
    else
        self.omega.cmds.send_ai_cmd(bot_runtime_id, cmd)
    end
end

--- @class CoroPlayer
local CoroPlayer = { _cname = "CoroPlayer" }

--- @param player_kit PlayerKit
--- @param Coromega Coromega
--- @return CoroPlayer
local function newCoroPlayer(player_kit, Coromega)
    local instance = { player_kit = player_kit, Coromega = Coromega }
    setmetatable(instance, { __index = CoroPlayer })
    return instance
end

--- 获得玩家的坐标
--- @return table
function CoroPlayer:get_pos()
    local result = self.Coromega:send_ws_cmd(("querytarget @a[name=\"%s\"]"):format(self:name()), true)
    return json.decode(result.OutputMessages[1].Parameters[1])[1]
end

--- 向玩家的聊天栏显示一条信息
--- @param msg string 消息字符串
function CoroPlayer:say(msg) self.player_kit:say(msg) end

--- 以 tellraw 的形式向指定玩家来发送 tell raw 消息，这个消息应当是一个对象
--- @param json_msg table 对象，被 json.encode 之后应该符合 tell raw 的规范
function CoroPlayer:raw_say(json_msg) self.player_kit:raw_say(json.encode(json_msg)) end

--- 获取指定玩家的输入
--- @param hint string 提示给玩家的信息
--- @param timeout number 输入超时，超时时返回为 nil
--- @return string 输入的内容
function CoroPlayer:ask(hint, timeout)
    self.player_kit:say(hint)
    local enclusure_resume = _current_coro_session_resume
    self.player_kit:intercept_just_next_input(function(chat)
        if chat == nil then
            enclusure_resume(nil)
        else
            enclusure_resume(chat.raw_msg)
        end
    end, timeout)
    return coroutine.yield()
end

--- 发送标题(副标题可以为空)
--- @param title string 标题
--- @param subtitle string|nil 副标题
function CoroPlayer:title(title, subtitle)
    if subtitle then
        self.player_kit:subtitle(subtitle, title)
    else
        self.player_kit:title(title)
    end
end

--- 发送副标题，必须有主标题 如果主标题为 nil 则不会显示 subtitle
--- @param subtitle string 副标题
--- @param title string 标题
function CoroPlayer:subtitle(subtitle, title) self.player_kit:subtitle(subtitle, title) end

--- 发送 actionbar
--- @param msg 消息
function CoroPlayer:action_bar(msg)
    self.player_kit:action_bar(msg)
end

--- 检查玩家是否满足条件 为条件限制器效果:@a[xxxxxxxx], e.g. { "m=c", "tag=!no_omega","tag=!ban" }
--- @param conditions string[] 条件字符串 列如:{ "m=c", "tag=!no_omega","tag=!ban" } 其会被拼装为指令 querytarget @a[name=玩家名，m=c,tag=!no_omega,tag=!ban]
--- @return bool
function CoroPlayer:check(conditions)
    local enclusure_resume = _current_coro_session_resume
    self.player_kit:check_condition(conditions, enclusure_resume)
    return coroutine.yield()
end

--- 获取玩家 uuid
--- 返回值:uuid 字符串，是否获得该信息
--- @return string,boolean
function CoroPlayer:uuid_string()
    local uuid, found = self.player_kit:get_uuid_string()
    return uuid, found
end

--- 获取玩家名字
--- 返回值：玩家名，是否获得该信息
--- @return string,boolean
function CoroPlayer:name()
    local name, found = self.player_kit:get_name()
    return name, found
end

--- 获取玩家 id
--- 返回值：获取玩家 id，是否获得该信息
--- @return string,boolean
function CoroPlayer:entity_unique_id()
    local eid, found = self.player_kit:get_entity_unique_id()
    return eid, found
end

--- 获取玩家登录时间
--- 返回: 登录时间 (unix time)，其类型与 :now() 一致，单位秒，是否获得该信息
--- @return number,boolean
function CoroPlayer:login_time()
    local login_time, found = self.player_kit:get_login_time()
    return login_time, found
end

--- 获取玩家平台聊天 id
--- 返回值：平台聊天 id，是否获得该信息
--- @return string,boolean
function CoroPlayer:platform_chat_id()
    local chat_id, found = self.player_kit:get_platform_chat_id()
    return chat_id, found
end

--- 获取玩家设备平台
--- 返回值：玩家设备平台，是否获得该信息
--- @return string,boolean
function CoroPlayer:build_platform()
    local build_platform, found = self.player_kit:get_build_platform()
    return build_platform, found
end

--- 获取获取玩家的皮肤 id
--- 返回值：获取玩家的皮肤 id，是否获得该信息
--- @return string,boolean
function CoroPlayer:skin_id()
    local skin_id, found = self.player_kit:get_skin_id()
    return skin_id, found
end

-- function CoroPlayer:duplicate_ability()
--     error("能力相关api因为mc修改发生变更，请参阅并使用如下新api:\newSession" ..
--         "set_build_ability\n" ..
--         "get_build_ability\n" ..
--         "set_mine_ability\n" ..
--         "get_mine_ability\n" ..
--         "set_door_and_switches_ability\n" ..
--         "get_door_and_switches_ability\n" ..
--         "set_open_container_ability\n" ..
--         "get_open_container_ability\n" ..
--         "set_attack_player_ability\n" ..
--         "get_attack_player_ability\n" ..
--         "set_attack_mobs_ability\n" ..
--         "get_attack_mobs_ability\n" ..
--         "set_operator_command_ability\n" ..
--         "get_operator_command_ability\n" ..
--         "set_teleport_ability\n" ..
--         "get_teleport_ability\n" ..
--         "get_flying_status\n" ..
--         "get_invulnerable_ability"
--     )
-- end

-- -- get properties flag
-- function CoroPlayer:properties_flag()
--     self:duplicate_ability()
-- end

-- -- get command permission level
-- function CoroPlayer:command_permission_level()
--     self:duplicate_ability()
-- end

-- -- get action permissions
-- function CoroPlayer:action_permissions()
--     self:duplicate_ability()
-- end

-- -- get op permission level
-- function CoroPlayer:op_permission_level()
--     self:duplicate_ability()
-- end

-- -- get custom stored permissions
-- function CoroPlayer:custom_stored_permissions()
--     self:duplicate_ability()
-- end

-- -- get adventure and action ability map
-- function CoroPlayer:adventure_and_action_ability_map()
--     self:duplicate_ability()
-- end

-- -- set adventure and permission ability map
-- function CoroPlayer:set_adventure_and_permission_ability_map(adventure_ability_map, action_ability_map)
--     self:duplicate_ability()
-- end

--- 读取玩家放置方块权限
--- 返回: 玩家放置方块权限，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_build_ability()
    return self.player_kit:get_build_ability()
end

--- 设置玩家放置方块权限
--- @param allow boolean 是否给予此权限
function CoroPlayer:set_build_ability(allow)
    self.player_kit:set_build_ability(allow)
    return self
end

--- 读取玩家破坏方块权限
--- 返回: 玩家破坏方块权限，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_mine_ability()
    return self.player_kit:get_mine_ability()
end

--- 设置玩家破坏方块权限
--- @param allow boolean 是否给予此权限
function CoroPlayer:set_mine_ability(allow)
    self.player_kit:set_mine_ability(allow)
    return self
end

--- 读取玩家操作门和开关权限
--- 返回: 玩家操作门和开关权限，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_door_and_switches_ability()
    return self.player_kit:get_door_and_switches_ability()
end

--- 设置玩家操作门和开关权限
--- @param allow boolean 是否给予此权限
function CoroPlayer:set_door_and_switches_ability(allow)
    self.player_kit:set_door_and_switches_ability(allow)
    return self
end

--- 读取玩家打开容器权限
--- 返回: 玩家玩家打开容器权限，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_open_container_ability()
    return self.player_kit:get_open_container_ability()
end

--- 设置玩家打开容器权限
--- @param allow boolean 是否给予此权限
function CoroPlayer:set_open_container_ability(allow)
    self.player_kit:set_open_container_ability(allow)
    return self
end

--- 读取玩家攻击其他玩家权限
--- 返回: 玩家攻击其他玩家权限，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_attack_player_ability()
    return self.player_kit:get_attack_player_ability()
end

--- 设置玩家攻击其他玩家权限
--- @param allow boolean 是否给予此权限
function CoroPlayer:set_attack_player_ability(allow)
    self.player_kit:set_attack_player_ability(allow)
    return self
end

--- 读取玩家攻击生物权限
--- 返回: 玩家攻击生物权限，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_attack_mobs_ability()
    return self.player_kit:get_attack_mobs_ability()
end

--- 设置玩家攻击生物权限
--- @param allow boolean 是否给予此权限
function CoroPlayer:set_attack_mobs_ability(allow)
    self.player_kit:set_attack_mobs_ability(allow)
    return self
end

--- 读取玩家命令权限 (同 op 权限)
--- 返回: 玩家命令权限 (同 op 权限)，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_operator_command_ability()
    return self.player_kit:get_operator_command_ability()
end

--- 设置玩家命令权限(同 op 权限)
--- @param allow boolean 是否给予此权限
function CoroPlayer:set_operator_command_ability(allow)
    self.player_kit:set_operator_command_ability(allow)
    return self
end

--- 读取玩家传送权限
--- 返回: 玩家传送权限，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_teleport_ability()
    return self.player_kit:get_teleport_ability()
end

--- 设置玩家传送权限
--- @param allow boolean 是否给予此权限
function CoroPlayer:set_teleport_ability(allow)
    self.player_kit:set_teleport_ability(allow)
    return self
end

--- 读取玩家飞行状态
--- 返回: 玩家飞行状态，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_flying_status()
    return self.player_kit:get_flying_status()
end

--- 读取玩家无敌 (不受伤害) 状态
--- 返回: 玩家无敌 (不受伤害) 状态，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:get_invulnerable_status()
    return self.player_kit:get_invulnerable_status()
end

--- 获取玩家设备id
--- 返回值：玩家设备id，是否获得该信息
--- @return string,boolean
function CoroPlayer:device_id()
    local device_id, found = self.player_kit:get_device_id()
    return device_id, found
end

--- 获取玩家实体运行时 id（只有机器人在附近时才能获取）
--- 返回值：玩家实体运行时 id，是否获得该信息
--- @return string,boolean
function CoroPlayer:entity_runtime_id()
    local entity_runtime_id, found = self.player_kit:get_entity_runtime_id()
    return entity_runtime_id, found
end

--- 获取玩家实体 metadata
--- 返回值：玩家实体 meta data ，是否获得该信息
--- @return table,boolean
function CoroPlayer:entity_metadata()
    local get_entity_metadata, found = self.player_kit:get_entity_metadata()
    return get_entity_metadata, found
end

--- 判断玩家是否为 op
--- 返回值：是否为 op，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:is_op()
    local is_op, found = self.player_kit:is_op()
    return is_op, found
end

--- 判断玩家是否在线
--- 返回值：是否在线，是否获得该信息
--- @return boolean,boolean
function CoroPlayer:is_online() return self.player_kit:still_online() end

--- 通过名字获取玩家对象
--- @param player_name string 玩家名
--- @return CoroPlayer|nil
function Coromega:get_player_by_name(player_name)
    local player_kit = self.omega.players.get_player_by_name(player_name)
    if not player_kit then return nil end
    return newCoroPlayer(player_kit, self)
end

--- 通过玩家 uuid 获取玩家对象
--- @param player_name string 玩家名
--- @return CoroPlayer|nil
function Coromega:get_player_by_uuid_string(uuid_string)
    local player_kit = self.omega.players.get_player_by_uuid_string(uuid_string)
    if not player_kit then return nil end
    return newCoroPlayer(player_kit, self)
end

--- 通过玩家名字或者 uuid 获取玩家对象
--- @param player_name string 玩家名
--- @return CoroPlayer|nil
function Coromega:get_player(uuid_string_or_name)
    local player_kit = self:get_player_by_uuid_string(uuid_string_or_name)
    if player_kit then
        return player_kit
    else
        return self:get_player_by_name(uuid_string_or_name)
    end
end

--- 获得当前所有在线的玩家
--- @return CoroPlayer[]
function Coromega:get_all_online_players()
    local player_kits = self.omega.players.get_all_online_players()
    local players = {}
    for _, player_kit in ipairs(player_kits) do
        players[#players + 1] = newCoroPlayer(player_kit, self)
    end
    return players
end

-- bot api wrapper

--- 获取机器人的名字
--- @return string 机器人的名字
function Coromega:bot_name() return self.omega.botUq.get_bot_name() end

--- 获取机器人 UUID
--- @return string 机器人 UUID
function Coromega:bot_uuid_string() return self.omega.botUq.get_bot_uuid_str() end

--- 获取机器人 unique_id
--- @return string 机器人 unique_id
function Coromega:bot_unique_id() return self.omega.botUq.get_bot_unique_id() end

--- 获取机器人 runtime_id
--- @return string 机器人 runtime_id
function Coromega:bot_runtime_id() return self.omega.botUq.get_bot_runtime_id() end

--- 获取机器人身份
--- @return string 机器人身份
function Coromega:bot_identity() return self.omega.botUq.get_bot_identity() end

--- 发送一条聊天消息，就像正常玩家那样
--- @param msg string
function Coromega:bot_say(msg) self.omega.players.bot_say(msg) end

--- 机器人当前维度
--- 维度 (0,1,2,...), 是否成功获得 0=主世界 1=地狱 2=末地 3=dm3 4=dm4. ...
--- @return number
function Coromega:bot_dimension() return self.omega.botUq.get_bot_dimension() end

--- 获取机器人当前位置 (omega 内部维护的值)
--- 返回：x, y, z, 距离上次服务器明确报告位置到目前的 tick
--- local x, y, z, out_of_sync_tick = coromega:bot_position()
--- @return number,number,number,number
function Coromega:bot_position() return self.omega.botUq.get_bot_position() end

--- 服务器当前 tick
--- 返回：tick, 是否成功获得
--- @return number,boolean
function Coromega:current_tick() return self.omega.botUq.get_current_tick() end

--- 服务器当前运行速度 (同步率)
--- 获取服务器当前运行速度 (服务器实际 tps/20)
--- 同步率，是否成功获得
--- @return number,boolean
function Coromega:sync_ratio() return self.omega.botUq.get_sync_ratio() end

--- 服务器 gamerules 列表
--- 看起来类似: {"commandblockoutput":"true","commandblocksenabled":"false" ...}
--- @return table
function Coromega:game_rules() return self.omega.botUq.get_game_rules() end

--- 服务器时间
--- 返回：server_time, 是否成功获得
--- @return number,boolean
function Coromega:server_time() return self.omega.botUq.get_server_time() end

--- 服务器一个昼夜内的时间
--- 返回：serve_day_time, 是否成功获得
--- @return number,boolean
function Coromega:server_day_time() return self.omega.botUq.get_server_day_time() end

--- 服务器白天/黑夜信息
--- 获取服务器白天/黑夜信息 (使用一个 0 ～ 1 之间的数字表示一天过去了多少)
--- 返回：day_percent, 是否成功获得
--- @return number,boolean
function Coromega:server_day_percent() return self.omega.botUq.get_server_day_percent() end

-- storage api wrapper

--- 获取 config 文件 (插件) 路径
--- e.g. coromega:config_path_of("插件","配置.json") -- ${neomega_storage}/config/插件/配置.json
--- @vararg string 任意数量的 config 后需要添加的路径, 参数可以是想要加上的子目录或者文件名
--- @return string 返回 config + 参数的文件存储路径
function Coromega:config_path_of(...)
    return self.omega.storage_path.get_config_path(...)
end

--- 获取代码文件 (插件) 路径
--- e.g. coromega:code_path_of("LuaLoader","test") -- {$storage$}/lang/LuaLoader/test
--- @vararg string 任意数量的 code 后需要添加的路径, 参数可以是想要加上的子目录或者文件名
--- @return string 返回代码文件路径加上参数路径后的新路径字符串
function Coromega:code_path_of(...)
    return self.omega.storage_path.get_code_path(...)
end

--- 获取 data 文件路径
--- e.g. coromega:data_path_of("小说文件夹","雪国冒险奇谭.txt") -- {$storage$}/data/小说文件夹/雪国冒险奇谭.txt
--- @vararg string 任意数量的 data 后需要添加的路径, 参数可以是想要加上的子目录或者文件名
--- @return string 返回 data + 参数的文件存储路径
function Coromega:data_path_of(...)
    return self.omega.storage_path.get_data_file_path(...)
end

--- 获取 cache 文件路径
--- e.g. coromega:cache_path_of("test","a") -- {$storage$}/cache/test/a
--- @vararg string 任意数量的 cache 后需要添加的路径, 参数可以是想要加上的子目录或者文件名
--- @return string 返回 cache + 参数的文件存储路径
function Coromega:cache_path_of(...)
    return self.omega.storage_path.get_cache_path(...)
end

--- 列出目录下所有文件/文件夹
--- 返回目录下文件信息和错误(如果有)
--- e.g. local all_files = coromega:path_list(coromega:path_join("storage","test"))
--- @param path string 指定路径
--- @return table,string
function Coromega:path_list(path)
    local info, err = self.omega.storage_path.list_dir(path)
    return info, err
end

--- 获取绝对路径
--- @param path string 指定路径
--- @return string
function Coromega:path_abs(path) return self.omega.storage_path.abs(path) end

--- 路径拼接
--- e.g. local path = coromega:path_join("storage","test") -- storage/test
--- @vararg string 参数：任意数量的路径字符串
--- @return string
function Coromega:path_join(...) return self.omega.storage_path.join(...) end

--- 获取文件扩展名
--- e.g. local ext = coromega:path_ext("test.lua") -- .lua
--- @param path string 指定路径
--- @return string
function Coromega:path_ext(path) return self.omega.storage_path.ext(path) end

--- 移动文件
--- 将 src 路径文件或者目录移动到 dst 路径，相当于剪切
--- @param src string
--- @param dst string
function Coromega:path_move(src, dst) return self.omega.storage_path.move(src, dst) end

--- 删除文件/目录
--- @param path string 需要删除的文件路径/目录
function Coromega:path_remove(path) return self.omega.storage_path.remove(path) end

--- 判断路径是否存在
--- @param path string 需要判断的文件路径/目录
function Coromega:path_exist(path) return self.omega.storage_path.exist(path) end

-- stoarge api wrapper

--- 将 data 数据以 json 形式保存到 path 路径的文件中去
--- @param path string 需要保存的文件路径
--- @param data table|any
function Coromega:save_data(path, data) self.omega.storage.save(path, data) end

--- 从 path 路径读取 json 数据
--- @param path string 需要读取的路径
--- @return table|any
function Coromega:load_data(path) return self.omega.storage.read(path) end

--- 将文本/字符串保存到 path 路径的文件中去
--- @param path string 需要保存的文件路径
--- @param data string
function Coromega:save_text(path, data) self.omega.storage.save_text(path, data) end

--- 从 path 路径读取文本数据
--- @param path string 需要读取的路径
--- @return string|nil
function Coromega:load_text(path) return self.omega.storage.read_text(path) end

--- @class WrappedKVDB
local WrappedKVDB = { _cname = "WrappedKVDB" }

--- @param db string
--- @return WrappedKVDB
local function newWrappedKVDB(db)
    local instance = { db = db }
    setmetatable(instance, { __index = WrappedKVDB })
    return instance
end

--- 根据 key 读取对应的数据
--- @param key string
--- @return any|nil
function WrappedKVDB:get(key)
    local value = self.db:get(key)
    return json.decode(value)
end

--- 保存一组数据
--- @param key string
--- @param value any
function WrappedKVDB:set(key, value) self.db:set(key, json.encode(value)) end

--- 删除一组数据
--- @param key string
function WrappedKVDB:delete(key) self.db:delete(key) end

--- 使用一个函数遍历数据库内所有数据，函数的返回为是否继续遍历
--- e.g.
--- db:iter(function(k,v)
---    print(k,v)
---    local next=true
---    return next
--- end)
--- @param fn function(key:string,val:any)
function WrappedKVDB:iter(fn)
    self.db:iter(function(k, v)
        return fn(k, json.decode(v))
    end)
end

--- 将一个数据库内的数据导入到另一个数据库
--- e.g.
--- local src_db=coroemag:key_value_db("src","json")
--- local dst_db=coromega:key_value_db("dst","level")
--- src_db:migrate_to(target_db)
--- @param target_db WrappedKVDB
function WrappedKVDB:migrate_to(target_db)
    self.db:migrate_to(target_db.db)
end

local SharedMap = { _cname = "SharedMap" }
local function newSharedMap(shared_map)
    local instance = {
        shared_string_kv_map = shared_map
    }
    setmetatable(instance, { __index = SharedMap })
    return instance
end

-- local val = sm:get("key")
function SharedMap:get(key)
    if _coro_running then
        local enclusure_resume = _current_coro_session_resume
        self.shared_string_kv_map.get(key, function(result)
            enclusure_resume(result)
        end)
        return coroutine.yield()
    else 
        return self.shared_string_kv_map.block_get(key)
    end
end

-- local old = sm:set("key",value)
function SharedMap:set(key, value)
    if _coro_running then
        local enclusure_resume = _current_coro_session_resume
        self.shared_string_kv_map.set(key, json.encode(value), function(result)
            enclusure_resume(result)
        end)
        return coroutine.yield()
    else 
        return self.shared_string_kv_map.block_set(key, json.encode(value))
    end
end

-- local old = sm:delete("key")
function SharedMap:delete(key)
    if _coro_running then
        local enclusure_resume = _current_coro_session_resume
        self.shared_string_kv_map.delete(key, function(result)
            enclusure_resume(result)
        end)
        return coroutine.yield()
    else 
        return self.shared_string_kv_map.block_delete(key)
    end
end

-- local data, loaded = sm:load_or_store("key", "value")
function SharedMap:load_or_store(key, value)
    if _coro_running then
        local enclusure_resume = _current_coro_session_resume
        self.shared_string_kv_map.load_or_store(key, json.encode(value), function(result)
            enclusure_resume(result.data, result.loaded)
        end)
        return coroutine.yield()
    else 
        local result = self.shared_string_kv_map.block_load_or_store(key, json.encode(value))
        return result.data, result.loaded
    end
end

-- local old = sm:compare_and_swap("key","old_val", "new_val")
function SharedMap:compare_and_swap(key, old, new)
    if _coro_running then
        local enclusure_resume = _current_coro_session_resume
        self.shared_string_kv_map.compare_and_swap(key, json.encode(old), json.encode(new), function(result)
            enclusure_resume(result)
        end)
        return coroutine.yield()
    else 
        return self.shared_string_kv_map.block_compare_and_swap(key, json.encode(old), json.encode(new))
    end
end

-- sm:iter(function(k,v)
--    print(k,v)
--    local next=true
--    return next
-- end)
function SharedMap:iter(fn)
    if _coro_running then
        local enclusure_resume = _current_coro_session_resume
        self.shared_string_kv_map.iter(
            function(k, v)
                return fn(k, json.decode(v))
            end,
            function(result)
                enclusure_resume(result)
            end
        )
        return coroutine.yield()
    else 
        return self.shared_string_kv_map.block_iter(function(k, v)
            return fn(k, json.decode(v))
        end)
    end
end

-- local sm = Coromega:shared_map()
function Coromega:shared_map()
    return newSharedMap(self.omega.share.get_shared_string_kv_map())
end


---@class Pos
---@field x integer
---@field y integer
---@field z integer
local pos_emmylua

--- 从服务器请求一个区域的所有方块<br>
--- 注意，虽然函数名为 request_structure 但是实际读取出的数据是以 canvas 形式保存在内存中的<br>
--- 虽然背后是一个复杂的算法使之可以不受范围限制，但实际不建议这么干<br>
--- 更详细的方块读取操作请移步 apply_reader_to_blocks<br>
--- e.g.
--- ```lua
---   local start_pos = { x = 10001, y = 100, z = 10000 }
---   local region_size= { x = 14, y = 3, z = 4 }
---   local move_bot = true
---   local canvas = coromega:request_structure(start_pos, region_size, move_bot)
--- ```
--- @param start_pos Pos 起始坐标
--- @param region_size table 范围
--- @param move_bot boolean 当为 true 时，机器人会移动到目标区域附近。为 false 时，机器人不会移动，此时若目标区域未加载 (例如没有玩家在附近) 则会导致请求失败
--- @return Canvas
function Coromega:request_structure(start_pos, region_size, move)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.request_structure(start_pos, region_size, move, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

--- 将机器人的背包物品移动到指定位置的容器中
--- @param container_pos Pos 容器坐标
--- @param move_operations table<integer,integer> 背包格子号到容器格子号的映射
--- @return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local move_operations={
--     [0] = 0,    -- 0号快捷栏移动到容器第1格
--     [9] = 1,    -- 9号背包栏移动到容器第2格
-- }
-- local err = coromega:move_item_to_container({x=-6,y=-60,z=-24}, move_operations)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:move_item_to_container(container_pos, move_operations)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.move_item_to_container(container_pos, move_operations, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---将机器人指定快捷物品栏里的物品改名
---@param anvil_pos Pos 铁砧坐标
---@param slot integer 快捷物品栏格子号
---@param new_name string 新名字
---@param auto_gen_anvil boolean 是否自动生成铁砧
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:rename_item({x=-6,y=-60,z=-24},0,"line1\nline2\nline3",true)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:rename_item(anvil_pos, slot, new_name, auto_gen_anvil)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.rename_item_with_anvil(anvil_pos, slot, new_name, auto_gen_anvil, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---将机器人指定快捷物品栏里的物品扔出
---@param slot integer 要扔出的物品所在快捷栏的槽位号（可选0~8）
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:drop_item(0)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:drop_item(slot)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.drop_item_from_hot_bar(slot, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---将机器人指定快捷物品栏里的物品附魔
---@param slot integer 快捷物品栏格子号
---@param enchants table<integer,integer> 要附魔附魔的效果ID及其对应的等级
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:enchant_item(0,{
--     [11] = 1,   -- 将物品附魔1级节肢克星
--     [12] = 2,   -- 将物品附魔2级击退
-- })
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
--- ---
--- 附魔id效果表
-- |编号|附魔效果|
-- |----|----|
-- |0|保护|
-- |1|火焰保护|
-- |2|摔落缓冲|
-- |3|爆炸保护|
-- |4|弹射物保护|
-- |5|荆棘|
-- |6|水下呼吸|
-- |7|深海探索者|
-- |8|水下速掘|
-- |9|锋利|
-- |10|亡灵杀手|
-- |11|节肢杀手|
-- |12|击退|
-- |13|火焰附加|
-- |14|抢夺|
-- |15|效率|
-- |16|精准采集|
-- |17|耐久|
-- |18|时运|
-- |19|力量|
-- |20|冲击|
-- |21|火矢|
-- |22|无限|
-- |23|海之眷顾|
-- |24|饵钓|
-- |25|冰霜行者|
-- |26|经验修补|
-- |27|绑定诅咒|
-- |28|消失诅咒|
-- |29|穿刺|
-- |30|激流|
-- |31|忠诚|
-- |32|引雷|
-- |33|多重射击|
-- |34|穿透|
-- |35|快速装填|
-- |36|灵魂疾行|
-- |37|迅捷潜行|
--- 如果输入非上述数字则视为效果`魔咒`
function Coromega:enchant_item(slot, enchants)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.enchant_item(slot, enchants, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---生成物品到指定快捷栏
---@param item_info string 物品nbt的json字符串数据
---@param slotID integer 快捷物品栏格子号
---@param anvil_pos Pos 如果要用到铁砧，将在该坐标使用
---@param next_container_pos Pos 如果要进行容器操作，将在该坐标使用
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:make_item(data,0,{x=-6,y=-60,z=-24},{x=-8,y=-60,z=-24})
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:make_item(item_info, slotID, anvil_pos, next_container_pos)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.make_item(item_info, slotID, anvil_pos, next_container_pos, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---使用对应快捷栏的物品
---@param slotID integer 快捷物品栏格子号
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:use_item(0)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:use_item(slotID)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.use_hotbar_item(slotID, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---对某个方块使用对应快捷栏的物品
---@param block_pos Pos 方块坐标
---@param blockNEMCRuntimeID integer|nil 方块RuntimeID，提供后运行速度更快
---@param face integer 对方块的哪一面使用
---@param slot integer 快捷物品栏格子号
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:use_item_on_block({x=-7,y=-56,z=-27},0,0)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
--- ---
-- |face编号|方向|
-- |----|----|
-- |0|y-|
-- |1|y+|
-- |2|z-|
-- |3|z+|
-- |4|x-|
-- |5|x+|
function Coromega:use_item_on_block(block_pos, face, slot, blockNEMCRuntimeID)
    local enclusure_resume = _current_coro_session_resume
    if blockNEMCRuntimeID == nil then
        self.omega.bot_action.use_hotbar_item_on_block_without_rid(block_pos, face, slot, function(result)
            enclusure_resume(result)
        end)
    else
        self.omega.bot_action.use_hotbar_item_on_block(block_pos, blockNEMCRuntimeID, face, slot, function(result)
            enclusure_resume(result)
        end)
    end
    return coroutine.yield()
end

---在指定偏移位置对某个方块使用对应快捷栏的物品
---@param block_pos Pos 方块坐标
---@param bot_offset Pos 机器人偏移坐标
---@param blockNEMCRuntimeID integer|nil 方块RuntimeID，提供后运行速度更快
---@param face integer 对方块的哪一面使用
---@param slot integer 快捷物品栏格子号
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:use_item_on_block_with_bot_offset({x=-7,y=-56,z=-27},{x=1,y=0,z=0},1,0)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
--- ---
-- |face编号|方向|
-- |----|----|
-- |0|y-|
-- |1|y+|
-- |2|z-|
-- |3|z+|
-- |4|x-|
-- |5|x+|
function Coromega:use_item_on_block_with_bot_offset(block_pos, bot_offset, face, slot, blockNEMCRuntimeID)
    local enclusure_resume = _current_coro_session_resume
    if blockNEMCRuntimeID == nil then
        self.omega.bot_action.use_hotbar_item_on_block_with_bot_offset_without_rid(block_pos, bot_offset, face, slot,
            function(result)
                enclusure_resume(result)
            end)
    else
        self.omega.bot_action.use_hotbar_item_on_block_with_bot_offset(block_pos, bot_offset, blockNEMCRuntimeID, face,
            slot, function(result)
            enclusure_resume(result)
        end)
    end
    return coroutine.yield()
end

---将机器人某个物品栏物品移动到另一个物品栏(快捷栏和背包都可以)
---@param source_slot integer 要移动的物品栏格子号,移动前必须有东西
---@param target_slot integer 移动到的物品栏格子号,移动前不能有东西
---@param count integer 移动数量
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:move_item(0,9,1) -- 将第一格快捷栏中的物品移动一格到背包第一格
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:move_item(source_slot, target_slot, count)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.move_item_inside_hotbar_or_inventory(source_slot, target_slot, count, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

--- 将机器人主手切换到相应快捷栏
--- @param slot integer 快捷物品栏格子号
--- @return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local err = coromega:select_hotbar(0)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:select_hotbar(slot)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.select_hotbar(slot, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---获取目标坐标的方块到对应快捷栏
---@param block_pos table<string,number> 方块坐标
---@param target_hotbar integer 快捷物品栏格子号
---@param retry_times integer 失败重试次数
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local block_position = {x=0, y=64, z=0}
-- local err = coromega:pick_block(block_position, 0, 3)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:pick_block(block_pos, target_hotbar, retry_times)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.pick_block(block_pos, target_hotbar, retry_times, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---破坏目标坐标的方块拾取掉落物到对应快捷栏
---@param block_pos table<string,number> 方块坐标
---@param recover_block boolean 是否恢复方块
---@param retry_times integer 失败重试次数
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local block_position = {x=0, y=64, z=0}
-- local err = coromega:break_and_pick_block(block_position, 0, true, 3)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ```
function Coromega:break_and_pick_block(block_pos, target_hotbar, recover_block, retry_times)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.block_break_and_pick_in_hotbar(block_pos, target_hotbar, recover_block, retry_times,
        function(result)
            enclusure_resume(result)
        end)
    return coroutine.yield()
end

---获取指定物品栏内物品的信息
---@param slot integer 物品栏槽位号
---@param windows integer|nil 指定窗口，不指定默认为0
---@return table 物品信息, boolean 是否成功获取
--- ---
--- ```lua
--- -- e.g.
-- local item_info, success = coromega:get_inventory_content(0)
-- if success then
--     coromega:print(("物品信息：%s"):format(json.encode(item_info)))
-- else
--     coromega:print("获取物品信息失败")
-- end
--- ``` 
function Coromega:get_inventory_content(slot, windows)
    local result = self.omega.bot_action.get_inventory_content(slot, type(windows) == "number"and windows or 0)
    return result.info, result.ok
end

--- 设置指定坐标的结构方块的内容
---@param block_pos table<string,number> 方块坐标
--- @param settings table<string,any> nbt表
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local block_position = {x=0, y=64, z=0}
-- local err = coromega:set_structure_block_data(block_position, structure_settings)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ``` 
function Coromega:set_structure_block_data(block_pos, settings)
    return self.omega.bot_action.set_structure_block_data(block_pos, settings)
end

--- 对指定位置下的容器放置内容
--- @param container_pos table 容器位置
--- @param container_data_json string 容器内容(参见 bot action 章节了解如何生成)
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local container_position = {x=-6, y=-60, z=-24}
-- local err = coromega:set_container_content(container_position, container_data)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ``` 
function Coromega:set_container_content(container_pos, container_data_json)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.set_container_content(container_pos, container_data_json, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

---根据内容写成书放到对应快捷栏
---@param slotID integer 快捷物品栏格子号
---@param pages string[] 每页内容
---@param title string 书名
---@param author string 作者名
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local slot_id = 0
-- local pages_content = {
--     "这是第一页的内容。",
--     "这是第二页的内容。",
--     "这是第三页的内容。"
-- }
-- local book_title = "我的书"
-- local book_author = "无名作者"
-- local err = coromega:write_book(slot_id, pages_content, book_title, book_author)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ``` 
function Coromega:write_book(slotID, pages, title, author)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.write_book_and_close(slotID, pages, title, author, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

--- 对指定坐标的物品展示框放入指定快捷栏中的物品
--- @param block_pos table 物品展示框位置
--- @param slotID integer 快捷物品栏格子号
--- @param rotation integer 旋转角度
---@return string|nil 报错信息
--- ---
--- ```lua
--- -- e.g.
-- local item_frame_position = {x=-6, y=-60, z=-24}
-- local slot_id = 0
-- local rotation= 0 -- 1 或者 45 或者 2 或者 90, 小于 45 的值会被*45处理
-- local err = coromega:place_item_frame_item(item_frame_position, slot_id,rotation)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ``` 
function Coromega:place_item_frame_item(block_pos, slotID,rotation)
    if not rotation then 
        rotation=0
    end
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.place_item_frame_item(block_pos, slotID,rotation, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

--- 放置一个箱子并放置内容
--- @param pos table 放置位置
--- @param container_data_json string 容器内容(参见 bot action 章节了解如何生成)
--- @param container_block string 容器方块名
--- @return string|nil
--- ---
--- ```lua
--- -- e.g.
-- local container_position = {x=-6, y=-60, z=-24}
-- local container_block_name = "chest [\"facing_direction\"=4]"
-- local err = coromega:gen_container(container_position, container_data, container_block_name)
-- coromega:print(("运行结果：%s"):format(err or "成功"))
--- ``` 
function Coromega:gen_container(pos, container_data_json, container_block)
    local enclusure_resume = _current_coro_session_resume
    self.omega.bot_action.gen_container(pos, container_data_json, container_block, function(result)
        enclusure_resume(result)
    end)
    return coroutine.yield()
end

--- 打开或创建一个 键-值 数据库
--- 数据库类型可以为以下三种之一:
--- 1. "","text_log" 默认的实现
---    折中的实现，不会因为意外关闭导致数据库完全损坏，而且也是以可读方式存在的
---    手动修改数据库文件的时候需要先改log文件，log 文件内容必须遵循特定规则
---    每次启动时都会把数据保存内存中，因此正式使用时只有少量数据时适合使用这个数据
--- 2. "level"
---    leveldb, 显然是最好的实现，然而，内部数据都是以二进制存储，无法阅读
---    leveldb 的 file lock 被移除，因此需要用其他手段保证不会同时写一个文件
---    适合在正式使用时使用
--- 3. "json"
---    最慢的最不安全的实现，每次启动时都会把数据保存内存中，当数据变更时更新 json 文件
---    若在保存的时候程序被关闭，可能导致数据库完全损坏
---    好处是内容便于阅读和修改，只建议在开发和调试时使用
--- @param path string 数据库路径
--- @param db_type string|nil 数据库类型
--- @return WrappedKVDB
function Coromega:key_value_db(path, db_type)
    if db_type == nil then
        db_type = ""
    end
    return newWrappedKVDB(self.omega.storage.get_kv_db(path, db_type))
end

-- builder api wrapper

--- 在 pos 位置放置一个方块
--- 在被调用时会立即放置方块，调用者应该自行确保该方块在机器人可放置范围内，且所在区块已经加载
--- e.g. place_block({ x = 1, y = 2, z = 3 }, "stone", "0")
--- @param pos table
--- @param block_name string
--- @param block_data int|string
function Coromega:place_block(pos, block_name, block_data)
    block_data = ("%s"):format(block_data)
    self.omega.cmds.send_wo_cmd(("setblock %d %d %d %s %s"):format(pos.x, pos.y, pos.z, block_name, block_data))
end

--- 在 pos 位置放置命令块
--- 在被调用时会立即放置方块，调用者应该自行确保该方块在机器人可放置范围内，且所在区块已经加载
--- coromega:place_command_block(
---     { x = 884, y = 73, z = 829 },
---     "repeating_command_block", 0,
---     {
---         need_red_stone = true,
---         conditional = true,
---         command = "list @a",
---         name = "列出所有玩家",
---         tick_delay = 10,
---         track_output = true,
---         execute_on_first_tick = true,
---     }
--- )
--- @param pos table
--- @param block_name string
--- @param block_data int|string
--- @param option table
function Coromega:place_command_block(pos, block_name, block_data, option)
    block_data = ("%s"):format(block_data)
    return self.omega.builder.place_command_block(pos, block_name, block_data,
        option.need_red_stone, option.conditional,
        option.command, option.name,
        option.tick_delay, option.track_output, option.execute_on_first_tick
    )
end

--- 在 pos 位置放置一个告示牌
--- e.g.
--- 在 1,-60,0 位置放置一个告示牌，上面写着 240! 同时发光
--- local err = coromega:place_sign(
---       { x = 1, y = -60, z = 0 }, -- 坐标
---       "jungle_standing_sign 0",
---       "§a§l240!",
---       true
---   )
---   if err then
---       coromega:print(err)
---   end
--- @param pos table
--- @param block_name string
--- @param text string 告示牌上的字
--- @param lighting bool 是否发光
function Coromega:place_sign(pos, block_name, text, lighting)
    return self.omega.builder.place_sign(pos, block_name, text, lighting)
end

-- build structure/canvas, then call callback when progress increased
-- :when_progress_increased_by_build(
--     target_structure_or_canvas,                  --需要被导的东西
--     target_structure_or_canvas:get_start_pos(),  --被导的东西的起始位置
--     target_structure_or_canvas:get_end_pos(),    --被导的东西的结束位置
--     { x = 31000, y = 100, z = 11000 },           --导入到的位置(租赁服中)
--     {
--         speed = 2000,                            --导入速度
--         incremental = false,                     --增量构建(false)
--         force_use_block_state = false,           --强制使用block state(false),注：即时这里设置false，如果struceture中use_block_state为true，也会使用block state
--         ignore_nbt_block = false,                --是否忽略nbt方块(false)
--         clear_target_block = false,              --导入时清除目标位置的方块(false)
--         clear_dropped_item = false,              --导入时清理掉落物(false)，注: 清理范围为整个租赁服，不止是导入的建筑范围
--         auto_reverse = true,                      --（重新开始时回退跃点）(true)
--         start_hop=0,                             --开始跃点(0)
--      }
-- )

--- 调用该 API 时，由 omega builder 负责方块正确的构建
--- 您需要有对应的权限
--- e.g.
---  coromega:when_progress_increased_by_build(
---  target_structure_or_canvas,                  --需要被导的东西
---  target_structure_or_canvas:get_start_pos(),  --被导的东西的起始位置
---  target_structure_or_canvas:get_end_pos(),    --被导的东西的结束位置
---  { x = 31000, y = 100, z = 11000 },           --导入到的位置 (租赁服中)
---  {
---      speed = 2000,                            --导入速度
---      incremental = false,                     --增量构建 (false)
---      force_use_block_state = false,           --强制使用 block state(false),注：即时这里设置 false，如果 struceture 中 use_block_state 为 true，也会使用 block state
---      ignore_nbt_block = false,                --是否忽略 nbt 方块 (false)
---      clear_target_block = false,              --导入时清除目标位置的方块 (false)
---      clear_dropped_item = false,              --导入时清理掉落物 (false)，注：清理范围为整个租赁服，不止是导入的建筑范围
---      auto_reverse = true,                      --（重新开始时回退跃点）(true)
---      start_hop=0,                             --开始跃点 (0)
---  }
---  ):start_new(function(total, current)
---  coromega:print(("progress: %d/%d"):format(total, current))
---  end)
--- @param aread_chunk AreadChunk
--- @param start_pos table
--- @param end_pos table
--- @param target_pos table
--- @param option table
function Coromega:when_progress_increased_by_build(aread_chunk, start_pos, end_pos, target_pos, option)
    local progress_poller = self.omega.builder.build(aread_chunk, start_pos, end_pos, target_pos,
        option.speed, option.incremental, option.force_use_block_state,
        option.ignore_nbt_block, option.clear_target_block, option.clear_dropped_item,
        option.auto_reverse, option.start_hop
    )
    self.mux_poller:poll(progress_poller)
    local factory = newSessionFactory()
    self.cbs[progress_poller] = function(event)
        local total = event.total
        local current = event.current
        if total == current then
            self.cbs[progress_poller] = nil
        end
        factory:on_new_session(total, current)
    end
    return factory
end

-- 插件间通信 api wrapper
--- 调用具有 api_name 的跨插件 api，调用参数为 args, 并返回调用结果
--- @param func string  字符串形式的跨插件 api 名
--- @param args table|any 可以被 json.encode 处理的参数
--- @param timeout number|nil 超时，当超时时，返回 nil,"context deadline exceeded"
--- @return any,string|nil
function Coromega:call_other_plugin_api(func, args, timeout)
    local enclusure_resume = _current_coro_session_resume
    self.omega.flex.call(func, json.encode(args), function(result, err)
        enclusure_resume(json.decode(result), err)
    end, timeout)
    return coroutine.yield()
end

--- 调用具有 api_name 的跨插件 api，调用参数为 args, 不等待结果
--- @param func string  字符串形式的跨插件 api 名
--- @param args table|any 可以被 json.encode 处理的参数
function Coromega:call_other_plugin_api_no_result(func, args)
    self.omega.flex.call(func, json.encode(args), nil)
end

--- 向某个指定话题发布消息
--- @param topic string  话题名
--- @param data table|any 可以被 json.encode 处理的参数
function Coromega:publish_info(topic, data)
    self.omega.flex.pub(topic, json.encode(data))
end

-- cqhttp api wrapper

--- 向 cqhttp 发送消息, target 的形式诸如 群聊:xxxxx, 频道:xxx(频道名):xxx(聊天室名)
--- e.g. coromega:send_cqhttp_message("群聊:548589654", "hello world 1")
--- @param target string 诸如 群聊:xxxxx, 频道:xxx(频道名):xxx(聊天室名)
--- @param message string 消息内容
function Coromega:send_cqhttp_message(target, message)
    self.omega.cqhttp.send_to(target, message)
end

--- 向默认发送列表发送 cqhttp 消息
--- @param message string 消息内容
function Coromega:send_cqhttp_message_to_default(message)
    self.omega.cqhttp.send_to_default(message)
end

--- 向指定 qq 号 发送私聊消息
--- @param id number qq号
--- @param message string 消息内容
function Coromega:send_cqhttp_message_to_id(id, message)
    local enclusure_resume = _current_coro_session_resume
    self.omega.cqhttp.send_private_message(id, message, enclusure_resume)
    return coroutine.yield()
end

--- 发送群消息, id 为群号
--- @param group_id number 群号
--- @param message string 消息内容
function Coromega:send_cqhttp_message_to_group(group_id, message)
    local enclusure_resume = _current_coro_session_resume
    self.omega.cqhttp.send_group_message(group_id, message, enclusure_resume)
    return coroutine.yield()
end

--- 发送频道消息, guild_id 为频道号, chanel_id 为聊天室号，因为这个获取较为困难，建议直接使用 send_cqhttp_message
--- 指定频道号指定聊天室发送消息
--- @param guild_id number 频道号
--- @param chanel_id number 聊天室号
--- @param message string 消息内容
function Coromega:send_cqhttp_message_to_guild(guild_id, chanel_id, message)
    local enclusure_resume = _current_coro_session_resume
    self.omega.cqhttp.send_guild_message(guild_id, chanel_id, message, enclusure_resume)
    return coroutine.yield()
end

--- 获取群成员信息
--- @param group_id number 群号
--- @return table
function Coromega:get_cqhttp_group_members_info(group_id)
    local enclusure_resume = _current_coro_session_resume
    self.omega.cqhttp.get_group_members_request(group_id, enclusure_resume)
    return coroutine.yield()
end

--- 获取已加入的频道信息
--- @return table
function Coromega:get_cqhttp_joined_guilds()
    local enclusure_resume = _current_coro_session_resume
    self.omega.cqhttp.get_guild_list(enclusure_resume)
    return coroutine.yield()
end

--- 获取指定频道号频道信息
--- @param guild_id number 频道号
--- @return table
function Coromega:get_cqhttp_guild_channels(guild_id)
    local enclusure_resume = _current_coro_session_resume
    self.omega.cqhttp.get_guild_channels(guild_id, enclusure_resume)
    return coroutine.yield()
end

--- 获取指定频道号指定成员信息
--- @param guild_id number 频道号
--- @param user_id string 成员号
function Coromega:get_cqhttp_guild_member(guild_id, user_id)
    local enclusure_resume = _current_coro_session_resume
    self.omega.cqhttp.get_guild_member_profile(guild_id, user_id, enclusure_resume)
    return coroutine.yield()
end

--- HTTP request
--- e.g.
--- local response, error_message = coromega:http_request("GET", "http://example.com", {
---     query = "page=1",
---     timeout = "30s",
---     headers = {
---         Accept = "*/*"
---     }
--- })
--- if error_message then
---     print("request error: ", error_message)
--- else
---     print("request response: ", response)
---     print("request response status_code: ", response.status_code)
---     print("request response headers: ", response.headers)
---     print("request response body_size: ", response.body_size)
---     print("request response body: ", response.body)
---     print("request response cookies: ", response.cookies)
---     print("request response url: ", response.url)
--- end
--- @param method string 方法 get/post/put/delete/head/patch
--- @param address string 字符串形式地址
--- @param option table|nil 可不填，或参考 https://github.com/cjoudrey/gluahttp 的选项，http 模块为 gluahttp 的异步版本
function Coromega:http_request(method, address, option)
    local enclusure_resume = _current_coro_session_resume
    self.omega.async_http.request(method, address, option, enclusure_resume)
    return coroutine.yield()
end

--- 等效于：http_request("get",url,option)
--- @param address string 字符串形式地址
--- @param option table|nil 可不填，或参考 https://github.com/cjoudrey/gluahttp 的选项，http 模块为 gluahttp 的异步版本
function Coromega:http_get(address, option) return self:http_request("get", address, option) end

--- 等效于：http_request("post",url,option)
--- @param address string 字符串形式地址
--- @param option table|nil 可不填，或参考 https://github.com/cjoudrey/gluahttp 的选项，http 模块为 gluahttp 的异步版本
function Coromega:http_post(address, option) return self:http_request("post", address, option) end

--- 等效于：http_request("put",url,option)
--- @param address string 字符串形式地址
--- @param option table|nil 可不填，或参考 https://github.com/cjoudrey/gluahttp 的选项，http 模块为 gluahttp 的异步版本
function Coromega:http_put(address, option) return self:http_request("put", address, option) end

--- 等效于：http_request("deleta",url,option)
--- @param address string 字符串形式地址
--- @param option table|nil 可不填，或参考 https://github.com/cjoudrey/gluahttp 的选项，http 模块为 gluahttp 的异步版本
function Coromega:http_delete(address, option) return self:http_request("delete", address, option) end

--- 等效于：http_request("head",url,option)
--- @param address string 字符串形式地址
--- @param option table|nil 可不填，或参考 https://github.com/cjoudrey/gluahttp 的选项，http 模块为 gluahttp 的异步版本
function Coromega:http_head(address, option) return self:http_request("head", address, option) end

--- 等效于：http_request("patch",url,option)
--- @param address string 字符串形式地址
--- @param option table|nil 可不填，或参考 https://github.com/cjoudrey/gluahttp 的选项，http 模块为 gluahttp 的异步版本
function Coromega:http_patch(address, option) return self:http_request("patch", address, option) end

-- 一个 Coromega 用于将 Omega 的异步回调转换为 coroutine 形式
-- 对于每个可能产生新的 Session 的入口点, 都设置一个 SessionFactory

local function newCoromega(omega)
    _ud2lua = omega.user_data_to_lua_value
    ---@class CorOmegaField
    local instance = {
        omega = omega,
        config = _ud2lua(omega.config:user_data()), -- 从配置文件中读取的配置
        enabled = true,
        mux_poller = omega.listen.make_mux_poller(),
        maintained_cbs = {}, -- adapt old code
        cbs = {},            -- adapt old code
        -- running = false
    }
    setmetatable(instance, { __index = Coromega })
    local module_level_event_sources = {
        [omega.cmds.resp] = function(event) event.cb(event.output) end,
        [omega.players.resp] = function(event) event.cb(event.output) end,
        [omega.flex.resp] = function(event) event.cb(event.output, event.err) end,
        [omega.system.resp] = function(event) event.cb(event.output) end,
        [omega.cqhttp.resp] = function(event) event.cb(event.output) end,
        [omega.websocket.resp] = function(event) event.cb(event.output) end,
        [omega.async_http.resp] = function(event) event.cb(event.resp, event.err) end,
        [omega.bot_action.resp] = function(event) event.cb(event.output) end,
        [omega.share.resp] = function(event) event.cb(event.output) end,
    }
    for k, v in pairs(module_level_event_sources) do
        instance:new_event_source(k, v)
    end
    return instance
end

--- 升级文件配置
--- e.g.
--- 当您升级了您的代码后，代码可能需要一些旧配置中原本不存在的配置项<br>
---     此方法存在的意义就是允许您修改配置文件，使之与新代码对应<br>
---     例如，在上述配置文件中，您希望为配置文件添加 "记分板显示名" 这一选项，您可以这么做：
---   ```lua
---   local version=coromega.config.Version
---   if version=="0.0.1" then -- 只有当配置文件版本较旧的时候才升级
---       coromega.config["记分板显示名"]="金币"
---       coromega.config.Version="0.0.2"
---       coromega:update_config(coromega.config)
---   end
---   local scoreboard_display_name=coromega.config["记分板显示名"]
---   ```
---   当您的插件运行时，配置文件将被更新为:
---   ```json
---   {
---     "名称": "购买.lua",
---     "描述": "允许用户购买物品",
---     "是否禁用": false,
---     "来源": "LuaLoader",
---     "配置": {
---       "Version": "0.0.2",
---       "记分板名": "coin",
---       "物品清单": [
---         { "名称": "苹果", "MC 名称": "apple", "价格": 10 },
---         { "名称": "石头", "MC 名称": "stone", "价格": 5 },
---         { "名称": "玻璃", "MC 名称": "glass", "价格": 20 }
---       ],
---       "记分板显示名": "金币"
---     }
---   }
--- @param new_config table 可被 json.encode 正确处理的任意数据
function Coromega:update_config(new_config)
    self.omega.config:upgrade(new_config)
end

--- 获取插件名字
--- @return string
function Coromega:get_plugin_name()
    return string.gsub(self.omega.config:get_plugin_name(), "%.lua$", "")
end

function Coromega:new_event_source(k, v)
    self.maintained_cbs[k] = v
    self.mux_poller:poll(k)
end

--- 设置后台 (终端) 菜单
--- - 范围：协程外
--- - 说明：在后台 (终端) 中添加一个菜单入口，当菜单被触发时，启动一个新的协程并运行指定处理函数
--- - 参数：option, 其结构为
---   - triggers: 触发词字符串列表，当输入符合其中任意一个时，菜单被触发，在后台输入？时显示第一个字符串
---   - argument_hint: 字符串，无实际影响，在渲染中起参数提示作用
---   - usage: 字符串，无实际影响，在渲染中起功能提示作用
--- - 返回：监听器，监听器的处理函数的参数为被切割 (按空格切割) 后，且去除触发词的输入
--- ```lua
--- coromega:when_called_by_terminal_menu({
---     triggers = { "coro", "coro_cmd", "coro_term_cmd" },
---     argument_hint = "[cmd]",
---     usage = "coro_test",
--- }):start_new(function(input)
---     local cmd = table.concat(input, " ")
---     if cmd == "" then
---         cmd = coromega:backend_input("please input cmd: ")
---     end
---     coromega:print(("cmd: %s"):format(cmd))
---     local result = coromega:send_ws_cmd(cmd, true)
---     coromega:print(("cmd result: %s"):format(json.encode(result)))
--- end)
--- ```
--- @param options table
--- @return SessionFactory
function Coromega:when_called_by_terminal_menu(options)
    local menu_poller = self.omega.menu.add_backend_menu_entry({
        triggers = options.triggers,
        argument_hint = options.argument_hint,
        usage = options.usage,
    })

    local factory = newSessionFactory()
    self:new_event_source(menu_poller, function(...) factory:on_new_session(...) end)
    return factory
end

--- 设置游戏菜单
--- - 范围：协程外
--- - 说明：在游戏中 neomega 菜单 中添加一个菜单入口，当菜单被触发时，启动一个新的协程并运行指定处理函数
--- - 参数：option, 其结构为
---   - triggers: 触发词字符串列表，当输入符合其中任意一个时，菜单被触发，当唤起游戏菜单时显示第一个字符串
---   - argument_hint: 字符串，无实际影响，在渲染中起参数提示作用
---   - usage: 字符串，无实际影响，在渲染中起功能提示作用
--- - 返回：监听器，监听器的处理函数的参数为 chat 对象
--- ```lua
--- coromega:when_called_by_game_menu({
---     triggers = { "coro", "coro_cmd", "coro_game_cmd" },
---     argument_hint = "[cmd]",
---     usage = "coro_test",
--- }):start_new(function(chat)
---     local cmd = table.concat(chat.msg, " ")
---     print(json.encode(chat))
---     local player = coromega:get_player(chat.name)
---     while (cmd == "") do
---         local chat = player:ask("请输入命令：")
---         cmd = chat.raw_msg
---         if cmd == "" then
---             player:say("命令不能为空")
---         end
---     end
---     coromega:print(("cmd: %s"):format(cmd))
---     local result = coromega:send_ws_cmd(cmd, true)
---     player:say(("cmd result: %s"):format(json.encode(result)))
--- end)
--- ```
--- @param options table
--- @return SessionFactory
function Coromega:when_called_by_game_menu(options)
    local menu_poller = self.omega.menu.add_game_menu_entry({
        triggers = options.triggers,
        argument_hint = options.argument_hint,
        usage = options.usage,
    })
    local factory = newSessionFactory()
    self:new_event_source(menu_poller, function(...) factory:on_new_session(...) end)
    return factory
end

--- 监听聊天消息时
--- - 范围：任意
--- - 说明：当收到聊天消息时，启动一个新协程并执行指定函数
--- - 返回值：监听器 -含有方法:start_new(function)
---   > 允许在监听器触发时启动函数并且放入新的协程
--- ```lua
--- coromega:when_chat_msg():start_new(function(chat)
---     coromega:print(("chat sender: %s > %s"):format(chat.name, json.encode(chat)))
--- end)
--- ```
--- @return SessionFactory
function Coromega:when_chat_msg()
    local chat_poller = self.omega.players.make_chat_poller()
    local factory = newSessionFactory()
    self:new_event_source(chat_poller, function(...) factory:on_new_session(...) end)
    return factory
end

--- 监听指定名字的消息，这个名字可以是物品名，启动一个新协程并执行指定函数
--- - 范围：任意
--- - 说明：当收到指定名字的消息时，这个名字可以是物品名，启动一个新协程并执行指定函数
--- - 参数：
---   - name:发送者名字
--- - 返回值：监听器 -含有方法:start_new(function)
---   > 允许在监听器触发时启动函数并且放入新的协程
--- ```lua
--- -- 命令块指令为 execute @e[type=snowball] ~ ~ ~ tell 机器人名字 @p[r=3]
--- -- 当收到命令块的消息时，执行回调
--- coromega:when_receive_msg_from_sender_named("雪球"):start_new(function(chat)
---     coromega:print(("item (%s) chat: %s"):format("雪球", json.encode(chat)))
--- end)
--- ```
--- @param string
--- @return SessionFactory
function Coromega:when_receive_msg_from_sender_named(sender_name)
    local sender_poller = self.omega.players.new_specific_item_msg_poller(sender_name)
    local factory = newSessionFactory()
    self:new_event_source(sender_poller, function(...) factory:on_new_session(...) end)
    return factory
end

--- 监听玩家在线状态变化事件
--- - 范围：任意
--- - 当玩家的在线情况发生变化时，启动一个新协程并执行指定函数
--- - 返回值：监听器 -含有方法:start_new(function)
---   > 允许在监听器触发时启动函数并且放入新的协程
---   > player 是一个玩家对象
--- ```lua
--- coromega:when_player_change():start_new(function(player, action)
---     if action == "exist" then
---         coromega:print(("player %s 已经在线"):format(player:name()))
---     elseif action == "online" then
---         coromega:print(("player %s 新上线"):format(player:name()))
---     elseif action == "offline" then
---         coromega:print(("player %s 下线"):format(player:name()))
---     end
--- end)
--- ```
--- @return SessionFactory
function Coromega:when_player_change()
    local player_change_poller = self.omega.players.make_player_change_poller()
    local factory = newSessionFactory()
    self:new_event_source(player_change_poller, function(event)
        local player = newCoroPlayer(event.player, self)
        local action = event.action
        factory:on_new_session(player, action)
    end)
    return factory
end

--- 监听命令块消息事件
--- - 范围：任意
--- - 说明：当收到命令块消息时，启动一个新协程并执行指定函数
--- - 参数：
---   - command_block_name:命令块名字
--- - 返回值：监听器 -含有方法:start_new(function)
---   > 允许在监听器触发时启动函数并且放入新的协程
--- ```lua
--- -- 命令块命名为 "扫地机"，指令为 tell 机器人名字 去扫地
--- -- 当收到命令块的消息时，执行回调
--- coromega:when_receive_msg_from_command_block_named("扫地机"):start_new(function(chat)
---     coromega:print(("command block (%s) chat: %s"):format("扫地机", json.encode(chat)))
--- end)
--- ```
--- @param command_block_name string
--- @return SessionFactory
function Coromega:when_receive_msg_from_command_block_named(command_block_name)
    local cmd_block_poller = self.omega.players.make_specific_command_block_tell_poller(command_block_name)
    local factory = newSessionFactory()
    self:new_event_source(cmd_block_poller, function(...) factory:on_new_session(...) end)
    return factory
end

--- 监听指定类型的数据包
--- - 范围：协程外
--- - 说明：当机器人收到指定的数据包类型时，启动一个新的协程并运行指定处理函数
--- - 参数：
---   - 待接收的数据包类型列表，这里有两种方式
---   - when_receive_packet_of_types(数据包类型 1, 数据包类型 2, 数据包类型 3 ...)
---     e.g. :when_receive_packet_of_types(packets.Text, packets.CommandOutput)
---     这代表接收所罗列的数据包类型
---   - when_receive_packet_of_types(packets.all, no 数据包类型 1, no 数据包类型 2, no 数据包类型 3 ...)
---     e.g. :when_receive_packet_of_types(packets.all, packets.noMovePlayer)
---     这代表接收除了 noXX 对应的 XX 类型数据包外的其余数据包类型 (反选)
--- - 返回：监听器，监听器的处理函数的参数为数据包，数据包具有以下三个成员函数
---   - name() 数据包名，例如 "IDText"
---   - id() 数据包类型编号，例如 27
---   - user_data() 数据包数据，user_data 形式，注意，您可以访问 user_data 形式数据包内部的成员
---     但是，user_data 并非普通的 lua 数据结构，因此您无法使用 pair 或 ipair 遍历数据包内部结构
---     您可以使用 ud2lua 函数将 user_data 转换为普通的 lua 数据结构以使用 pair 或 ipair,
---     但是，ud2lua 会造成额外的性能开销，因此您应该尽量避免使用 ud2lua 函数以提高插件性能
--- ```lua
--- local packets = omega.packets
--- coromega:when_receive_packet_of_types(packets.Text, packets.CommandOutput):start_new(function(packet)
---   coromega:print(("packet name: %s id: %s"):format(packet:name(), packet:id()))
---   if packet:name() == packets.CommandOutput then
---       coromega:print(("detail packet %s"):format(packet:json_str()))
---       local packet_userdata = packet:user_data()
---       coromega:print(("detail packet (user_data) %s"):format(packet_userdata))
---       coromega:print(("detail packet (lua table) %s"):format(ud2lua(packet_userdata)))
---       coromega:print(("Origin: %s"):format(packet_userdata.CommandOrigin.Origin))
---       coromega:print(("OutputMessages[0].Message: %s"):format(packet_userdata.OutputMessages[1].Message))
---   end
--- end)
--- coromega:when_receive_packet_of_types(packets.all, packets.noMovePlayer)
--- ```
--- @varargs string|number
--- @return SessionFactory
function Coromega:when_receive_packet_of_types(...)
    local packet_poller = self.omega.listen.make_packet_poller(...)
    local factory = newSessionFactory()
    self:new_event_source(packet_poller, function(...) 
        factory:on_new_session(...) 
    end)
    return factory
end

--- 跨插件写入值
--- - 范围：任意
--- - 说明：向 omega 写入值，值可以被跨进程、跨插件读取，且不会随着框架崩溃消失 (只有在机器人退出才会消失)
--- - 考虑到这是跨进程的，其速度并不是很快
--- - 参数：
--- - key: 名字，必须为 string
--- - val: 值，必须为 string
--- - 返回：无
--- ``` lua
--- coromega:soft_set("status/my_plugin","start")
--- ```
--- @param key string
--- @param value string
function Coromega:soft_set(key, val)
    self.omega.flex.set(key, val)
end

--- 跨插件读取值
--- - 范围：任意
--- - 说明：向 omega 读取值，值可以被跨进程、跨插件读取，且不会随着框架崩溃消失 (只有在机器人退出才会消失)
--- - 考虑到这是跨进程的，其速度并不是很快
--- - 参数：
--- - key: 名字，必须为 string
--- - 返回：val,found
--- ``` lua
--- local hashed_server_code,found=coromega:soft_get("HashedServerCode")
--- coromega:print("hashed_server_code",hashed_server_code)
--- coromega:print("found",found)
--- local status=coromega:soft_get("status/my_plugin")
--- coromega:print("status: ",status)
--- ```
--- @param key string
--- @return string|nil,boolean
function Coromega:soft_get(key)
    return self.omega.flex.get(key)
end

--- 获取用户 Token 的 MD5 & 服务器号 MD5
--- @return table
function Coromega:user_info()
    return {
        ["HashedUserToken"] = self:soft_get("HashedUserID"),
        ["HashedServerCode"] = self:soft_get("HashedServerCode"),
        ["HashedServeCode"] = self:soft_get("HashedServerCode")
    }
end

--- 暴露跨插件 API
--- - 范围：任意
--- - 说明：以 api_name 暴露一个跨插件 api, 当该 api 被调用时，一个协程被创建并在其中运行指定的 api 函数
--- - 参数：
--- - api_name: 字符串形式的跨插件 api 名
--- - set_result: 设置返回结果和错误（若不使用则使用函数的返回值）
--- - 返回：监听器，监听器内的处理函数的参数为：
--- - 调用参数
--- - 返回函数：当返回函数被调用时，调用者将收到调用结果，返回函数最多只能被调用一次
--- ```lua
--- coromega:when_called_by_api_named("/calculator/add"):start_new(function(args, set_result)
---     local result = args[1] + args[2]
---     set_result(result)
--- end)
--- @param api_name string
--- @return SessionFactory
function Coromega:when_called_by_api_named(api_name)
    local api_poller = self.omega.flex.expose(api_name)
    local factory = newSessionFactory()
    self:new_event_source(api_poller, function(event)
        local args = event.args
        local set = false
        factory:on_result(function(ret, err)
            if set == false then
                event.cb(json.encode(ret), err)
            end
        end)
        factory:on_new_session(json.decode(args), function(result, err)
            if set then
                error("double set result!")
            end
            event.cb(json.encode(result), err)
            set = true
        end)
    end)
    return factory
end

--- 接收/订阅跨插件消息
--- - 范围：任意
--- - 说明：订阅一个指定 topic, topic 是跨插件的，当该 topic 下有新消息时，一个协程被创建并在其中运行指定的函数
--- - 参数：
---   - topic: 字符串形式的话题名
--- - 返回：监听器，监听器内的处理函数的参数为 topic 下的新数据
--- ```lua
--- coromega:when_new_data_in_subscribed_topic_named("/send_time/1"):start_new(function(data)
---     print(data.disp)
---     print(data.send_time)
--- end)
--- ```
--- @param string
--- @return SessionFactory
function Coromega:when_new_data_in_subscribed_topic_named(topic)
    local topic_poller = self.omega.flex.listen(topic)
    local factory = newSessionFactory()
    self:new_event_source(topic_poller, function(data)
        factory:on_new_session(json.decode(data))
    end)
    return factory
end

--- 监听 cqhttp 消息
--- - when_receive_cqhttp_message()
---   - 事件端点，协程起点
---   - 监听 cqhttp 消息
---   - 参数：无
---   - 返回值为监听器<br>
---     监听器的回调函数的参数为
---     - message_type(消息类型)
---     - message(消息)
---     - raw_message_string(原始消息)
--- ```lua
---   coromega:when_receive_cqhttp_message():start_new(function(message_type, message, raw_message_string)
---       print(("cqhttp 消息> message type: %s, message: %s, raw message string: %s"):format(message_type, message,
---           raw_message_string))
---   end)
--- ```
--- @return SessionFactory
function Coromega:when_receive_cqhttp_message()
    local cqhttp_poller = self.omega.cqhttp.make_message_poller()
    local factory = newSessionFactory()
    self:new_event_source(cqhttp_poller, function(data)
        local raw_message_string = data.raw_msg
        local message_type = data.msg_type
        local message = data.msg
        factory:on_new_session(message_type, message, raw_message_string)
    end)
    return factory
end

--- 监听默认发送列表 cqhttp 消息
--- - 事件端点，协程起点
--- - 监听默认发送列表的 cqhttp 消息
--- - 返回值为监听器<br>
--- 监听器的回调函数的参数为
--- - source(来源)
--- - name(名字 昵称#qq 号)
--- - message(消息)
--- ```lua
--- coromega:when_receive_filtered_cqhttp_message_from_default():start_new(function(source, name, message)
---     print(("cqhttp 默认监听对象> 来源：%s, 名字：%s, 消息：%s"):format(source, name, message))
--- end)
--- ```
function Coromega:when_receive_filtered_cqhttp_message_from_default()
    local cqhttp_poller = self.omega.cqhttp.make_default_message_poller()
    local factory = newSessionFactory()
    self:new_event_source(cqhttp_poller, function(data)
        local name = data.name
        local source = data.source
        local message = data.msg
        factory:on_new_session(source, name, message)
    end)
    return factory
end

--- @class WSServerSessionFactory
local WSServerSessionFactory = { _cname = "WSServerSessionFactory" }
local function newWSServerSessionFactory()
    local instance = { on_server_dead = function() end }
    setmetatable(instance, { __index = WSServerSessionFactory })
    return instance
end

function WSServerSessionFactory:on_new_conn(conn)
    local session = newSession()
    session.co = coroutine.create(function() self.coro_fn(conn) end)
    session.resume()
end

function WSServerSessionFactory:when_new_conn(coro_fn)
    self.coro_fn = coro_fn
    return self
end

function WSServerSessionFactory:when_dead(cb)
    self.on_server_dead = function(reason)
        local session = newSession()
        session.co = coroutine.create(function() cb(reason) end)
        session.resume()
    end
    return self
end

--- @class WSConnWrapper
local WSConnWrapper = { _cname = "WSConnWrapper" }
local function newWSConnWrapper(conn)
    local instance = { conn = conn }
    setmetatable(instance, { __index = WSConnWrapper })
    return instance
end

function WSConnWrapper:on_new_msg(message)
    if self.on_next_msg then
        self.on_next_msg(message)
        self.on_next_msg = nil
    elseif self.coro_fn then
        local session = newSession()
        session.co = coroutine.create(function() self.coro_fn(message) end)
        session.resume()
    end
end

--- 接收到消息时的回调
--- 当新消息到来且未被 receive_message 拦截时，一个新协程被创建并启动 func 函数
--- 函数的参数为字符串形式的消息，如果连接断开，则获得 nil
--- @param coro_fn function(data:string|nil)
function WSConnWrapper:when_new_msg(coro_fn)
    self.coro_fn = coro_fn
    return self
end

--- 发送数据
--- @param msg table 可被 json.encode 处理的数据
function WSConnWrapper:send(msg)
    self.conn:send_message(json.encode(msg))
end

--- 发送消息
--- @param msg string
function WSConnWrapper:send_message(msg)
    self.conn:send_message(msg)
end

--- 接收(仅)下一条消息
--- 接收下一条消息，下一条消息会做为该函数的返回值出现，而不会被 when_new_msg 处理
--- @return string
function WSConnWrapper:receive_message()
    local enclusure_resume = _current_coro_session_resume
    self.on_next_msg = function(msg)
        enclusure_resume(msg)
    end
    return coroutine.yield()
end

--- 创建一个 WebSocket 服务器
--- 当一个客户端连接到webscoket服务器时，会创建一个 Session
--- @param host string
--- @param port int
--- @return SessionFactory
function Coromega:create_websocket_server(host, port)
    local factory = newWSServerSessionFactory()
    local err = self.omega.websocket.server(host, port, function(conn)
        local wrapper = newWSConnWrapper(conn)
        self:new_event_source(conn, function(recved_msg)
            wrapper:on_new_msg(recved_msg)
        end)
        factory:on_new_conn(wrapper)
    end, factory.on_server_dead)
    if err ~= nil then
        return nil
    end
    return factory
end

--- 创建一个Webscoket客户端
--- @param addr string
--- @param header table|nil
--- @return WSConnWrapper|nil
function Coromega:connect_to_websocket(addr, header)
    local conn = self.omega.websocket.connect(addr, header)
    if conn == nil then
        return nil
    end
    local wrapper = newWSConnWrapper(conn)
    self:new_event_source(conn, function(recved_msg)
        wrapper:on_new_msg(recved_msg)
    end)
    return wrapper
end

--- 创建一个新的协程, 并立即执行指定的函数
--- @param coro_fn function
function Coromega:start_new(coro_fn)
    local session = newSession()
    local co = coroutine.create(coro_fn)
    session.co = co
    session.resume()
    -- error("crash")
end

--- 失能所有的回调，效果类似于关闭插件
function Coromega:halt()
    self.enabled = false
end

--- 处理所有的回调，并使能 coroutine
function Coromega:run()
    for k, v in pairs(self.cbs) do
        self.new_event_source(k, v) -- adapt old code
    end
    while self.mux_poller:block_has_next() do
        if self.enabled then
            local event = self.mux_poller:block_get_next()
            local cb = self.maintained_cbs[event.type]
            cb(event.data)
        end
    end
end

--- 入口函数
--- @return Coromega
function from(omega)
    return newCoromega(omega)
end
return _G