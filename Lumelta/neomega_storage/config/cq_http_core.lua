-- ORIG_VERSION_HASH: 80fe0aac88a618d077ead9379836ad25
-- ORIG_VERSION_HASH 可以帮助 neOmega 判断此 lua 文件中的代码是否被用户修改过
-- 如果此 lua 文件中的代码被用户修改过，那么 neOmega 将不会再修改它以避免错误的覆盖用户修改
-- 如果此 lua 文件中的代码没有被用户修改过，那么 neOmega 将在此插件有更新时自动应用更新
-- 当前状态: 代码未被用户修改，neOmega 将自动应用更新
-- ORIG_VERSION_HASH: END
-- QQ 与 Omega 间各个部分的关系:
--      QQ
--      |
--      辅助程序[各种支持 OneBot11 协议的，例如启动器自带的 QQBot 或者 LLOneBot等]，你的QQ账号在这里登陆
--      |
-- MC- NeOmega[内置QQBotHelper，根据OneBot11协议从辅助程序接收数据]
--     ｜
--     **此文件在这里** -> cqhttp.lua [接口拓展和基础解析的lua模块，例如定义默认的监听目标和输出目标，将消息转换给其他模块]
--     |
--     插件加载器--------------------------------------------------------------------------
--     ｜                   |                                                             |
--     MC_QQ聊天互通.lua   QQExtendCore[前置扩展插件] --soft-api-- QQExtendLib[库文件]-- 其他扩展QQ功能的插件[例如QQ扩展示例]

local omega = require("omega")
local json = require("json")
--- @type Coromega
local coromega = require("coromega").from(omega)
local print = function (...)
    coromega:info_out(...)
end
local cqhttp = omega.cqhttp

local config = ud2lua(omega.config:user_data())
local default_listen_targets = config["默认监听目标"]
local default_send_targets = config["默认发送目标"]
print(("默认接收的消息源: %s"):format(json.encode(default_listen_targets)))
print(("默认消息发送的目标: %s"):format(json.encode(default_send_targets)))

local default_listened_friends = {}
local default_listened_groups = {}
local default_listened_channels = {}

local guild_id_to_name = {}
local guild_name_to_id = {}
local channel_id_to_name = {}
local channel_name_to_id = {}

for _, v in pairs(default_listen_targets) do
    if v:sub(1, ("好友:"):len()) == "好友:" then
        -- 如果是 好友:xxx 的形式
        local friend_id = v:sub(("好友:"):len() + 1)
        print(("监听好友: %s"):format(friend_id))
        default_listened_friends[friend_id] = v
    elseif v:sub(1, ("群聊:"):len()) == "群聊:" then
        --  如果是 群聊:xxx 的形式
        local group_id = v:sub(("群聊:"):len() + 1)
        print(("监听群聊: %s"):format(group_id))
        default_listened_groups[group_id] = v
    elseif v:sub(1, ("频道:"):len()) == "频道:" then
        --  如果是 频道:频道名:聊天室 的形式
        local guild_name, channel_name = v:match("频道:(.+):(.+)")
        print(("监听频道: %s, 聊天室: %s"):format(guild_name, channel_name))
        default_listened_channels[guild_name .. ":" .. channel_name] = v
    end
end

