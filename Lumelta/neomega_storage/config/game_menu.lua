-- ORIG_VERSION_HASH: 7aa2e6f5d0f684680bc968be60ff86b7
-- ORIG_VERSION_HASH 可以帮助 neOmega 判断此 lua 文件中的代码是否被用户修改过
-- 如果此 lua 文件中的代码被用户修改过，那么 neOmega 将不会再修改它以避免错误的覆盖用户修改
-- 如果此 lua 文件中的代码没有被用户修改过，那么 neOmega 将在此插件有更新时自动应用更新
-- 当前状态: 代码未被用户修改，neOmega 将自动应用更新
-- ORIG_VERSION_HASH: END
local omega = require("omega")
--- @type Coromega
local coromega = require("coromega").from(omega)
local print = function (...)
    coromega:info_out(...)
end
local db = omega.storage.get_kv_db("game_menu")
-- read configs
local config = ud2lua(omega.config:user_data())
local menu_trigger_words = config["菜单触发词"]
local menu_organize = config["菜单组织结构和权限选项"]
local root_permission_option = config["使用omega需要具有的权限"]
local permission_check_list = config["除OP权限外其他权限检查依据"]

-- 此菜单经过 铃鹿 (a.k.a Aurilia0617) 大佬进行大量的优化和美化
-- 详细信息可以去频道 Aurilia0617 的帖子下找

--美化菜单部分 采用主题制度也就是 get_theme()中放入自己的主题即可
local color = {
    black      = "§0",
    darkblue   = "§1",
    darkgreen  = "§2",
    darkaqua   = "§3",
    teal       = "§3", -- same as darkaqua
    darkred    = "§4",
    darkpurple = "§5",
    gold       = "§6",
    orange     = "§6", -- same as gold
    gray       = "§7",
    grey       = "§7", -- same as gray
    darkgray   = "§8",
    blue       = "§9",
    green      = "§a",
    aqua       = "§b",
    cyan       = "§b", -- same as aqua
    red        = "§c",
    pink       = "§d",
    purple     = "§d", -- same as pink
    yellow     = "§e",
    white      = "§f",
    big        = "§l",
    bold       = "§l", -- same as big
    italic     = "§o",
    reset      = "§r",
    obfuscated = "§k",
    hide       = "§k", -- same as obfuscated
    strikethru = "§m",
    underline  = "§n",

}
--替换出颜色来
function color:format_color(str)
    -- 定义替换函数
    if type(str) == "string" then
        for k, v in pairs(color) do
            str = str:gsub('$' .. k, v)
        end
    else
        print("解析错误")
    end
    return str
end

local template = {
    valid_count_one_canback_selections =
    "$theme_color输入 $selection_color1 $theme_color或 $selection_color2 $theme_color以选择,输入 $selection_color返回 $theme_color以返回上一级,或输入 $selection_color取消 $theme_color以退出",
    valid_count_one_notcanback_selections =
    "$theme_color输入 $selection_color1 $theme_color以选择, 输入 $selection_color取消 $theme_color以退出菜单",
    no_permission = "$error_color$big你没有权限执行此操作",
    resposen = "$ok_color$big好的 (＾◡＾) ",
    quite_menu = "$ok_color(つ✧ω✧)つ已退出菜单",
    cancel_selections = "$theme_color输入: $selection_color取消 $theme_color以退出菜单",
    no_permission_exce = "$error_color(╯°□°）╯︵ ┻━┻ - $b你没有权限执行此操作",
    no_respose = "$question_color(⊙_⊙)?抱歉我并不明白你在说什么",
    omega_recall = "$question_color(⊙_⊙)?再输入一次omg重新唤起菜单",
    entry_print = "$big$theme_color[ $selection_color%s $theme_color] %s%s $reset$white %s",
    sub_menu = "$big$theme_color[$selection_color %s $theme_color] %s $reset$white %s",
    back_parent = "$big$theme_color[$selection_color %s $theme_color] %s $reset$white %s",
    cant_find = "$error_color(￣ー￣??)无法找到玩家$b %s $e的信息\n",
    tips_for_selections =
    "$theme_color输入 $selection_color[1-%s] $theme_color之间的数字以选择, 输入 $selection_color取消 $theme_color以退出菜单",
    op_info = "玩家 %s 的权限: op=%s, creative=%s\n",
    cannot_find_anything = "error:cant find any thing",
    permission_display = "$theme_color权限: ",
    has_permission = "$theme_color[$ok_color%s√$theme_color] ",
    miss_permission = "$theme_color[$error_color%s×$theme_color] ",
}

local Theme = { _cname = "Theme" }
local function newTheme(theme)
    local instance = { _t = theme }
    setmetatable(instance, { __index = Theme })
    return instance
end
function Theme:entry_print(valid_count, trigger, argument_hint, usage)
    return (self._t.entry_print):format(valid_count, trigger,
        argument_hint, usage
    )
end

function Theme:sub_menu(valid_count, key, description)
    return (self._t.sub_menu):format(valid_count, key, description)
end

function Theme:back_parent(valid_count, one_word, send_word)
    return (self._t.back_parent):format(valid_count, one_word, send_word)
end

function Theme:title(type_str)
    return self._t[type_str] or self._t.cannot_find_anything
end

function Theme:cant_find(name)
    return (self._t.cant_find):format(name)
end

function Theme:tips_for_selections(selections_valid_count)
    return (self._t.tips_for_selections):format(selections_valid_count)
end

function Theme:Op_title(name, is_op, creative)
    return (self._t.op_info):format(name, is_op, creative)
end

function Theme:permission_display(permission)
    local s = (self._t.permission_display)
    for k, v in pairs(permission) do
        if v then
            s = s .. (self._t.has_permission):format(k)
        else
            s = s .. (self._t.miss_permission):format(k)
        end
    end
    return s
end

function render_color_template(template, theme_color, selecton_color, error_color, ok_color, question_color)
    local rendered_theme = {}
    for k, v in pairs(template) do
        rendered_theme[k] = color:format_color(v
            :gsub("$theme_color", theme_color):gsub("$selection_color", selecton_color)
            :gsub("$error_color", error_color):gsub("$ok_color", ok_color)
            :gsub("$question_color", question_color)
        )
    end
    return newTheme(rendered_theme)
end

local _themes = {
    default = render_color_template(template, color.aqua, color.orange, color.red, color.green, color.pink),
}

local function themes(theme_name)
    return _themes[theme_name]
end

-- {player1={op=true,creative=true},player2={op=false,creative=false,...}}
local player_permission = {}
-- {player1={must_omg=true,loose=true},player2={must_omg=false,loose=false,...}}
local player_config = {}
db:iter(function(key, value)
    -- key = "must_omg:player_name" or "loose:player_name"
    -- value = "true" or "false"
    local option, player_name = key:match("([^:]+):([^:]+)")
    if option and player_name then
        if not player_config[player_name] then
            player_config[player_name] = {}
        end
        player_config[player_name][option] = value == "true"
        print(("load player config: %s=%s"):format(key, value))
    end
    return true
end)

function store_must_omg_option(player, value)
    db:set(("must_omg:%s"):format(player), (value and "true") or "false")
end

function store_loose_option(player, value)
    db:set(("loose:%s"):format(player), (value and "true") or "false")
end

local Triggers = { _cname = "Triggers" }

local function newTriggers(...)
    local instance = { _lookup = {}, _keys = {} }
    setmetatable(instance, { __index = Triggers })
    instance:add(...)
    return instance
end


local PermissionGuard = { _cname = "PermissionGuard" }
local function newPermissionGuard(condition, permission_override)
    if condition == nil then
        if permission_override == nil or permission_override:condition() == nil then
            return nil
        else
            condition = permission_override:condition()
        end
    elseif permission_override ~= nil and permission_override:condition() ~= nil then
        local override_condition = permission_override:condition()
        for k, v in pairs(override_condition) do
            condition[k] = v
        end
    end
    local instance = { _condition = condition }
    setmetatable(instance, { __index = PermissionGuard })
    return instance
