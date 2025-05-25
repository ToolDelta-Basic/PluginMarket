-- ORIG_VERSION_HASH: 25cd5a8efe7a5991992ecb83308b6eae
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
local default_code_header = [[
local omega = require("omega")
local json = require("json")
--- @type Coromega
local coromega = require("coromega").from(omega)
]]
local default_code_content = [[

print("config of %s:  ",json.encode(coromega.config))

-- 如果你需要调试请将下面一段解除注释，关于调试的方法请参考文档
-- local dbg = require('emmy_core')
-- dbg.tcpConnect('localhost', 9966)
-- print("waiting...")
-- for i=1,1000 do -- 调试器需要一些时间来建立连接并交换所有信息
--     -- 如果始终无法命中断点，你可以尝试将 1000 改的更大
--     print(".")
-- end
-- print("end")

coromega:when_called_by_terminal_menu({
    triggers = { "%s" },
    argument_hint = "[arg1] [arg2] ...",
    usage = "%s",
}):start_new(function(input)
    print("hello from %s!")
end)

coromega:when_called_by_game_menu({
    triggers = { "%s" },
    argument_hint = "[arg1] [arg2] ...",
    usage = "%s",
})
:start_new(function(chat)
    local caller_name = chat.name
    local caller = coromega:get_player_by_name(caller_name)
    local input = chat.msg
    print(input)
    caller:say("hello from %s!")
end)


coromega:run()
]]

coromega
	:when_called_by_terminal_menu({
		triggers = { "create" },
		argument_hint = "[plugin_name] [describe]",
		usage = "创建新插件",
	})
	:start_new(function(input)
		local plugin_name = input[1]
		local plugin_describe = input[2]

		while not plugin_name or plugin_name == "" do
			plugin_name = coromega:backend_input("请输入插件名: ")
			if not plugin_name or plugin_name == "" then
				print("插件名不可为空")
			end
		end
		plugin_name = plugin_name:gsub(".lua$", "")

		while not plugin_describe or plugin_describe == "" do
			plugin_describe = coromega:backend_input("请输入插件描述: ")
			if not plugin_describe or plugin_describe == "" then
				print("插件描述不可为空")
			end
		end

		local plugin_code_file = coromega:code_path_of("LuaLoader", plugin_name .. ".lua")
		local plugin_config_dir = coromega:config_path_of(plugin_name .. "[lua]")
		local plugin_config_file = coromega:path_join(plugin_config_dir, ("%s[LuaLoader]-1.json"):format(plugin_name))
		if coromega:path_exist(plugin_code_file) then
			print(("插件名和现有插件冲突, 冲突文件位于 %s"):format(plugin_code_file))
			return
		end
		if coromega:path_exist(plugin_config_dir) then
			print(("插件名和现有插件配置冲突, 冲突文件夹位于 %s"):format(plugin_config_dir))
			return
		end
		print(
			("开始创建插件 %s: \n\t代码文件位于: %s \n\t配置文件夹位于: %s"):format(
				plugin_name,
				plugin_code_file,
				plugin_config_dir
			)
		)
		coromega:save_data(plugin_config_file, {
			["名称"] = plugin_name .. ".lua",
			["配置"] = {
				["Version"] = "0.0.1",
			},
			["描述"] = plugin_describe,
			["是否禁用"] = false,
			["来源"] = "LuaLoader",
		})

		local code_file_pointer, err = io.open(plugin_code_file, "w")
		if not code_file_pointer then
			print(("无法创建Lua文件: %s 错误: %s"):format(plugin_code_file, err))
			return
		end
		code_file_pointer:write(default_code_header)
		code_file_pointer:write(
			default_code_content:format(
				plugin_name,
				plugin_name,
				plugin_describe,
				plugin_name,
				plugin_name,
				plugin_describe,
				plugin_name
			)
		)
		code_file_pointer:close()
		print(("插件 %s 创建成功, 输入 reload 使之生效"):format(plugin_name))
	end)

coromega:run()