local default_send_target_fns = {}
local deferred_guild_info_translate = {}
local deferred_msg = {}
for _, v in pairs(default_send_targets) do
    if v:sub(1, ("好友:"):len()) == "好友:" then
        -- 如果是 好友:xxx 的形式
        local friend_id = v:sub(("好友:"):len() + 1)
        default_send_target_fns[#default_send_target_fns + 1] = function(msg)
            cqhttp.send_private_message(friend_id, msg)
        end
    elseif v:sub(1, ("群聊:"):len()) == "群聊:" then
        --  如果是 群聊:xxx 的形式
        local group_id = v:sub(("群聊:"):len() + 1)
        default_send_target_fns[#default_send_target_fns + 1] = function(msg)
            cqhttp.send_group_message(group_id, msg)
        end
    elseif v:sub(1, ("频道:"):len()) == "频道:" then
        --  如果是 频道:频道名:聊天室 的形式
        local guild_name, channel_name = v:match("频道:(.+):(.+)")
        deferred_guild_info_translate[#deferred_guild_info_translate + 1] = { guild_name, channel_name }
    end
end


local cbs = {}
cbs[cqhttp.resp] = function(resp)
    resp.cb(resp.output)
end

local push_default_msg = push_default_received_msg

local function send_to(msg)
    local target = msg.target
    -- print("target: " .. target)
    local msg = msg.msg
    if target == "" then
        -- print("send to default")
        -- send to default
        for i, send in pairs(default_send_target_fns) do
            print(("send to default target %d"):format(i))
            send(msg)
        end
        if #deferred_guild_info_translate ~= 0 then
            deferred_msg[#deferred_msg + 1] = msg
        end
    else
        if target:sub(1, ("好友:"):len()) == "好友:" then
            -- 如果是 好友:xxx 的形式
            local friend_id = target:sub(("好友:"):len() + 1)
            cqhttp.send_private_message(friend_id, msg)
        elseif target:sub(1, ("群聊:"):len()) == "群聊:" then
            --  如果是 群聊:xxx 的形式
            local group_id = target:sub(("群聊:"):len() + 1)
            cqhttp.send_group_message(group_id, msg)
        elseif target:sub(1, ("频道:"):len()) == "频道:" then
            --  如果是 频道:频道名:聊天室 的形式
            local guild_name, channel_name = target:match("频道:(.+):(.+)")
            local guild_id = guild_name_to_id[guild_name]
            if not guild_id then
                print(("频道 %s 未找到对应的频道"):format(guild_name))
                return
            end
            local channel_id = channel_name_to_id[guild_id][channel_name]
            if not channel_id then
                print(("聊天室 %s 未找到"):format(channel_name))
                return
            end
            cqhttp.send_guild_message(guild_id, channel_id, msg)
        end
    end
end
cbs[send_msg_poller] = send_to

-- push_default_msg("2401PT", "hello world")

local function parse_message(message)
    -- 字符串消息
    if type(message) == "string" then
        return message
    end
    -- 字典消息
    if message.type then
        return (message.type == "text" and message.data.text) or ""
    end
    -- 字典列表消息
    local textValues = {}
    for _, obj in ipairs(message) do
        if obj.type == "text" and type(obj.data.text) == "string" then
            table.insert(textValues, obj.data.text)
        end
    end
    -- 返回拼接后的字符串
    return (#textValues > 0 and table.concat(textValues, "")) or ""
end

cbs[cqhttp.make_message_poller()] = function(packet)
    local msg_type = packet.msg_type
    local msg = packet.msg
    local msg_str = ""
    local sender_name = ""
    local source = ""
    if msg_type == "GroupMessage" then
        -- print(("group message: msg_type=%s,msg=%s"):format(msg_type, json.encode(msg)))
        local group_id = msg.GroupID
        msg_str = (msg.Message.RawMessage ~= "" and msg.Message.RawMessage) or parse_message(msg.Message.Message)
        msg_str = msg_str:gsub("&#91;", "["):gsub("&#93;", "]")
        sender_name = ((msg.Sender.Card ~= "" and msg.Sender.Card) or msg.Sender.User.Nickname) .. "#" .. msg.Sender.User.UserID
        source = default_listened_groups[("%s"):format(group_id)]
        if source then
            -- print(("group [%s]: %s"):format(sender_name, msg_str))
            push_default_msg(sender_name, msg_str, source)
        end
        -- print(("[%s]: %s"):format(sender_name, msg_str))
    elseif msg_type == "PrivateMessage" then
        -- print(("private message: msg_type=%s,msg=%s,userID"):format(msg_type, json.encode(msg), msg.UserID))
        msg_str = (msg.Message.RawMessage ~= "" and msg.Message.RawMessage) or parse_message(msg.Message.Message)
        msg_str = msg_str:gsub("&#91;", "["):gsub("&#93;", "]")
        sender_name = msg.Sender.Nickname .. "#" .. msg.Sender.UserID
        local user_id = ("%s"):format(msg.UserID)
        -- print(("[%s]: %s"):format(sender_name, msg_str))
        if default_listened_friends[sender_name] then
            push_default_msg(sender_name, msg_str, default_listened_friends[sender_name])
        elseif default_listened_friends[user_id] then
            push_default_msg(sender_name, msg_str, default_listened_friends[user_id])
        end
    elseif msg_type == "GuildMessage" then
        local channel_id = msg.ChannelID
        local guild_id = msg.GuildID
        local guild_name = guild_id_to_name[guild_id]
        local channels_name = channel_id_to_name[guild_id]
        local channel_name = ""
        if channels_name then
            channel_name = channels_name[channel_id]
        end
        -- print(("guild message: msg_type=%s,msg=%s"):format(msg_type, json.encode(msg)))
        msg_str = (msg.Message.RawMessage ~= "" and msg.Message.RawMessage) or parse_message(msg.Message.Message)
        msg_str = msg_str:gsub("&#91;", "["):gsub("&#93;", "]")
        sender_name = msg.Sender.User.Nickname .. "#" .. msg.Sender.User.UserID
        -- print(("[%s][%s][%s]: %s"):format(guild_name, channel_name, sender_name, msg_str))
        source = default_listened_channels[guild_name .. ":" .. channel_name]
        if source then
            push_default_msg(sender_name, msg_str, source)
        end
    else
        return
    end
end

cbs[cqhttp.make_default_message_poller()] = function(msg)
    print(("> [%s@%s]: %s"):format(msg.name, msg.source, msg.msg))
    -- cqhttp.send_to(msg.source, "echo: " .. msg.msg)
    -- cqhttp.send_to("", "echo: " .. msg.msg)
end

local function onChannelList(guild_id, guild_name, list)
    -- print(("%s %s %s"):format(guild_id, guild_name, json.encode(list)))
    for _, channel in pairs(list) do
        local channel_id = channel.ChannelID
        local channel_name = channel.ChannelName
        channel_id_to_name[guild_id][channel_id] = channel_name
        channel_name_to_id[guild_id][channel_name] = channel_id
        channel_id_to_name[guild_name][channel_id] = channel_name
        channel_name_to_id[guild_name][channel_name] = channel_id
    end
    for i, info in pairs(deferred_guild_info_translate) do
        local channel_name, room_name = unpack(info)
        local guild_id = guild_name_to_id[channel_name]
        if not guild_id then
            return
        end
        local room_id = channel_name_to_id[guild_id][room_name]
        if not room_id then
            return
        end
        local send = function(msg)
            cqhttp.send_guild_message(guild_id, room_id, msg)
        end
        default_send_target_fns[#default_send_target_fns + 1] = send
        for _, msg in pairs(deferred_msg) do
            send(msg)
        end
        deferred_guild_info_translate[i] = nil
        if #deferred_guild_info_translate == 0 then
            deferred_msg = {}
        end
    end
end

local function onGuildList(list)
    for _, guild in pairs(list) do
        local guild_id = guild.GuildID
        local guild_name = guild.GuildName
        guild_id_to_name[guild_id] = guild_name
        guild_name_to_id[guild_name] = guild_id
        channel_id_to_name[guild_id] = {}
        channel_name_to_id[guild_id] = {}
        channel_id_to_name[guild_name] = {}
        channel_name_to_id[guild_name] = {}
        cqhttp.get_guild_channels(guild_id, function(list)
            onChannelList(guild_id, guild_name, list)
        end)
    end
end
cqhttp.get_guild_list(onGuildList)

-- print("cqhttp.lua: start")

local mux_poller = omega.listen.make_mux_poller()
for k, _ in pairs(cbs) do
    mux_poller:poll(k)
end
while mux_poller:block_has_next() do
    local event = mux_poller:block_get_next()
    local cb = cbs[event.type]
    cb(event.data)
end