end
function PermissionGuard:check(permission)
    if self._condition == nil then return true end
    for condition, need in pairs(self._condition) do
        if need then
            if not permission[condition] then return false end
        end
    end
    return true
end

function PermissionGuard:condition()
    return self._condition
end

--负责了 omg菜单项的注册
-- 看起来是调用了newMenuGroup来实现菜单的注册
-- add_entry 即是添加一个菜单选项
-- triggers 负责了响应参数
-- argument_hint 负责参数描述
-- usage 负责了 描述用途
-- on_trig_callback 负责了玩家触发事件后的逻辑处理
local MenuGroup = { _cname = "MenuGroup" }
local function newMenuGroup(config, parent, permission)
    local instance = {
        _items = {},
        _lookup = newTriggers(),
        _msg_matcher = newTriggers(),
        _parent = parent,
        permission = permission
    }
    setmetatable(instance, { __index = MenuGroup })
    instance:from_config(config)
    return instance
end

function MenuGroup:from_config(config)
    for _, cfg in ipairs(config) do
        if cfg["类型"] == "功能" then
            self:add_entry_holder(cfg["名称"], cfg["权限要求"])
        elseif cfg["类型"] == "子菜单" then
            self:add_sub_menu(cfg["名称"], cfg["子菜单描述"], cfg["权限要求"], cfg["子菜单项"])
        end
    end
end

function MenuGroup:add_lookup(triggers, item)
    for _, trigger in ipairs(triggers) do
        self._lookup:add({ trigger }, item)
    end
    if self._parent then
        self._parent:add_lookup(triggers, item)
    end
end

function MenuGroup:add_msg_matcher(triggers, item)
    for _, trigger in ipairs(triggers) do
        self._msg_matcher:add({ trigger }, item)
    end
    if self._parent then self._parent:add_msg_matcher(triggers, item) end
end

