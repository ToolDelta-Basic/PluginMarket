-- ORIG_VERSION_HASH: 76f136215eb9f61e3617caeabdfd076b
-- ORIG_VERSION_HASH 可以帮助 neOmega 判断此 lua 文件中的代码是否被用户修改过
-- 如果此 lua 文件中的代码被用户修改过，那么 neOmega 将不会再修改它以避免错误的覆盖用户修改
-- 如果此 lua 文件中的代码没有被用户修改过，那么 neOmega 将在此插件有更新时自动应用更新
-- 当前状态: 代码未被用户修改，neOmega 将自动应用更新
-- ORIG_VERSION_HASH: END
local all_entries = {}
local entry_by_trigger = {}

local terminal_grey = "\27[38;5;8m"
local terminal_clear = "\27[0m"
local terminal_blue = "\27[38;5;12m"

local reload_entry = {
    entry = {
        triggers = { 'reload' },
        argument_hint = '',
        usage = '重新启动 Omega Frame 但不断开与 MC 的连接，插件也将一并全部重新启动',
    },
    on_trig_callback = function()
        os.exit(3)
    end
}

local reboot_entry = {
    entry = {
        triggers = { 'reboot', 'stop' },
        argument_hint = '',
        usage = '重新启动 Omega Frame 同时断开 MC 的连接，机器人将会重连',
    },
    on_trig_callback = function()
        os.exit(2)
    end
}


all_entries[1] = reload_entry
all_entries[2] = reboot_entry
entry_by_trigger[reload_entry.entry.triggers[1]] = reload_entry
entry_by_trigger[reboot_entry.entry.triggers[1]] = reboot_entry
entry_by_trigger[reboot_entry.entry.triggers[2]] = reboot_entry

local function add_menu_entry(entry)
    -- entry = {entry={triggers={'key1','key2','key3',...},argument_hint='',usage=''},on_trig_callback=function(args...)}
    -- print(("add entry: [%s] %s %s\n"):format(
    --     table.concat(entry.entry.triggers, ", "),
    --     entry.entry.argument_hint,
    --     entry.entry.usage)
    -- )
    all_entries[#all_entries + 1] = entry
    for _, trigger in pairs(entry.entry.triggers) do
        entry_by_trigger[trigger] = entry
    end
end

local function handle_terminal_menu_call(input)
    -- remove trailing newline
    input = input:gsub("\n$", "")
    -- print(("handle terminal menu call: %s\n"):format(input))
    -- split input by space
    local args = {}
    for arg in string.gmatch(input, "%S+") do
        args[#args + 1] = arg
    end
    -- get first arg as trigger
    local trigger = args[1]
    if trigger == nil then
        print("无效的输入,你可以试试输入" .. terminal_blue .. " ? " .. terminal_clear .. "打开菜单\n")
        return
    end
    -- get entry by trigger
    local entry = nil
    entry = entry_by_trigger[trigger]
    local condense_arg_1 = ""
    if entry == nil then
        -- try to find trigger with prefix
        for trigger_, entry_ in pairs(entry_by_trigger) do
            if trigger:sub(1, #trigger_) == trigger_ then
                entry = entry_
                condense_arg_1 = trigger:sub(#trigger_ + 1)
                break
            end
        end
    end
    if entry == nil then
        print(("无法找到输入(%s)对应的操作,你可以试试输入 help 打开菜单\n"):format(trigger))
        return
    end
    -- call callback with rest of args
    if condense_arg_1 ~= "" then
        args[1] = condense_arg_1
        entry.on_trig_callback(unpack(args))
    else
        entry.on_trig_callback(unpack(args, 2))
    end
end

local function popup_menu()
    print("==== NEOMEGA MENU ====")
    for _, entry in pairs(all_entries) do
        local line = terminal_blue .. entry.entry.triggers[1] .. terminal_clear
        if #entry.entry.triggers > 1 then
            line = line .. terminal_grey .. " (" .. table.concat(entry.entry.triggers, ", ", 2) .. ")" .. terminal_clear
        end
        if entry.entry.argument_hint ~= "" then
            line = line .. " " .. entry.entry.argument_hint
        end
        line = line .. ": " .. entry.entry.usage
        print(("%s"):format(line))
    end
    print("======================")
end

while poller:has_next() do
    local event_type, event = poller:get_next()
    if event_type == event_type_add_menu_entry then
        add_menu_entry(event)
    elseif event_type == event_type_terminal_call then
        handle_terminal_menu_call(event)
    elseif event_type == event_type_pop_backend_menu then
        popup_menu()
    end
end
