-- ORIG_VERSION_HASH: 20fd2d863669343d74be7ffb5fab76f9
-- ORIG_VERSION_HASH 可以帮助 neOmega 判断此 lua 文件中的代码是否被用户修改过
-- 如果此 lua 文件中的代码被用户修改过，那么 neOmega 将不会再修改它以避免错误的覆盖用户修改
-- 如果此 lua 文件中的代码没有被用户修改过，那么 neOmega 将在此插件有更新时自动应用更新
-- 当前状态: 代码未被用户修改，neOmega 将自动应用更新
-- ORIG_VERSION_HASH: END
local omega = require("omega")
local json = require("json")
--- @type Coromega
local coromega = require("coromega").from(omega)
local print = function (...)
    coromega:info_out(...)
end

local send_mode = "ws"
send_mode = omega.config:user_data()["默认身份"]
if send_mode == "websocket" then
    send_mode = "ws"
elseif send_mode == "setting" then
    send_mode = "wo"
elseif send_mode == "aiCommand" then
    send_mode = "ai"
end
if send_mode ~= "ws" and send_mode ~= "wo" and send_mode ~= "player" and send_mode ~= "ai" then
    send_mode = "ws"
end

local TERM_BLUE = "\27[38;5;12m"
local TERM_GREEN = "\27[38;5;10m"
local TERM_RED = "\27[38;5;9m"
local TERM_CLEAR = "\27[0m"

cbs = {}
cbs[omega.cmds.resp] = function(response)
    local cb = response.cb
    local packet = response.output
    cb(packet)
end

local function display_cmd_output(cmd_to_send, output)
    local data = output:user_data()
    local success_count = data.SuccessCount
    local TERM_C = TERM_GREEN
    if success_count == 0 then
        TERM_C = TERM_RED
        print((TERM_RED .. "指令 " .. TERM_BLUE .. "%s" .. TERM_RED .. " 执行失败"):format(cmd_to_send))
    else
        print((TERM_GREEN .. "指令 " .. TERM_BLUE .. "%s" .. TERM_GREEN .. " 执行成功: %s 次"):format(
            cmd_to_send, success_count)
        )
    end
    local output_messages = ud2lua(data.OutputMessages)
    for _, msg in ipairs(output_messages) do
        -- check Message and Parameters if exists
        if msg.Message and msg.Parameters then
            print(("%s%s"):format(TERM_C, coromega:lang_format(0, msg.Message, unpack(msg.Parameters))))
        else
            print(("%s%s"):format(TERM_C, json.encode(msg)))
        end
    end
    -- print(TERM_BLUE .. "[full]: " .. json.encode(data))
end

local cmd_poller = omega.menu.add_backend_menu_entry({
    triggers = { "/" },
    argument_hint = "[cmd]",
    usage = "发送指令",
})

cbs[cmd_poller] = function(input_args)
    local cmd_to_send = table.concat(input_args, " ")
    print(("发送指令: " .. TERM_BLUE .. "%s (%s)"):format(cmd_to_send, send_mode))
    if send_mode == "ws" then
        omega.cmds.send_ws_cmd_with_resp(cmd_to_send, function(output)
            display_cmd_output(cmd_to_send, output)
        end)
    elseif send_mode == "player" then
        omega.cmds.send_player_cmd_with_resp(cmd_to_send, function(output)
            display_cmd_output(cmd_to_send, output)
        end)
    elseif send_mode == "wo" then
        omega.cmds.send_wo_cmd(cmd_to_send)
        print(TERM_BLUE .. "此类指令无返回值，且部分指令不会生效")
    elseif send_mode == "ai" then
        omega.cmds.send_ai_cmd_with_resp(omega.botUq.get_bot_runtime_id(), cmd_to_send, function(output)
            display_cmd_output(cmd_to_send, output)
        end)
    end
end

local cmd_mod_poller = omega.menu.add_backend_menu_entry({
    triggers = { "cmdmod" },
    argument_hint = "[ws/wo/player/ai]",
    usage = "设置发送命令时的身份",
})

cbs[cmd_mod_poller] = function(input_args)
    local option = table.concat(input_args, " ")
    -- trim whitespace
    option = option:gsub("^%s*(.-)%s*$", "%1")
    -- to lower case
    option = option:lower()
    if option == "ws" or option == "websocket" then
        send_mode = "ws"
        print(TERM_BLUE .. "设置发送命令时的身份为: websocket")
    elseif option == "wo" or option == "setting" then
        send_mode = "wo"
        print(TERM_BLUE .. "设置发送命令时的命令为: 无返回指令")
    elseif option == "player" then
        send_mode = "player"
        print(TERM_BLUE .. "设置发送命令时的命令为: player")
    elseif option == "ai" then
        send_mode = "ai"
        print(TERM_BLUE .. "设置发送命令时的命令为: aiCommand")
    else
        print(TERM_RED .. "无效的选项: " .. option)
        print(TERM_RED .. "可选选项: ws(websocket)/wo(无返回指令)/player/ai(aiCommand)")
    end
end

local mux_poller = omega.listen.new_mux_poller()
for k, _ in pairs(cbs) do
    mux_poller:poll(k)
end
local i=0
while mux_poller:block_has_next() do -- 如果有下一个事件
    local event = mux_poller:block_get_next()
    if cbs[event.type] ~= nil then
        cbs[event.type](event.data)
    end
end