function MenuGroup:add_entry_holder(name, permission)
    local item = { type = "entry", item = nil, permission = newPermissionGuard(permission, self.permission) }
    self:add_lookup({ name }, item)
    self._items[#self._items + 1] = item
end

function MenuGroup:add_sub_menu(name, description, permission, menu)
    local permission = newPermissionGuard(permission, self.permission)
    local item = {
        type = "sub_menu",
        key = name,
        description = description,
        item = newMenuGroup(menu, self, permission),
        permission = permission
    }
    self:add_lookup({ name }, item)
    self:add_msg_matcher({ name }, item)
    self._items[#self._items + 1] = item
end

function MenuGroup:add_entry(entry)
    -- {triggers={'key1','key2','key3',...},argument_hint='',usage=''},on_trig_callback=function(chat)}
    local place_holder_item = self._lookup:match_multi(entry.triggers, entry)
    if place_holder_item and place_holder_item.type == "entry" then
        place_holder_item.item = entry
        self:add_msg_matcher(entry.triggers, place_holder_item)
        return
    end
    local item = { type = "entry", item = entry, permission = nil }
    self:add_msg_matcher(entry.triggers, item)
    self._items[#self._items + 1] = item
end

function MenuGroup:print_and_get_option(permission, print)
    local selections = {}
    local selectable = newTriggers()
    local num_selectable = newTriggers()
    local valid_count = 0
    for _, item in ipairs(self._items) do
        if item.item then
            if (not item.permission) or item.permission:check(permission) then
                valid_count = valid_count + 1
                if item.type == "entry" then
                    local argument_hint = ""
                    if item.item.argument_hint ~= "" then
                        argument_hint = (" %s"):format(item.item.argument_hint)
                    end
                    --输出menu
                    print(themes("default"):entry_print(("%s"):format(valid_count), item.item.triggers[1],
                        argument_hint,
                        item.item.usage))
                    selectable:add(item.item.triggers, item)
                    num_selectable:add({ ("%s"):format(valid_count) }, item)
                elseif item.type == "sub_menu" then
                    --sub_menu
                    print(themes("default"):sub_menu(tostring(valid_count), item.key, item.description))
                    selectable:add({ item.key }, item)
                    num_selectable:add({ ("%s"):format(valid_count) }, item)
                end
            end
        end
    end
    selections.selectable = selectable
    selections.num_selectable = num_selectable
    selections.can_back = false
    if self._parent then
        valid_count = valid_count + 1
        -- 返回上级菜单输出
        print(themes("default"):back_parent(("%s"):format(valid_count), "返回", "返回上一级菜单"))
        local parent_menu = { type = "sub_menu", item = self._parent }
        num_selectable:add({ ("%s"):format(valid_count) }, parent_menu)
        selectable:add({ "返回" }, parent_menu)
        selections.can_back = true
    end
    selections.valid_count = valid_count
    return selections
end

function MenuGroup:msg_match(chat, loose)
    local entry = self._msg_matcher:msg_match(chat, loose)
    if not entry or not entry.item then return nil end
    return entry
end

function print_selections(selections, print)
    if selections.valid_count == 0 then
        print(themes("default"):title("cancel_selections"))
        return
    end
    if selections.valid_count == 1 then
        if selections.can_back then
            print(themes("default"):title("valid_count_one_canback_selections"))
        else
            print(themes("default"):title("valid_count_one_notcanback_selections"))
        end
        return
    end
    print(themes("default"):tips_for_selections(("%s"):format(selections.valid_count)))
end

function Triggers:add(words, entry)
    if words == nil then return end
    for _, word in pairs(words) do
        self._lookup[word] = entry
        self._keys[#self._keys + 1] = word
    end
end

function Triggers:get(trigger)
    if trigger == nil then return nil end
    return self._lookup[trigger]
end

function Triggers:keys()
    return self._keys
end

function Triggers:match_multi(triggers)
    for _, trigger in ipairs(triggers) do
        local match = self:get(trigger)
        if match then return match end
    end
    return nil
end

function Triggers:msg_match(chat, loose)
    local trigger = chat.msg[1]
    if trigger == nil then return nil end
    local match = self:get(trigger)
    if match then
        chat.msg = { unpack(chat.msg, 2) }
        return match
    end
    if not loose then return nil end
    for word, entry in pairs(self._lookup) do
        if trigger:sub(1, word:len()) == word then
            chat.msg[1] = trigger:sub(word:len() + 1)
            return entry
        end
    end
    return nil
end

local root_menu_triggers = newTriggers(menu_trigger_words, true)
local root_menu = newMenuGroup(menu_organize, nil, newPermissionGuard(root_permission_option))

function react_user_input(menu, chat, permission, print, must_omg, loose)
    local next_menu = nil
    local entry = nil
    if root_menu_triggers:msg_match(chat, loose) then
        entry = menu:msg_match(chat, permission, loose)
    else
        if must_omg then
            -- print(("> %s"):format(table.concat(chat.msg, " ")))
            return nil
        else
            entry = menu:msg_match(chat, permission, loose)
            if not entry then
                -- print(("> %s"):format(table.concat(chat.msg, " ")))
                return nil
            end
        end
    end
    if entry then
        if (entry.permission) and (not entry.permission:check(permission)) then
            print(themes("default"):title("no_permission"))
            return nil
        end
        if entry.type == "entry" then
            print(themes("default"):title("resposen"))
            entry.item.on_trig_callback(chat)
            return nil
        else -- sub_menu
            next_menu = entry.item
        end
    else
        next_menu = menu
        if next_menu.permission and (not next_menu.permission:check(permission)) then
            print(themes("default"):title("no_permission"))
            return nil
        end
    end
    if next_menu then
        local selections = {}
        if config["启用美化"] then
            coromega:start_new(function()
                next_menu.style_factory:print_menu_and_change_selections({
                    entry = entry or next_menu,
                    menu = next_menu,
                    playername = chat.name,
                    player_permission = permission
                }, selections)
            end)
        else
            if next_menu == root_menu then
                print(themes("default"):permission_display(permission))
            end
            selections = next_menu:print_and_get_option(permission, print)
            print_selections(selections, print)
        end
        return selections
    end
end

local game_menu = game_menu_active_poller
local cmds = omega.cmds
local game_chat = omega.players.make_chat_poller()
local mux_poller = omega.listen.new_mux_poller()
local player_cache = {}

function react_user_selection(selections, chat, permission, print, loose)
    if chat.msg[1] and chat.msg[1] == "取消" then
        print(themes("default"):title("quite_menu"))
        return
    end
    local entry = selections.num_selectable:msg_match(chat, loose)
    if not entry then
        entry = selections.selectable:msg_match(chat, loose)
    end
    if not entry then
        if root_menu_triggers:msg_match(chat, true) then
            print(themes("default"):title("omega_recall"))
            return
        else
            print(themes("default"):title("no_respose"))
            print_selections(selections, print)
            return selections
        end
    end
    if (entry.permission) and (not entry.permission:check(permission)) then
        print(themes("default"):title("no_permission_exce"))
        return nil
    end
    if entry.type == "entry" then
        print(themes("default"):title("resposen"))
        entry.item.on_trig_callback(chat)
        return nil
    else -- sub_menu
        local selections = {}
        if config["启用美化"] then
            coromega:start_new(function()
                entry.item.style_factory:print_menu_and_change_selections({
                    entry = entry,
                    menu = entry.item,
                    playername = chat.name,
                    player_permission = permission
                }, selections)
            end)
        else
            selections = entry.item:print_and_get_option(permission, print)
            print_selections(selections, print)
        end
        return selections
    end
end

function handle_game_chat(chat)
    -- chat={name="...",msg={"...","...","..."},type=...,raw_msg=...,raw_name=...,raw_parameters={"...","...","..."},parsed_msg=...}
    local name = chat.name
    if chat.type ~= 1 and chat.type ~= 7 then
        -- not player, and not tell command
        return
    end
    if name == "" or string.match(name, "§r$") then
        -- nil name, and commandblock tell
        name = "serve"
        return
    end
    -- Uncomment it to see what message can be accepted
    -- print(("> %s: %s\n"):format(name, table.concat(chat.msg, " ")))
    handle_game_chat_with_permission_check(chat, name)
end

function talk_to(player, msg)
    cmds.send_wo_cmd(("tellraw %s {\"rawtext\":[{\"text\":\"%s\"}]}"):format(player, msg))
end

function check_player_permission_by_check_list(player, known_permission, residual_check_list, after_finish_cb)
    if residual_check_list == nil then
        residual_check_list = {}
    end
    if #residual_check_list == 0 then
        after_finish_cb(known_permission)
        return
    end
    local permission_to_check = residual_check_list[1]
    local permission_name = permission_to_check["权限名"]
    local permission_selector = permission_to_check["选择器"]
    -- print(("check %s: %s"):format(permission_name, permission_selector))
    residual_check_list = { unpack(residual_check_list, 2) }
    player:check_condition(permission_selector,
        function(has_permission)
            -- print(("check %s: %s"):format(permission_name, has_permission))
            known_permission[permission_name] = has_permission
            check_player_permission_by_check_list(player, known_permission, residual_check_list, after_finish_cb)
        end
    )
end

function handle_game_chat_with_permission_check(chat, name)
    local player_info = player_cache[name]
    if not player_info then
        local player, found = omega.players.get_player_by_name(name)
        if not found then
            print(themes("default"):cant_find(name))
            return
        end
        local cache_player_info_and_handle_game_chat = function(permission)
            player_permission[name] = permission
            local option = player_config[name]
            if option == nil then
                option = { must_omg = false, loose = true }
                player_config[name] = option
            end
            local talk = function(msg)
                talk_to(name, msg)
            end
            player_info = { name = name, player = player, permission = permission, option = option, print = talk }
            player_cache[name] = player_info
            handle_game_chat_with_permission(chat, player_info)
        end

        local permission = player_permission[name]
        if not permission then
            local is_op, known = player:is_op()
            permission = { op = is_op }
            check_player_permission_by_check_list(player, permission, permission_check_list, function(permission)
                cache_player_info_and_handle_game_chat(permission)
            end)
        else
            local player, found = omega.players.get_player_by_name(name)
            if found then
                local is_op, known = player:is_op()
                if known then
                    permission.op = is_op
                end
            end
            cache_player_info_and_handle_game_chat(permission)
        end
    else
        local player, found = omega.players.get_player_by_name(name)
        if found then
            local is_op, known = player:is_op()
            if known then
                player_info.permission.op = is_op
            end
        end
        handle_game_chat_with_permission(chat, player_info)
    end
end

function handle_game_chat_with_permission(chat, player_info)
    local selections = react_user_input(root_menu, chat,
        player_info.permission, player_info.print, player_info.option.must_omg, player_info.option.loose)
    if not selections then return end
    ask_player_input(selections, player_info)
end

function ask_player_input(selections, player_info)
    player_info.player:intercept_just_next_input(function(chat)
        local selections = react_user_selection(selections, chat,
            player_info.permission, player_info.print, player_info.option.loose)
        if not selections then return end
        ask_player_input(selections, player_info)
    end)
end

root_menu:add_entry({
    triggers = { "启用菜单前缀词" },
    argument_hint = "",
    usage = ("必须输入 omg 前缀才可使用功能"),
    on_trig_callback = function(chat)
        player_config[chat.name].must_omg = true
        player_cache[chat.name].option.must_omg = true
        store_must_omg_option(chat.name, true)
    end
})

root_menu:add_entry({
    triggers = { "关闭菜单前缀词" },
    argument_hint = "",
    usage = ("不需要输入 omg 前缀即可使用功能"),
    on_trig_callback = function(chat)
        player_config[chat.name].must_omg = false
        player_cache[chat.name].option.must_omg = false
        store_must_omg_option(chat.name, false)
    end
})

root_menu:add_entry({
    triggers = { "启用模糊表达" },
    argument_hint = "",
    usage = "关键词间可以没有空格",
    on_trig_callback = function(chat)
        player_config[chat.name].loose = true
        player_cache[chat.name].option.loose = true
        store_loose_option(chat.name, true)
    end
})
root_menu:add_entry({
    triggers = { "关闭模糊表达" },
    argument_hint = "",
    usage = "关键词间必须有空格",
    on_trig_callback = function(chat)
        player_config[chat.name].loose = false
        player_cache[chat.name].option.loose = false
        store_loose_option(chat.name, false)
    end
})

print(("game menu loaded with trigger [%s]"):format(table.concat(menu_trigger_words, ", ")))
local player_change_poller = omega.players.make_player_change_poller()
local function on_player_change(player, action)
    local name, found = player:get_username()
    local uuid_string, found = player:get_uuid_string()
    local online, found = player:still_online()
    local action = action -- exist/online/offline
    print(("player: %s (%s) %s (online=%s)"):format(name, uuid_string, action, online))
    if action == "offline" then
        player_permission[name] = nil
        player_cache[name] = nil
    end
end

-- mux_poller:poll(game_menu):poll(game_chat):poll(omega.players.resp):poll(player_change_poller)
-- while mux_poller:block_has_next() do
--     local event = mux_poller:block_get_next()
--     if event.type == game_menu then
--         root_menu:add_entry(event.data)
--     elseif event.type == game_chat then
--         local chat = event.data
--         handle_game_chat(chat)
--     elseif event.type == omega.players.resp then
--         local resp = event.data
--         resp.cb(resp.output)
--     elseif event.type == player_change_poller then
--         local player = event.data.player
--         local action = event.data.action
--         on_player_change(player, action)
--     end
-- end

--------------------------美化风格拓展部分----------------------------

--- 默认风格配置, 如果要在风格添加新的字段，直接在这填即可
--- 文本类为string
--- 格式类必须含有%s
--- 是否类为boolean
local default_menu_style_config = {
    ["菜单头文本"] = "",
    ["条件渲染1文本"] = {},
    ["状态栏是否向上合并打印"] = false,
    ["op显示文本"] = "op",
    ["使用菜单显示文本"] = "使用菜单",
    ["创造特权显示文本"] = "创造特权",
    ["状态关闭文本格式"] = "§b[§c%s×§b]",
    ["永久状态头文本"] = "",
    ["永久状态尾文本"] = "",
    ["状态头文本"] = "§b权限: ",
    ["状态尾文本"] = "",
    ["状态开启文本格式"] = "§b[§a%s√§b]",
    ["无状态时文本"] = "",
    ["选项表前文本"] = "",
    ["选项表前文本是否向上合并打印"] = false,
    ["条件渲染2文本"] = {},
    ["选项前文本"] = "",
    ["选项后文本"] = "",
    ["选项参数提示格式"] = "§b%s ",
    ["选项合并打印条数"] = 1,
    ["选项名格式"] = "§b§l%s",
    ["选项头格式"] = "§b[ §6%s§b ] ",
    ["选项描述格式"] = " §f%s",
    ["条件渲染3文本"] = {},
    ["条件渲染4文本"] = {},
    ["条件渲染5文本"] = {},
    ["分页前文本"] = "",
    ["分页前文本是否向上合并打印"] = false,
    ["分页后文本"] = "",
    ["翻页模式每页最大选项数"] = 0,
    ["翻页序号格式"] = "§d§l[ §6%s§d§l ]",
    ["上页显示格式"] = "%s §b§l上页 ",
    ["下页显示格式"] = " §b§l下页 %s",
    ["页码是否展开显示"] = true,
    ["页码展开最大显示数"] = 3,
    ["非当前页码格式"] = "§7%s",
    ["当前页码格式"] = "§e§l%s",
    ["翻页模式页数/总页数显示格式"] = "§7%s/%s",
    ["输入提示前文本"] = "",
    ["输入提示前文本是否向上合并打印"] = false,
    ["输入提示后文本"] = "",
    ["菜单尾文本"] = "",
    ["菜单尾文本是否向上合并打印"] = false,
    ["是否强制顺序打印选项"] = false,
    ["若为根菜单是否打印权限信息"] = true,
    ["若有前缀和模糊是否打印状态"] = false,
}

--- 值生成器，可从跨插件通信api或json配置中获取值，优先api
--- @class ValueGenerator
local ValueGenerator = { _cname = "ValueGenerator" }

--- @return ValueGenerator 字符串生成器实例
local function newValueGenerator()
    --- @class ValueGenerator
    local instance = {
    }
    setmetatable(instance, { __index = ValueGenerator })
    return instance
end

-- 从风格配置中写入值
--- @param value any @字段的值
function ValueGenerator:set_value_from_config(value)
    self.config_value = value
    return self
end

-- 从注册的api中写入值
--- @param data table @注册的api名，与可能的参数
function ValueGenerator:set_value_from_api(data)
    if data.option_name then
        self.options = self.options or {}
        self.options[data.option_name] = data.api_name
    else
        self.api_name = data.api_name
    end
    return self
end

-- 获取值
--- @vararg ... @玩家名与可能的参数
function ValueGenerator:get_value(...)
    local args = { ... }
    local playername = args[1]
    local option_name
    if #args > 1 then
        option_name = args[2]
    end
    if (not option_name or not self.options or not self.options[option_name]) and self.api_name then
        local value = coromega:call_other_plugin_api(self.api_name, { playername }) or self.config_value
        -- 格式验证
        if type(self.config_value) == "table" or (type(value) == type(self.config_value)) then
            return value
        end
    elseif option_name and self.options and self.options[option_name] then
        local value = coromega:call_other_plugin_api(self.options[option_name], { playername }) or self.config_value
        -- 格式验证
        if type(self.config_value) == "table" or (type(value) == type(self.config_value)) then
            return value
        end
    end
    return self.config_value
end

function ValueGenerator:set_replace(replace)
    self.replace = replace
    return self
end

-- 命令发送器
-- 对于同一个玩家，它会等上一条命令生效后才会发送下一条命令
--- @class CmdSender
local CmdSender = { _cname = "CmdSender" }

--- @return CmdSender 命令发送器实例
local function newCmdSender()
    --- @class CmdSender
    local instance = {
        -- 玩家令牌信息
        player_token = {},
        -- 玩家等待发送队列
        player_cmds_list = {}
    }
    setmetatable(instance, { __index = CmdSender })
    return instance
end

function CmdSender:Send(playername)
    -- 如果没有等待发送的命令则退出
    if #self.player_cmds_list[playername] == 0 then
        return
    end
    --没收令牌
    self.player_token[playername] = false
    -- 弹出队头发送
    local cmd = table.remove(self.player_cmds_list[playername], 1)
    coromega:send_wo_cmd(cmd)
    -- coromega:sleep(1/20)
    --返还令牌
    self.player_token[playername] = true
    --如果队列中还有剩余元素则继续Send
    self:Send(playername)
end

-- 将要发送的个人命令放入发送器队列中，如果有令牌它会自动发的
function CmdSender:AddtoQueue(playername, cmd)
    self.player_cmds_list[playername] = self.player_cmds_list[playername] or {}
    table.insert(self.player_cmds_list[playername], cmd)

    self.player_token[playername] = self.player_token[playername] or true
    if self.player_token[playername] then
        --令牌存在则直接发送
        self:Send(playername)
    end
end

-- 菜单结构工厂，用来生成临时的分页结构
--- @class MenuFactory
local MenuFactory = { _cname = "MenuFactory" }

--- @return MenuFactory 菜单结构工厂实例
local function newMenuFactory()
    --- @class MenuFactory
    local instance = {
    }
    setmetatable(instance, { __index = MenuFactory })
    return instance
end

-- 计算页数
---@param totalItems integer @总选项数
---@param itemsPerPage integer @每页最大总项数
---@return integer @总页数
---@return table @分组情况，数组类型[]page，下标表示这是第几页的信息，page.from指从第几项开始，page.to表示到第几项结束，page.previous表示是否有上页，pre.next表示是否有下页
function MenuFactory:calculatePagination(totalItems, itemsPerPage)
    local pages = {}
    local currentPage = 1
    local currentItem = 1

    if itemsPerPage < 2 then
        itemsPerPage = 2
    end

    -- 如果总条目数大于每页最大条目数，那么每页实际最大条目数减1
    local actualItemsPerPage
    if totalItems > itemsPerPage then
        actualItemsPerPage = itemsPerPage - 1
    else
        actualItemsPerPage = itemsPerPage
    end
    while currentItem <= totalItems do
        local page = { from = currentItem, previous = currentPage > 1 }

        -- 计算当前页的结束项
        local endItem = currentItem + actualItemsPerPage - 1
        if endItem > totalItems then
            endItem = totalItems
        end
        page.to = endItem
        -- 检查是否有下一页
        page.next = endItem < totalItems

        pages[currentPage] = page

        -- 更新当前项和当前页码以准备下一页的计算
        currentItem = endItem + 1
        currentPage = currentPage + 1
    end

    return currentPage - 1, pages
end

-- 生成翻页模式的selections及其打印列表
--- @param menu any                     @原始菜单实例
--- @param player_permission any        @唤醒玩家的权限
--- @param max_num_of_options number    @单页最大项数
--- @param style_factory StyleFactory   @使用的风格工厂
--- @return table 打印表
function MenuFactory:page_mode(menu, player_permission, max_num_of_options, style_factory, selections)
    -- 选项名回调
    local selectable = newTriggers()
    -- 数字回调
    local num_selectable = newTriggers()
    -- 当前页总项数
    local valid_count = 0
    -- 要打印的菜单表
    local display_list = {}
    -- 分页
    local totalPages, pages
    -- 当前页
    local current_page
    -- 所有页转为不可关键词触发的页菜单
    local page_menus = {}
    -- 如果是页菜单则跳过分页流程
    -- 能打印的项
    local options = {}
    if not menu.pages then
        for _, item in ipairs(menu._items) do
            -- 筛选掉你在配置里写了选项，但实际并没有这个项目实体的项
            if item.item then
                -- 用菜单要求的权限核查玩家有的权限
                if (not item.permission) or item.permission:check(player_permission) then
                    table.insert(options, item)
                end
            end
        end
        -- 加入可能的返回选项
        if menu._parent then
            local parent_menu = { type = "sub_menu", key = "返回", description = " 返回上一级菜单", item = menu._parent }
            table.insert(options, parent_menu)
        end
        totalPages, pages = self:calculatePagination(#options, max_num_of_options)
        current_page = 1
        for index, page in ipairs(pages) do
            local empty_menu = newMenuGroup({}, nil, nil)
            for i = page.from, page.to, 1 do
                table.insert(empty_menu._items, options[i])
            end
            page_menus[index] = empty_menu
        end
        for index, menu_i in ipairs(page_menus) do
            -- 页菜单专属字段
            menu_i.pages = pages
            menu_i.total_pages = totalPages
            menu_i.page_menus = page_menus
            menu_i.current_page = index
            menu_i.style_factory = style_factory
            menu_i.options = options
            menu_i.is_root_menu = menu == root_menu
        end
    else
        totalPages, pages = menu.total_pages, menu.pages
        current_page = menu.current_page
        page_menus = menu.page_menus
        options = menu.options
    end

    -- 当前页转为打印列表
    for i = pages[current_page].from, pages[current_page].to, 1 do
        -- 这个表项可以打印啦，迭代计数器
        valid_count = valid_count + 1
        if options[i].type == "entry" then -- 这是一个单项
            -- 放入打印表
            display_list[valid_count] = options[i]
            -- 选项名回调放入其所有触发词
            selectable:add(options[i].item.triggers, options[i])
            -- 数字回调嘛
            num_selectable:add({ ("%s"):format(valid_count) }, options[i])
        elseif options[i].type == "sub_menu" then -- 这是一个子菜单项
            -- 跟上面一样
            display_list[valid_count] = options[i]
            selectable:add({ options[i].key }, options[i])
            num_selectable:add({ ("%s"):format(valid_count) }, options[i])
        end
    end

    -- 将当前页可能的上下页写入打印表，只要有一项则两项都要显示（为了美观）
    if pages[current_page].previous or pages[current_page].next then
        -- 写上页
        if pages[current_page].previous then
            -- 有上页
            valid_count = valid_count + 1
            local pre_page = {
                type = "sub_menu",
                key = "上页",
                description = "",
                item = page_menus[current_page - 1],
                merge = true, -- 与选项合并打印
            }
            display_list[valid_count] = pre_page
            selectable:add({ pre_page.key }, pre_page)
            num_selectable:add({ ("%s"):format(valid_count) }, pre_page)
        else
            -- 没有上页，但是有下页，写入本页作为上页
            valid_count = valid_count + 1
            local pre_page = {
                type = "sub_menu",
                key = "上页",
                description = "",
                item = page_menus[current_page],
                merge = true, -- 与选项合并打印
            }
            display_list[valid_count] = pre_page
            selectable:add({ pre_page.key }, pre_page)
            num_selectable:add({ ("%s"):format(valid_count) }, pre_page)
        end
        -- 写下页
        if pages[current_page].next then
            -- 有下页
            valid_count = valid_count + 1
            local next_page = {
                type = "sub_menu",
                key = "下页",
                description = "",
                item = page_menus[current_page + 1],
                merge = true, -- 与上页合并打印
            }
            display_list[valid_count] = next_page
            selectable:add({ next_page.key }, next_page)
            num_selectable:add({ ("%s"):format(valid_count) }, next_page)
        else
            -- 没有下页，但是有上页，写入本页作为下页
            valid_count = valid_count + 1
            local next_page = {
                type = "sub_menu",
                key = "下页",
                description = "",
                item = page_menus[current_page],
                merge = true, -- 与上页合并打印
            }
            display_list[valid_count] = next_page
            selectable:add({ next_page.key }, next_page)
            num_selectable:add({ ("%s"):format(valid_count) }, next_page)
        end
    end

    -- 补全selections
    selections.selectable = selectable
    selections.num_selectable = num_selectable
    selections.can_back = selections.can_back or false
    selections.valid_count = valid_count
    selections.current_page = current_page
    selections.total_pages = totalPages
    selections.is_root_menu = menu.is_root_menu or (menu == root_menu)

    return display_list
end

-- 生成普通模式的selections及其打印列表
---@param menu table @目标菜单实体
function MenuFactory:normal_mode(menu, player_permission, selections)
    -- 选项名回调
    local selectable = newTriggers()
    -- 数字回调
    local num_selectable = newTriggers()
    -- 总项数
    local valid_count = 0
    -- 要打印的菜单表
    local display_list = {}
    -- 根据权限迭代计数器，注入回调
    for _, item in ipairs(menu._items) do
        -- 筛选掉你在配置里写了选项，但实际并没有这个项目实体的项
        if item.item then
            -- 用菜单要求的权限核查玩家有的权限
            if (not item.permission) or item.permission:check(player_permission) then
                -- 这个表项可以打印啦，迭代计数器
                valid_count = valid_count + 1
                if item.type == "entry" then -- 这是一个单项
                    -- 放入打印表
                    display_list[valid_count] = item
                    -- 选项名回调放入其所有触发词
                    selectable:add(item.item.triggers, item)
                    -- 数字回调嘛
                    num_selectable:add({ ("%s"):format(valid_count) }, item)
                elseif item.type == "sub_menu" then -- 这是一个子菜单项
                    -- 跟上面一样
                    display_list[valid_count] = item
                    selectable:add({ item.key }, item)
                    num_selectable:add({ ("%s"):format(valid_count) }, item)
                end
            end
        end
    end
    -- 看看要不要加返回
    if menu._parent then
        valid_count = valid_count + 1
        local parent_menu = { type = "sub_menu", key = "返回", description = " 返回上一级菜单", item = menu._parent }
        -- 跟上面的一样
        display_list[valid_count] = parent_menu
        num_selectable:add({ ("%s"):format(valid_count) }, parent_menu)
        selectable:add({ "返回" }, parent_menu)
        selections.can_back = true
    end
    -- 补全selections
    selections.selectable = selectable
    selections.num_selectable = num_selectable
    selections.can_back = selections.can_back or false
    selections.valid_count = valid_count
    selections.is_root_menu = menu == root_menu
    selections.total_pages = 1

    return display_list
end

--- 打印工厂，根据传入参数返回一个字符串列表
--- @class PrintFactory
local PrintFactory = { _cname = "PrintFactory" }

local function newPrintFactory()
    --- @class PrintFactory
    local instance = {
        -- 待打印的列表
        print_list = {}
    }
    setmetatable(instance, { __index = PrintFactory })
    return instance
end

function PrintFactory:add_string(str, merge)
    if str == "" or (type(str) == "table" and #str == 0) then
        return
    end
    if merge and #self.print_list > 0 then
        if type(str) == "table" then
            local has_merge = false
            for _, value in ipairs(str) do
                if not has_merge then
                    self.print_list[#self.print_list] = self.print_list[#self.print_list] .. tostring(value)
                    has_merge = true
                else
                    table.insert(self.print_list, tostring(value))
                end
            end
        else
            self.print_list[#self.print_list] = self.print_list[#self.print_list] .. tostring(str)
        end
    else
        table.insert(self.print_list, tostring(str))
    end
end

function PrintFactory:get_list()
    return self.print_list
end

--- 风格工厂，每个风格对应都有一个
--- @class StyleFactory
local StyleFactory = { _cname = "StyleFactory" }

--- 根据风格生成相应的风格工厂
--- @param expander Expansion @所属的拓展器
--- @param style_config table @风格配置
--- @return StyleFactory 风格工厂实例
local function newStyleFactory(expander, style_config)
local function deepcopy(orig)
        local orig_type = type(orig)
        local copy
        if orig_type == 'table' then
          copy = {}
          for orig_key, orig_value in next, orig, nil do
            copy[orig_key] = deepcopy(orig_value)
          end
        else 
          copy = orig
        end
        return copy
      end
    --- @class StyleFactory
    --- @field menu_style table<string, ValueGenerator> @转为值生成器的风格配置
    local instance = {
        raw_config = style_config,
style_config = deepcopy(style_config),
        expander = expander,
        menu_style = {}
    }
    setmetatable(instance, { __index = StyleFactory })
    -- 核查补全配置
    local replace_list = instance:ensure_style_completeness(default_menu_style_config)
    -- 配置转为值生成器
    instance:replace_value_with_generator(replace_list)
    -- 玩家聊天栏打印机
    instance.print = function(playername, msg, ...)
        msg = string.format(msg, ...)
        if instance.menu_style["是否强制顺序打印选项"]:get_value(playername) then
            instance.expander.cmdsender:AddtoQueue(playername,
                ("tellraw %s {\"rawtext\":[{\"text\":\"%s\"}]}"):format(playername, msg))
        else
            talk_to(playername, msg)
        end
    end
    return instance
end

--核查风格类型，用默认风格补全风格
--- @param default_menu_style table @用来补充的默认风格
function StyleFactory:ensure_style_completeness(default_menu_style)
local replace_list = {}
    for key, value in pairs(default_menu_style) do
        if type(value) == "string" then
            -- 字符串类型核查
            if self.style_config[key] and tostring(self.style_config[key]) then
                self.style_config[key] = tostring(self.style_config[key])
            else
                self.style_config[key] = value
                replace_list[key] = true
            end
        elseif type(value) == "number" then
            -- 数字类型核查
            if self.style_config[key] and tonumber(self.style_config[key]) then
                self.style_config[key] = tonumber(self.style_config[key])
            else
                self.style_config[key] = value
                replace_list[key] = true
            end
        else
            -- 剩下的随便了，反正有布尔型兜底
            if self.style_config[key] == nil then
                self.style_config[key] = value
replace_list[key] = true
            end
        end
    end
return replace_list
end

-- 将风格配置字段替换为值生成器
function StyleFactory:replace_value_with_generator(replace_list)
    for key, value in pairs(self.style_config) do
        self.menu_style[key] = newValueGenerator():set_value_from_config(value):set_replace(replace_list[key] or false)
    end
end

-- 获取显示页码的数组
---@param totalPages integer
---@param currentPage integer
---@param displayCount integer
---@return table
function StyleFactory:generatePagination(totalPages, currentPage, displayCount)
    local pages = {}
    local halfWindow = math.floor(displayCount / 2)

    local startPage = math.max(1, currentPage - halfWindow)

    local endPage = math.min(totalPages, startPage + displayCount - 1)

    if startPage == 1 then
        endPage = math.min(totalPages, displayCount)
    end

    if endPage == totalPages then
        startPage = math.max(1, totalPages - displayCount + 1)
    end

    for i = startPage, endPage do
        table.insert(pages, i)
    end

    return pages
end

-- 获取数据并打印菜单
--- @param data table @截胡原来菜单要打印的那些数据
--- @param selections table @omg原始菜单要拿去进行选项输入回调的表
function StyleFactory:print_menu_and_change_selections(data, selections)
    selections.key = data.entry.key
    -- 本次打印列表
    local display_list
    --- 进行翻页模式相关的处理
    local max_num_of_options = self.menu_style["翻页模式每页最大选项数"]:get_value(data.playername)
    if not max_num_of_options or max_num_of_options == 0 then
        -- 正常模式的菜单
        display_list = self.expander.menu_factory:normal_mode(data.menu, data.player_permission, selections)
    else
        -- 翻页模式的菜单
        display_list = self.expander.menu_factory:page_mode(data.menu, data.player_permission, max_num_of_options, self,
            selections)
    end

    -- 状态栏文本生成
    local status_str = ""
    local status_list = self.expander:get_status_list(display_list, data.playername, selections)
    -- 状态栏若不为空则打印状态头
    local get_status_head = false
    --如果有前缀和模糊选项则打印状态
    if self.menu_style["若有前缀和模糊是否打印状态"]:get_value(data.playername) then
        for key, value in pairs(display_list) do
            -- 忽略子菜单项
            if value.item.triggers then
                if value.item.triggers[1] == "启用菜单前缀词" or value.item.triggers[1] == "关闭菜单前缀词" then
                    get_status_head = true
                    status_list["菜单前缀"] = player_config[data.playername].must_omg
                end
                if value.item.triggers[1] == "启用模糊表达" or value.item.triggers[1] == "关闭模糊表达" then
                    get_status_head = true
                    status_list["模糊表达"] = player_config[data.playername].loose
                end
            end
        end
    end
    if self.menu_style["若为根菜单是否打印权限信息"]:get_value(data.playername) and selections.is_root_menu then
        get_status_head = true
        status_list[self.menu_style["使用菜单显示文本"]:get_value(data.playername)] = data.player_permission["使用菜单"]
        status_list[self.menu_style["创造特权显示文本"]:get_value(data.playername)] = data.player_permission["创造特权"]
        status_list[self.menu_style["op显示文本"]:get_value(data.playername)] = data.player_permission["op"]
    end
    for key, value in pairs(status_list) do
        get_status_head = true
        if value then
            status_str = (self.menu_style["状态开启文本格式"]:get_value(data.playername)):format(key) .. "§r" .. status_str
        else
            status_str = (self.menu_style["状态关闭文本格式"]:get_value(data.playername)):format(key) .. "§r" .. status_str
        end
    end
    if get_status_head then
        status_str = self.menu_style["状态头文本"]:get_value(data.playername) ..
            "§r" .. status_str .. "§r" .. self.menu_style["状态尾文本"]:get_value(data.playername)
    else
        status_str = self.menu_style["无状态时文本"]:get_value(data.playername)
    end
    local persisten_status_header = self.menu_style["永久状态头文本"]:get_value(data.playername)
    local persisten_status_tail = self.menu_style["永久状态尾文本"]:get_value(data.playername)
    if persisten_status_header ~= "" or persisten_status_tail ~= "" then
        status_str = persisten_status_header .. "§r" .. status_str .. "§r" .. persisten_status_tail
    end

    -- 选项文本生成
    local options_str = self.menu_style["选项表前文本"]:get_value(data.playername)
    local options_str_list = {}
    local max_lenght = self.menu_style["选项合并打印条数"]:get_value(data.playername)
    if max_lenght < 1 then
        max_lenght = 1
    end
    local page_option_str = ""
    local merger_str = false
    -- 选项前文本与选项之间不需要自动换行
    local first_line_break = false
    for index, value in ipairs(display_list) do
        if options_str ~= "" and first_line_break then
            options_str = options_str .. "\n"
        else
            first_line_break = true
        end
        if value.key then --子菜单类型
            if value.merge then
                if value.key == "上页" then
                    -- 页码文本
                    local show_pages_list
                    if not self.menu_style["页码是否展开显示"]:get_value(data.playername) then
                        show_pages_list = (self.menu_style["翻页模式页数/总页数显示格式"]:get_value(data.playername)):format(
                            selections.current_page, selections.total_pages)
                    else
                        local show_page_count = self.menu_style["页码展开最大显示数"]:get_value(data.playername)
                        local show_pages = self:generatePagination(selections.total_pages, selections.current_page,
                            show_page_count)
                        for _, num in ipairs(show_pages) do
                            if show_pages_list then
                                show_pages_list = show_pages_list .. " "
                            else
                                show_pages_list = ""
                            end
                            if num ~= selections.current_page then
                                show_pages_list = show_pages_list ..
                                    (self.menu_style["非当前页码格式"]:get_value(data.playername)):format(num)
                            else
                                show_pages_list = show_pages_list ..
                                    (self.menu_style["当前页码格式"]:get_value(data.playername)):format(num)
                            end
                        end
                    end
                    -- 上页显示格式加入页码文本
                    merger_str = true
                    options_str = string.gsub(options_str, "\n$", "")
                    page_option_str = page_option_str ..
                        "§r" ..
                        (self.menu_style["上页显示格式"]:get_value(data.playername)):format((self.menu_style["翻页序号格式"]:get_value(data.playername))
                            :format(index))
                    page_option_str = page_option_str .. "§r" .. show_pages_list
                else
                    page_option_str = page_option_str ..
                        "§r" ..
                        (self.menu_style["下页显示格式"]:get_value(data.playername)):format((self.menu_style["翻页序号格式"]:get_value(data.playername))
                            :format(index))
                end
            else
                options_str = options_str ..
                    "§r" ..
                    (self.menu_style["选项前文本"]:get_value(data.playername, value.key) .. "§r" .. self.menu_style["选项头格式"]:get_value(data.playername, value.key) .. "§r" .. self.menu_style["选项名格式"]:get_value(data.playername, value.key) .. "§r" .. self.menu_style["选项描述格式"]:get_value(data.playername, value.key) .. "§r" .. self.menu_style["选项后文本"]:get_value(data.playername, value.key))
                    :format(index, value.key, value.description)
            end
        else
            options_str = options_str ..
                "§r" ..
                (self.menu_style["选项前文本"]:get_value(data.playername, value.item.triggers[1]) .. "§r" .. self.menu_style["选项头格式"]:get_value(data.playername, value.item.triggers[1]) .. "§r" .. self.menu_style["选项名格式"]:get_value(data.playername, value.item.triggers[1]) .. "§r" .. self.menu_style["选项参数提示格式"]:get_value(data.playername, value.item.triggers[1]) .. "§r" .. self.menu_style["选项描述格式"]:get_value(data.playername, value.item.triggers[1]) .. "§r" .. self.menu_style["选项后文本"]:get_value(data.playername, value.item.triggers[1]))
                :format(index, value.item.triggers[1], value.item.hint or "", value.item.usage)
        end
        if not merger_str and (index % max_lenght) == 0 then
            table.insert(options_str_list, options_str)
            options_str = ""
        end
    end
    if options_str ~= "" then
        table.insert(options_str_list, options_str)
    end

    -- 打印输入提示前文本
    local menu_end_str = self.menu_style["输入提示前文本"]:get_value(data.playername)

    --打印输入提示语
    if selections.valid_count == 0 then
        menu_end_str = menu_end_str .. "§r" .. themes("default"):title("cancel_selections")
    elseif selections.valid_count == 1 then
        if selections.can_back then
            menu_end_str = menu_end_str .. "§r" .. themes("default"):title("valid_count_one_canback_selections")
        else
            menu_end_str = menu_end_str .. "§r" .. themes("default"):title("valid_count_one_notcanback_selections")
        end
    else
        menu_end_str = menu_end_str .. "§r" ..
            themes("default"):tips_for_selections(("%s"):format(selections.valid_count))
    end
    menu_end_str = menu_end_str .. "§r" .. self.menu_style["输入提示后文本"]:get_value(data.playername)

    local print_factory = newPrintFactory()
    local text_to_render_1 = self.menu_style["条件渲染1文本"]:get_value(data.playername)
    local text_to_render_2 = self.menu_style["条件渲染2文本"]:get_value(data.playername)
    local text_to_render_3 = self.menu_style["条件渲染3文本"]:get_value(data.playername)
    local text_before_pages = self.menu_style["分页前文本"]:get_value(data.playername)
    local text_after_pages = self.menu_style["分页后文本"]:get_value(data.playername)
    local text_to_render_4 = self.menu_style["条件渲染4文本"]:get_value(data.playername)
    local text_to_render_5 = self.menu_style["条件渲染5文本"]:get_value(data.playername)
    local text_menu_end = self.menu_style["菜单尾文本"]:get_value(data.playername)
    print_factory:add_string(self.menu_style["菜单头文本"]:get_value(data.playername))
    if self.menu_style["状态栏是否向上合并打印"]:get_value(data.playername) then
        print_factory:add_string(status_str, true)
    else
        print_factory:add_string(text_to_render_1)
        print_factory:add_string(status_str)
    end
    local merge_options = false
    if self.menu_style["选项表前文本是否向上合并打印"]:get_value(data.playername) then
        print_factory:add_string(options_str, true)
        for _, value in ipairs(options_str_list) do
            if merge_options then
                print_factory:add_string(value)
            else
                print_factory:add_string(value, true)
                merge_options = true
            end
        end
    else
        print_factory:add_string(text_to_render_2)
        for _, value in ipairs(options_str_list) do
            print_factory:add_string(value)
        end
    end
    if page_option_str ~= "" and false then --self.menu_style["分页前文本是否向上合并打印"]:get_value(data.playername) then
        print_factory:add_string(text_before_pages, true)
        print_factory:add_string(page_option_str, true)
        print_factory:add_string(text_after_pages, true)
    elseif page_option_str ~= "" then
        print_factory:add_string(text_to_render_3)
        print_factory:add_string(text_before_pages)
        print_factory:add_string(page_option_str, true)
        print_factory:add_string(text_after_pages, true)
    end
    if self.menu_style["输入提示前文本是否向上合并打印"]:get_value(data.playername) then
        print_factory:add_string(menu_end_str, true)
    else
        print_factory:add_string(text_to_render_4)
        print_factory:add_string(menu_end_str)
    end
    if self.menu_style["菜单尾文本是否向上合并打印"]:get_value(data.playername) then
        print_factory:add_string(text_menu_end, true)
    else
        print_factory:add_string(text_to_render_5)
        print_factory:add_string(text_menu_end)
    end

    local list = print_factory:get_list()
    for _, value in ipairs(list) do
        self.print(data.playername, value)
    end
end

--- 自定义拓展
--- @class Expansion
local Expansion = { _cname = "Expansion" }

--- 拓展器创建
--- @param raw_config table @omg菜单原始配置表
--- @return Expansion 拓展器实例
local function newExpander(raw_config)
    --- @class Expansion
    local instance = {
        _config = raw_config,
        -- 风格工厂表
        style_factory_list = {},
        -- 命令发送器
        cmdsender = newCmdSender(),
        -- 菜单结构工厂
        menu_factory = newMenuFactory(),
        -- 状态表
        status_list = {},
        -- 指定子菜单显示状态表
        menu_status_list = {},
        -- 根菜单显示状态表
        root_menu_status_list = {}
    }
    setmetatable(instance, { __index = Expansion })
    return instance
end

--- 根据风格获取相应的风格工厂
--- @param style_name string @风格名
--- @return StyleFactory 风格工厂实例
function Expansion:get_style_factory(style_name)
    self._config["美化风格"] = self._config["美化风格"] or {}
    -- 从总配置中获取目标风格配置
    local style_config
    if style_name then
        style_config = self._config["美化风格"][style_name] or {}
    else
        -- 风格不存在则使用默认配置并命名为"#默认风格"
        style_name = "#默认风格"
        style_config = {}
    end
    -- 从风格工厂表里获取对应工厂，不存在则创建
    if not self.style_factory_list[style_name] then
        self.style_factory_list[style_name] = newStyleFactory(self, style_config)
    end
    return self.style_factory_list[style_name]
end

--- 注册api到对应值生成器
--- @param style_name string @风格名
--- @param field_name string @风格字段名
--- @param api_name string @api名
function Expansion:register_api_to_style_generator(style_name, field_name, api_name, option_name)
    if not style_name then
        -- 没写风格名，视为改默认风格
        style_name = "#默认风格"
    end
    local style_factory = self:get_style_factory(style_name)
    if not api_name or not field_name or not style_factory.menu_style[field_name] then
        -- 没写必要参数或者指定字段不存在，不改
        return
    end
    if option_name and (field_name == "选项前文本" or field_name == "选项头格式" or field_name == "选项名格式" or field_name == "选项参数提示格式" or field_name == "选项描述格式" or field_name == "选项后文本") then
        style_factory.menu_style[field_name]:set_value_from_api({ api_name = api_name, option_name = option_name }):set_replace(false)
    else
        style_factory.menu_style[field_name]:set_value_from_api({ api_name = api_name }):set_replace(false)
    end
end

--- 遍历菜单添加相应的风格工厂
--- @param root_menu table @根菜单实体
function Expansion:add_style_factory_to_root_menu(root_menu)
    -- 根菜单的工厂
    root_menu.style_factory = self:get_style_factory(self._config["主菜单风格"])
    -- 获取子菜单的风格配置
    local sub_menu_style_name_list = {}
    for _, cfg in ipairs(self._config["菜单组织结构和权限选项"]) do
        if cfg["类型"] == "子菜单" then
            sub_menu_style_name_list[cfg["名称"]] = cfg["菜单风格"]
        end
    end
    -- 遍历下属包装子菜单
    for _, item in ipairs(root_menu._items) do
        if item.type == "sub_menu" then
            -- 对包装子菜单中的真正子菜单实体注入工厂
            item.item.style_factory = self:get_style_factory(sub_menu_style_name_list[item.key])
        end
    end
end

--- 根据选项列表获取其中要显示状态的选项及其状态
function Expansion:get_status_list(display_list, playername, selections)
    local t = {}
    -- 如果要打印的表项在api注册表里注册了则调用api
    for _, value in ipairs(display_list) do
        -- 是单项
        if value.item.triggers and value.item.triggers[1] and self.status_list[value.item.triggers[1]] then
            local shower = self.status_list[value.item.triggers[1]]
            if shower.api_name then
                local result = coromega:call_other_plugin_api(shower.api_name, { playername })
                if type(result) == type(true) then
                    t[shower.show_str] = result
                else
                    t[shower.show_str] = shower.field_value or false
                end
            else
                t[shower.show_str] = shower.field_value or false
            end
            -- 是子菜单
        elseif value.item.key and self.status_list[value.item.key] then
            local shower = self.status_list[value.item.key]
            if shower.api_name then
                local result = coromega:call_other_plugin_api(shower.api_name, { playername })
                if type(result) == type(true) then
                    t[shower.show_str] = result
                else
                    t[shower.show_str] = shower.field_value or false
                end
            else
                t[shower.show_str] = shower.field_value or false
            end
        end
    end
    -- 如果当前子菜单有指定状态显示则加上
    if selections.key and self.menu_status_list[selections.key] then
        local shower_list = self.menu_status_list[selections.key]
        for _, shower in ipairs(shower_list) do
            if shower.api_name then
                local result = coromega:call_other_plugin_api(shower.api_name, { playername })
                if type(result) == type(true) then
                    t[shower.show_str] = result
                else
                    t[shower.show_str] = shower.field_value or false
                end
            else
                t[shower.show_str] = shower.field_value or false
            end
        end
    end
    -- 如果是根菜单则加上根菜单指定状态显示
    if selections.is_root_menu then
        for _, shower in ipairs(self.root_menu_status_list) do
            if shower.api_name then
                local result = coromega:call_other_plugin_api(shower.api_name, { playername })
                if type(result) == type(true) then
                    t[shower.show_str] = result
                else
                    t[shower.show_str] = shower.field_value or false
                end
            else
                t[shower.show_str] = shower.field_value or false
            end
        end
    end
    return t
end

--- 指定哪些选项在菜单中显示时同时在状态栏显示其开关状态，支持api和直接值，优先api
--- @param trigger_name string @指定某个选项，或者某个子菜单，若找不到或者不存在默认为根菜单
--- @param show_str string @状态栏中显示的名称
--- @param api_name string @获取状态的api名
--- @param field_value string @设置为默认值
function Expansion:show_status(trigger_name, show_str, api_name, field_value)
    -- 检查对象类型
    local entry = root_menu._msg_matcher:msg_match({ msg = { trigger_name } }, false)
    local trigger_type
    if entry and entry.type then
        trigger_type = entry.type
    end
    if trigger_type == "entry" then
        self.status_list[trigger_name] = {
            api_name = api_name,
            field_value = field_value,
            show_str = show_str or trigger_name
        }
    elseif trigger_type == "sub_menu" then
        self.menu_status_list[trigger_name] = self.menu_status_list[trigger_name] or {}
        table.insert(self.menu_status_list[trigger_name], {
            api_name = api_name,
            field_value = field_value,
            show_str = show_str or trigger_name
        })
    else
        table.insert(self.root_menu_status_list, {
            api_name = api_name,
            field_value = field_value,
            show_str = show_str or trigger_name
        })
    end
end

function Expansion:update_default_factory(default_factory)
    for name, factory in pairs(self.style_factory_list) do
        if name ~= "#默认风格" then
            for key, value in pairs(factory.menu_style) do
                if value.replace then
                    factory.menu_style[key] = default_factory.menu_style[key]
                end
            end
        end
    end
end

-- 是否使用美化拓展的代码
-- 拿着这个Expander去可劲造罢
Expander = newExpander(config)
if config["启用美化"] then
    Expander:add_style_factory_to_root_menu(root_menu)
end

------------- 开放的跨插件通信 ---------------

-- 设置 美化部分的管理
coromega:when_called_by_api_named("menu/setting"):start_new(function(data, set_result)
    -- data={type="",value=any, key="" }
    if data.type == "启用美化" then
        if type(data.value) == "boolean" then
            if data.value then
                Expander:add_style_factory_to_root_menu(root_menu)
            end
            config["启用美化"] = data.value
        end
    elseif data.type == "设置风格" and data.key == nil and type(data.value) == "string" then
        config["主菜单风格"] = tostring(data.value) or config["主菜单风格"]
        -- 更新全局风格工厂
        Expander:add_style_factory_to_root_menu(root_menu)
    elseif data.type == "添加风格" and type(data.value) == "table" then
        local style_factory = Expander:get_style_factory(data.key)
        -- 将普通字段类型和注册api类型分开处理组成风格工厂
        for key, value in pairs(data.value) do
            if style_factory.menu_style[key] then
                if type(value) == "table" and value.api_name and type(value.api_name) == "string" then
                    -- 注册api
                    style_factory.menu_style[key]:set_value_from_api({ api_name = value.api_name }):set_replace(false)
                else
                    -- 注册单值
                    style_factory.menu_style[key]:set_value_from_config(value):set_replace(false)
                end
            else
                -- 当作选项类api注册
                Expander:register_api_to_style_generator(data.key, value.option_name, value.api_name, key)
            end
        end
        if not data.key then
        Expander:update_default_factory(style_factory)
        end
    elseif data.type == "设置风格" and type(data.key) == "string" and type(data.value) == "string" then
        for _, cfg in ipairs(Expander._config["菜单组织结构和权限选项"]) do
            if cfg["类型"] == "子菜单" and cfg["名称"] == data.key then
                cfg["菜单风格"] = data.value
                break
            end
        end
        -- 更新全局风格工厂
        Expander:add_style_factory_to_root_menu(root_menu)
    elseif data.type == "设置状态" then
        -- key指定某个选项，或者某个子菜单，若找不到或者不存在默认为根菜单
        -- value里要给出状态显示名，获得值的途径(默认值，要调用的api二选一)
        Expander:show_status(data.key, data.value.display_name, data.value.api_name, data.value.default_value)
    end
    set_result(nil)
end)

--------------------------------------------------------------
coromega:new_event_source(game_menu, function(eventData)
    root_menu:add_entry(eventData)
end)

coromega:new_event_source(game_chat, function(eventData)
    coromega:start_new(function()
        handle_game_chat(eventData)
    end)
end)

coromega:new_event_source(player_change_poller, function(eventData)
    local player = eventData.player
    local action = eventData.action
    on_player_change(player, action)
end)

coromega:run()
