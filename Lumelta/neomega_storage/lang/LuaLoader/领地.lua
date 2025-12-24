-- ORIG_VERSION_HASH: 07373904d5fddbb00fd721e487605e9f
-- ORIG_VERSION_HASH 可以帮助 neOmega 判断此 lua 文件中的代码是否被用户修改过
-- 如果此 lua 文件中的代码被用户修改过，那么 neOmega 将不会再修改它以避免错误的覆盖用户修改
-- 如果此 lua 文件中的代码没有被用户修改过，那么 neOmega 将在此插件有更新时自动应用更新
-- 当前状态: 代码未被用户修改，neOmega 将自动应用更新
-- ORIG_VERSION_HASH: END
local omega = require("omega")
local json = require("json")
--- @type Coromega
local coromega = require("coromega").from(omega)
local config = coromega.config -- 获取配置

-- 存储领地命令方块的坐标
local territory_command_block_x = config["领地命令方块存放位置"]["x"] or 10000
local territory_command_block_y = config["领地命令方块存放位置"]["y"] or 250
local territory_command_block_z = config["领地命令方块存放位置"]["z"] or 10000
local maxx = config["最大长度"] or 50 -- 创建玩家领地的最大长度
local maxz = config["最大宽度"] or 50 -- 创建玩家领地的最大宽度
local one_money = config["每格所需货币数"] or 3 -- 每一格所需的货币
local remove_one_money = config["删除领地后每格返还货币数"] or 1 -- 删除领地后每一格所返还的货币
local money_name = config["货币显示名称"] or "金币" -- 货币的显示名称
local money_scoreboard = config["货币积分板名称"] or "金币" -- 货币的积分板名称
local data_scoreboard = config["数据积分板名称"] or "数据" -- 存储数据的积分板名称
local tip_scoreboard = config["领地主人提示积分板名称"] or "领地主人提示" -- 存储是否显示领地主人提示的积分板名称
local creating_scoreboard = config["正在创建领地时的积分板"] or "正在创建领地"
local clear_scoreboard = config["清除实体积分板名称"] or "清除" -- 存储清除实体积分板名称
local show_create_territory_tip = config["创建领地时是否实时显示领地的大小等"] or false -- 创建领地的时候是否需要实时显示领地的大小面积等等 出现卡顿可以关闭
local territory_data_name = config["领地数量名称"] or "领地数量" -- 存储领地数量的名称
local fake_territory_data_name = config["假领地数量名称"] or "假领地数量"-- 存储假领地数量的名称
local db_name = config["数据库名称"] or "领地数据" -- 数据库的名称
local use_new = config["是否使用新算法生成领地命令方块坐标"] or false -- 是否使用新算法生成坐标 新算法支持缓存x,y
local db = omega.storage.get_kv_db(db_name) -- 获取数据库
-- 领地外圈五格所有会被清除的实体
local all_ban_entity = {
    "ender_pearl",  -- 末影珍珠
    "ender_crystal", -- 末地水晶
    "fireball",     -- 火球
    "tnt",          -- TNT
    "boat",         -- 船
    "tnt_minecart", -- TNT矿车
    "chest_boat",   -- 运输船
    "minecart",     -- 矿车
    "area_effect_cloud", -- 药水云
    "arrow"         -- 箭
}

-- 各种显示文本
local messages = {
    initialize_territorial_system = {
        no_permission = "§c〡 你没有权限",
        wait = "§e# §7领地已开始初始化 请稍等..."
    },
    my_territory = {
        no_territory = "§c〡 你还没创建领地",
        info = "residence information §4︳§f 信息介绍\n§7-------------------------§f\n▎§4┊ ︳§f┤ §7长宽   §f︳  l: ［长］ w: ［宽］\n▎§4┊ ︳§f┤§7 面积   §f︳  s: ［面积］\n▎§4┊ ︳§f┤§7 价值   §f︳  $: ［价值］ ［货币名称］ \n▎§4┊ ︳§f┤§7中心坐标: ［中心X］ ［中心Z］ \n▎§4┊ ︳§f┤§7提示文本: ［提示文本］\n§7-------------------------",
    },
    change_territory_tip = {
        no_territory = "§c〡 你还没创建领地",
        please = "§e# §7请输入领地提示文本:",
        wait = "§a〡 §7正在修改中 请稍等...",
        success = "§a〡 §7已修改把领地提示文本成功修改成:［提示文本］"
    },
    create_territory = {
        size_tip = "residence information §4︳§f 信息介绍\n§7-------------------------§f\n▎§4┊ ︳§f┤ §7长宽   §f︳  长 : ［长］  宽 : ［宽］  \n▎§4┊ ︳§f┤§7 面积   §f︳  s:［面积］\n▎§4┊ ︳§f┤§7 价值   §f︳  $: ［价值］ ［货币名称］ \n§7-------------------------",
        already_created = "§c〡 §7你已经创建过领地了",
        record_start = "§a〡 §g已记录起点坐标为：［坐标X］ ［坐标Y］ ［坐标Z］",
        please = "§a〡 §e请移动到下一点 并输入任意字符（输入取消 可以取消创建领地）",
        cancel_creation = "§c〡 §7已退出创建领地",
        record_end = "§a〡 §g已记录终点坐标为：［坐标X］ ［坐标Y］ ［坐标Z］",
        dimension_mismatch = "§c〡 §7起点终点维度不一致 已退出创建领地",
        invalid_size = "§c〡 §7长宽不能为零 已退出创建领地",
        details = "     < 领地§4◈§f信息 >\n[ Territory Information ]\n§7------------------------\n§f>> §7长:  §f ［长］\n>> §7宽:  §f ［宽］ \n>> §7面积:  §f ［面积］ \n§7------------------------\n§f         ▷§a tip §f◁\n§7     请认真核对信息\n------------------------§f\n>> §7总计:  §f  ［价值］  ［货币名称］ \n>> §7左下坐标:  §fx: ［左下角X］ z: ［左下角Z］ \n>> §7中心坐标:  §fx: ［中心X］ z: ［中心Z］\n\n\n",
        input_tip = "§a〡 §7请输入领地自定义显示文本:",
        checking_conditions = "§a〡 §7正在检查领地创建条件中...",
        size_too_large = "§c〡 §7领地长度或宽度过大 最大长度: ［最大长度］格 最大宽度: ［最大宽度］格",
        insufficient_funds = "§c〡 §7对不起 所需要的 ［货币名称］ 不够 你身上总共 ［玩家货币］ ［货币名称］",
        overlap = "§c〡 §7你选中的领地范围有其他人的领地",
        creation_failed = "§c〡 §7创建领地失败",
        conditions_passed = "§a〡 §7领地创建条件检查通过",
        registering_territory = "§a正在注册领地中...",
        creation_success = "§a§l创建领地成功",
        funds_deducted = "§g〡 §7已扣除你 ［扣除金额］ ［货币名称］ 还剩 ［剩余金额］ ［货币名称］"
    },
    add_whitelist = {
        no_territory = "§c■ §7> §f你还没创建领地",
        cannot_add_self = "§c■ §7> §f不能添加自己为信任玩家",
        invalid_input = "§c■ §7> §f无效输入 已退出",
        cancel = "§a■ §7> §f已退出",
        success = "§a■ §7> §f添加成功！",
        already_exists = "§c■ §7> §f添加失败 该玩家已存在",
        select_player = "§7> 以下是所有玩家:",
        please = "§e■ §7> §7请输入对应的编号选择玩家（输入取消可退出）:",
        player_list = "[［索引］] ［名字］" -- 用于显示玩家列表的消息模板
    },
    remove_whitelist = {
        no_territory = "§c■ §7> §f你还没创建领地",
        cannot_remove_self = "§c■ §7> §f不能把自己移出信任玩家",
        select_player = "§7> 以下是所有玩家:",
        please = "§c■ §7> §f请选择一个玩家（输入编号选择，输入取消退出）:",
        invalid_input = "§c■ §7> §f无效输入 已退出",
        cancel = "§a■ §7> §f已退出",
        remove_success = "§a■ §7> §f删除成功！",
        player_not_in_whitelist = "§c■ §7> §f删除失败 该玩家不在信任玩家中",
        player_list = "[［索引］] ［名字］" -- 消息格式
    },
    list_whitelist = {
        no_territory = "§c■ §7> §f你还没创建领地", -- 消息：没有创建领地
        no_whitelist = "§c■ §7> §f你没有添加任何的信任玩家", -- 消息：没有添加信任玩家
        whitelist_header = "§7> §f你添加的信任玩家有：" -- 消息：信任玩家列表标题
    },
    remove_territory = {
        no_territory = "§c■ §7> §f你还没有创建领地", -- 当玩家没有领地时显示的消息
        confirm_deletion = "§e■ §7> §f你确定要删除领地吗？（是/否）", -- 询问玩家是否确认删除领地的消息
        deleting = "§a■ §7> §7正在删除领地中，请稍等...", -- 删除领地过程中的提示消息
        cancel_deletion = "§a■ §7> §f已退出删除领地", -- 玩家取消删除领地时显示的消息
        success = "§g■ §7> §f领地删除成功，已返还你 ［金额］ ［货币单位］" -- 领地删除成功后的消息模板
    },
    return_territory = {
        no_territory = "§c〡 §7你还没创建领地",
        returned = "§a〡 §7已返回领地"
    },
    create_fake_territory = {
        size_tip = "residence information §4︳§f 信息介绍\n§7-------------------------§f\n▎§4┊ ︳§f┤§7坐标 ［坐标X］ ［坐标Z］ \n▎§4┊ ︳§f┤ §7长宽   §f︳  l:［长］ w:［宽］\n▎§4┊ ︳§f┤§7 面积   §f︳  s:［面积］\n§7-------------------------",
        no_permission = "§c〡 §7你没有权限",
        recorded_start_pos = "§a〡 §7已记录起点坐标为：［X坐标］ ［Y坐标］ ［Z坐标］",
        move_to_next_point = "§a〡 §g请移动到下一点 并输入任意内容（输入取消 可以取消创建假领地）",
        exit_creation = "§a〡 §7已退出创建假领地",
        recorded_end_pos = "§a〡 §e已记录终点坐标为：［X坐标］ ［Y坐标］ ［Z坐标］",
        dimension_mismatch = "§c〡 §7起点终点维度不一致 已退出创建假领地",
        invalid_dimensions = "§c〡 §7长宽不能为零 已退出创建假领地",
        info_message = "residence information §4︳§f 信息介绍\n§7-------------------------§f\n▎§4┊ ︳§f┤ §7长宽   §f︳  长 : ［长］ 宽 :［宽］ \n▎§4┊ ︳§f┤§7 面积   §f︳  s:［面积］\n▎§4┊ ︳§f┤§7中心坐标: ［中心X］ ［中心Z］\n§7-------------------------",
        input_display_name = "§g# §7请输入这块假领地的名字:",
        checking_conditions = "§7正在检查假领地创建条件中...",
        conditions_passed = "§a〡 §7假领地创建条件检查通过",
        registering = "§7正在注册假领地中...",
        creation_success = "§a创建假领地成功",
        overlap_error = "§c〡 §7你选中的假领地范围有其他人的领地",
        creation_failed = "§c〡 §7创建假领地失败"
    },
    remove_fake_territory = {
        no_permission = "§c你没有权限",
        no_fake_territory = "§c〡 §7还没有任何的假领地",
        all_fake_territories = "§g# §7这是所有的假领地:",
        display = "[［索引］] ［名字］ 坐标: ［X坐标］ ［Y坐标］ ［Z坐标］ 长［长］格 宽［宽］格 由［创建者］创建",
        please = "§g# §7请输入需要删除的假领地编号（输入取消可退出）:",
        invalid_input = "§c〡 §7无效输入 已退出",
        delete_success = "§a〡 §7已成功删除该假领地",
        cancel_deletion = "§c〡 §7已退出删除假领地"
    },
    list_fake_territory = {
        no_permission = "§c你没有权限",
        no_fake_territory = "§c〡 §7还没有任何的假领地",
        list_title = "§a〡 §7这是所有的假领地:",
        display = "[［索引］] ［名字］ 坐标: ［X坐标］ ［Y坐标］ ［Z坐标］ 长［长］格 宽［宽］格 由［创建者］创建"
    },
    list_territory = {
        no_permission = "§c你没有权限",
        no_territory = "§c〡 §7还没有任何的玩家领地",
        list_title = "§a〡 §7这是所有的玩家领地:",
        display = "[［索引］] ［提示］ 坐标: ［X坐标］ ［Y坐标］ ［Z坐标］ 长［长］格 宽［宽］格 由［创建者］创建"
    },
    remove_player_territory = {
        no_permission = "§c你没有权限",
        no_territories = "§c〡 §7还没有任何的领地",
        list_header = "§a〡 §7这是所有的领地:",
        display = "[［索引］] ［主人］ 坐标: ［X坐标］ ［Y坐标］ ［Z坐标］ 面积［面积］格",
        please = "§g# §7请输入需要删除的领地编号（输入取消可退出）:",
        invalid_input = "§c〡 §7无效输入 已退出",
        confirm_delete = "§g# §7你确定要删除他的领地吗？（是/否）",
        deleting = "§7正在删除领地中 请稍等...",
        delete_success = "§a〡 §7领地删除成功",
        cancel = "§c〡 §7已退出删除领地"
    },
    territory_owner_hint = {
        enabled = "§a〡 §7已开启领地主人提示",
        disabled = "§c〡 §7已关闭领地主人提示"
    },
    reset_territories = {
        no_permission = "§c你没有权限",
        no_territories = "§c还没有任何的领地",
        confirm_delete = "§c# §7你确定要删除所有领地吗？（是/否）",
        confirm_delete_again = "§c§l# §7你真的要删除所有领地吗？（是/否）",
        confirm_no_mistake = "§g# §c你真的确定自己没有手滑吗？（是/否）",
        final_confirm = "§e§l# §c最后一遍问你 你确定要删除所有领地吗？此操作不可逆（是/否）",
        deleting_territories = "§7正在删除所有玩家领地中 请稍等...",
        exited_deletion = "§a〡 §7已退出删除所有玩家领地",
        deleting_specific_territory = "[［索引］] 正在删除［主人］的领地",
        all_territories_deleted = "§a〡 §7所有玩家领地已删除"
    },
    reset_fake_territories = {
        no_permission = "§c你没有权限",
        no_fake_territories = "§c还没有任何的假领地",
        confirm_start = "§c# §7你确定要删除所有假领地吗？（是/否）",
        confirm_really = "§c§l# §7你真的要删除所有假领地吗？（是/否）",
        confirm_sure = "§g# §c你真的确定自己没有手滑吗？（是/否）",
        confirm_final = "§e§l# §c最后一遍问你 你确定要删除所有假领地吗？此操作不可逆（是/否）",
        deleting_progress = "§7正在删除所有假领地中 请稍等...",
        exit_deletion = "§a〡 §7已退出删除所有假领地",
        deleting_single = "§7正在删除第［索引］个假领地",
        all_deleted = "§a〡 §7所有假领地已删除"
    }
}

-- 菜单项的配置
local menu = {
    initialize_territorial_system = {
        triggers = { "初始化领地" },
        argument_hint = "[无]",
        usage = "重新初始化领地以防止第1次初始化失败"
    },
    my_territory = {
        triggers = { "领地信息" },
        argument_hint = "[无]",
        usage = "显示你的§e领地§f信息"
    },
    change_territory_tip = {
        triggers = { "修改领地提示文本" },
        argument_hint = "[提示文本]",
        usage = "修改你的领地提示文本"
    },
    create_territory = {
        triggers = { "创建领地" },
        argument_hint = "[无]",
        usage = "圈一块自定义大小的长方形领地"
    },
    add_whitelist = {
        triggers = { "添加领地信任玩家" },
        argument_hint = "[玩家名字]",
        usage = "添加领地信任玩家让他可以进入你的领地"
    },
    remove_whitelist = {
        triggers = { "移出领地信任玩家" },
        argument_hint = "[玩家名字]",
        usage = "删除领地信任玩家让他可以不进入你的领地"
    },
    list_whitelist = {
        triggers = { "列出领地信任玩家" },
        argument_hint = "[无]",
        usage = "列出所有的领地信任玩家"
    },
    remove_territory = {
        triggers = { "废除领地" },
        argument_hint = "[无]",
        usage = "删除你的领地"
    },
    return_territory = {
        triggers = { "领地返回" },
        argument_hint = "[无]",
        usage = "返回你的领地"
    },
    create_fake_territory = {
        triggers = { "创建假领地" },
        argument_hint = "[无]",
        usage = "圈一块自定义大小的长方形假领地 使其他玩家不可在此地方创建领地（需要OP权限）"
    },
    remove_fake_territory = {
        triggers = { "废除假领地" },
        argument_hint = "[无]",
        usage = "废除一块假领地（需要OP权限）"
    },
    list_fake_territory = {
        triggers = { "列出假领地" },
        argument_hint = "[无]",
        usage = "列出所有的假领地（需要OP权限）"
    },
    list_territory = {
        triggers = { "列出玩家领地", "列出领地" },
        argument_hint = "[无]",
        usage = "列出所有的玩家领地（需要OP权限）"
    },
    remove_player_territory = {
        triggers = { "废除玩家领地" },
        argument_hint = "[无]",
        usage = "删除任意玩家的领地（需要OP权限）"
    },
    enable_territory_owner_hint = {
        triggers = { "开启领地主人提示" },
        argument_hint = "[无]",
        usage = "开启显示对应领地的主人提示"
    },
    disable_territory_owner_hint = {
        triggers = { "关闭领地主人提示" },
        argument_hint = "[无]",
        usage = "关闭显示对应领地的主人提示"
    },
    reset_territories = {
        triggers = { "重置领地" },
        argument_hint = "[无]",
        usage = "删除所有玩家的领地（需要OP权限）"
    },
    reset_fake_territories = {
        triggers = { "重置假领地" },
        argument_hint = "[无]",
        usage = "删除所有假领地（需要OP权限）"
    }
}

-- 如果你需要调试请将下面一段解除注释，关于调试的方法请参考文档
-- local dbg = require('emmy_core')
-- dbg.tcpConnect('localhost', 9966)
-- print("waiting...")
-- for i=1,1000 do -- 调试器需要一些时间来建立连接并交换所有信息
--     -- 如果始终无法命中断点，你可以尝试将 1000 改的更大
--     print(".")
-- end
-- print("end")

-- 一些乱七八糟的函数

-- 把scoreboard命令输出的结果简化成分数
local function output_to_score(output)
    local score = tonumber(ud2lua(output:user_data().OutputMessages)[1]["Parameters"][1])
    return score or 0
end

-- 生成二维平面坐标（旧算法，速度慢，分布不均匀）
function old_generate_coordinates(id)
    -- 计算行数（即Z坐标），行数是大于等于log2(id)的最小整数
    local z = 0
    local count = 1
    while count < id do
        z = z + 1
        count = count + 2^z
    end
    
    -- 计算X坐标
    local x
    local startId = count - 2^z + 1
    if z % 2 == 0 then
        -- 偶数行从右向左填充
        x = 2^z - (id - startId)
    else
        -- 奇数行从左向右填充
        x = id - startId
    end
    
    -- 返回X和Z坐标
    return {x = x, z = z}
end

-- 新算法可以完整覆盖
function generate_coordinates_by_x_z(x, z)
    if x > z then
        z = z + 1
    elseif x <= z and x > 1 then
        x = x - 1
    elseif x == 1 then
        x, z = z + 1, 1
    end
    return {x=x,z=z}
end

function generate_coordinates_by_id(n)
    local x, z = 2,1
    if n == 1 then
        x,z = 1,1
    elseif n ~= 2 then
        for i = 1, n - 2 do
            local x_z = generate_coordinates_by_x_z(x, z)
            x=x_z.x
            z=x_z.z
        end
    end
    return {x=x,z=z}
end

local generate_coordinates=old_generate_coordinates
if use_new then
    generate_coordinates=generate_coordinates_by_id
end

-- 根据两点坐标获取左下角坐标
function getBottomLeftCorner(corner1, corner2)
    -- 确定左下角的坐标
    local bottomLeftX = math.min(corner1.x, corner2.x)
    local bottomLeftZ = math.min(corner1.z, corner2.z)

    return {x = bottomLeftX, z = bottomLeftZ}
end

-- 计算长方形的长和宽
function calculateDimensions(point1, point2)
    -- 确定长和宽
    local length = math.abs(point2.x - point1.x)
    local width = math.abs(point2.z - point1.z)
    
    -- 返回长和宽
    return {length = length, width = width}
end

-- 计算长方形的表面积
function calculateSurfaceArea(point1, point2)
    -- 首先计算长和宽
    local dimensions = calculateDimensions(point1, point2)
    
    -- 计算表面积
    local surfaceArea = dimensions.length * dimensions.width
    
    -- 返回表面积
    return surfaceArea
end

-- 获取排序的角
function get_sorted_corners(rect)
    local start_x, start_z = rect.start.x, rect.start.z
    local finish_x, finish_z = rect.finish.x, rect.finish.z
    return {
        {x = math.min(start_x, finish_x), z = math.min(start_z, finish_z)},
        {x = math.max(start_x, finish_x), z = math.max(start_z, finish_z)}
    }
end

-- 检查两个领地是否重叠
function check_overlap(rect_a, rect_b)
    local a_sorted = get_sorted_corners(rect_a)
    local a_left, a_right = a_sorted[1], a_sorted[2]
    local b_sorted = get_sorted_corners(rect_b)
    local b_left, b_right = b_sorted[1], b_sorted[2]
    
    -- 检查矩形在x轴和z轴上是否重叠
    return not (a_right.x < b_left.x or a_left.x > b_right.x or
                a_right.z < b_left.z or a_left.z > b_right.z)
end

-- 寻找重叠的领地
function find_overlapping_planes(base_plane, other_planes)
    local overlapping_planes = {}
    for i, plane in ipairs(other_planes) do
        for name, rect in pairs(plane) do
            if check_overlap(base_plane, rect) then
                table.insert(overlapping_planes, name)
            end
        end
    end
    return overlapping_planes
end

-- 通过两点坐标获取中间点
function calculateCenter(point1, point2)
    -- 计算x坐标的平均值（整数）
    local centerX = math.floor((point1.x + point2.x) / 2)
    -- 计算z坐标的平均值（整数）
    local centerZ = math.floor((point1.z + point2.z) / 2)
    
    -- 返回中心坐标
    return {x = centerX, z = centerZ}
end

-- 初始化领地函数
function initialize_territorial_system()
    coromega:print("10秒后开始进行领地初始化...")
    omega.players.say_to("@a","10秒后进行领地初始化...")
    coromega:sleep(10)
    -- 避免缺少积分板
    omega.cmds.send_wo_cmd(("scoreboard objectives add %s dummy"):format(data_scoreboard)) -- 存放领地数据的积分板
    omega.cmds.send_wo_cmd(("scoreboard objectives add %s dummy"):format(tip_scoreboard)) -- 存放显示领地主人提示的积分板
    omega.cmds.send_wo_cmd(("scoreboard objectives add %s dummy"):format(clear_scoreboard)) -- 存放清除实体的积分板
    omega.cmds.send_wo_cmd(("scoreboard objectives add %s dummy"):format(creating_scoreboard)) -- 存放正在创建领地时的积分板
    coromega:print(("选择坐标: %d %d %d"):format(territory_command_block_x,territory_command_block_y,territory_command_block_z))
    local index=0
    for _, ban_entity in pairs(all_ban_entity) do
        omega.players.say_to("@a",("[领地初始化] §o§l§b〡§f〡  §r§7领地正在初始化中...(%d/%d)"):format(index+1,#all_ban_entity+2))
        coromega:print("禁用实体: "..ban_entity)
        coromega:print(index)
        local command_block_type="chain_command_block"
        if index == 0 then
            command_block_type="repeating_command_block"
        end
        local err = coromega:place_command_block(
            { x = territory_command_block_x, y = territory_command_block_y+index, z = territory_command_block_z},
            command_block_type,
            1,
            {
                need_red_stone = false,
                conditional = false,
                command = ('kill @e[scores={%s=1},type=%s]'):format(clear_scoreboard,ban_entity),
                name = ("_ban_%s"):format(ban_entity),
                tick_delay = 0,
                track_output = false,
                execute_on_first_tick = true
            }
        )
        index=index+1
        coromega:sleep(1) -- 好累啊 休息一会
    end
    
    omega.players.say_to("@a",("[领地初始化] §o§l§b〡§f〡 §r§7领地正在初始化中...(%d/%d)"):format(index+1,#all_ban_entity+2))
    local err = coromega:place_command_block(
        { x = territory_command_block_x, y = territory_command_block_y+index, z = territory_command_block_z},
        "chain_command_block",
        1,
        {
            need_red_stone = false,
            conditional = false,
            command = ('gamemode 2 @a[m=0,scores={%s=1}]'):format(clear_scoreboard),
            name = "冒险模式",
            tick_delay = 0,
            track_output = false,
            execute_on_first_tick = true
        }
    )
    coromega:sleep(1) -- 好累啊 休息一会
    omega.players.say_to("@a",("[领地初始化] §o§l§b〡§f〡 §r§7领地正在初始化中...(%d/%d)"):format(index+2,#all_ban_entity+2))
    local err = coromega:place_command_block(
        { x = territory_command_block_x, y = territory_command_block_y+index+1, z = territory_command_block_z},
        "chain_command_block",
        1,
        {
            need_red_stone = false,
            conditional = false,
            command = ('scoreboard players reset @e[scores={%s=1}] %s'):format(clear_scoreboard,clear_scoreboard),
            name = "重置分数",
            tick_delay = 0,
            track_output = false,
            execute_on_first_tick = true
        }
    )
    coromega:sleep(1) -- 好累啊 休息一会
    omega.players.say_to("@a",'[领地初始化] 添加常加载: "_领地_常加载"')
    omega.cmds.send_wo_cmd(('tickingarea add %d 0 %d %d 0 %d "_领地_常加载"'):format(territory_command_block_x,territory_command_block_z,territory_command_block_x+100,territory_command_block_z+100)) -- 设置常加载           
    omega.cmds.send_wo_cmd(('scoreboard players set %s %s 1'):format("_领地_初始化",data_scoreboard)) -- 设置 1 避免下次继续初始化
    omega.players.say_to("@a",('[领地初始化] 领地初始化完成 如果需要重新初始化 请修改积分板 "%s" 中的 "%s" 变成 0\n§l§e如需更多公益插件请进入官方交流区870300327 '):format(data_scoreboard,"_领地_初始化"))
end

-- 第1次使用时初始化
coromega:start_new(function()
    omega.cmds.send_ws_cmd_with_resp(("scoreboard players test %s %s * *"):format("_领地_初始化", data_scoreboard), function(output)
        local initialization = output_to_score(output)
        if initialization == 0 then
            initialize_territorial_system()
        end
    end)
end)

-- 菜单项：创建领地
coromega:when_called_by_game_menu(menu.create_territory):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    local uuid = player:uuid_string()
    if db:get(uuid) ~= "" then
        player:say(messages.create_territory.already_created)
        return
    end

    local now_pos = player:get_pos().position
    local pos={x=math.floor(now_pos.x),y=math.floor(now_pos.y),z=math.floor(now_pos.z)}
    local dim = {"overworld", "nether", "the_end"}
    local dimension = dim[(player:get_pos().dimension+1)] or ("dm"..player:get_pos().dimension)
    player:say(messages.create_territory.record_start
        :gsub("［坐标X］", tostring(math.floor(pos.x)))
        :gsub("［坐标Y］", tostring(math.floor(pos.y)))
        :gsub("［坐标Z］", tostring(math.floor(pos.z)))
    )
    omega.cmds.send_wo_cmd(("scoreboard players set %s %s 1"):format(chat.name,creating_scoreboard))
    if show_create_territory_tip then
        coromega:start_new(function()
            local exit = false
            while true do
                if exit then
                    break
                end
                coromega:sleep(0.3)
                omega.cmds.send_ws_cmd_with_resp(("scoreboard players test %s %s * *"):format(chat.name, creating_scoreboard), function(output)
                    if output_to_score(output) == 1 then
                        omega.cmds.send_ws_cmd_with_resp(("querytarget @a[name=%s]"):format(chat.name), function(output)
                            local creating_pos=json.decode(ud2lua(output:user_data().OutputMessages)[1]["Parameters"][1])[1]["position"]
                            local LW=calculateDimensions({x=math.floor(pos.x),z=math.floor(pos.z)}, {x=math.floor(creating_pos.x),z=math.floor(creating_pos.z)})
                            local actionbar = {
                                rawtext = {
                                    {
                                        text = messages.create_territory.size_tip
                                            :gsub("［坐标X］", tostring(math.floor(creating_pos.x)))
                                            :gsub("［坐标Y］", tostring(math.floor(creating_pos.y)))
                                            :gsub("［坐标Z］", tostring(math.floor(creating_pos.z)))
                                            :gsub("［长］", tostring(LW.length))
                                            :gsub("［宽］", tostring(LW.width))
                                            :gsub("［面积］", tostring(LW.length*LW.width))
                                            :gsub("［价值］", tostring(LW.width*LW.length*one_money))
                                            :gsub("［货币名称］", tostring(money_name))
                                    }
                                }
                            }
                            omega.cmds.send_wo_cmd(("titleraw @a[name=%s] actionbar %s"):format(chat.name,json.encode(actionbar)))
                        end)
                    else
                        exit = true
                        return
                    end
                end)
            end
        end)
    end
    local exit = player:ask(messages.create_territory.please)
    omega.cmds.send_wo_cmd(("scoreboard players set %s %s 0"):format(chat.name,creating_scoreboard))
    if exit == "取消" then
        player:say(messages.create_territory.cancel_creation)
        return
    end
    local now_end_pos=player:get_pos().position
    local end_pos={x=math.floor(now_end_pos.x),y=math.floor(now_end_pos.y),z=math.floor(now_end_pos.z)}
    local end_dimension = dim[(player:get_pos().dimension+1)] or ("dm"..player:get_pos().dimension)
    if dimension ~= end_dimension then
        player:say(messages.create_territory.dimension_mismatch)
        return
    end
    player:say(messages.create_territory.record_end
        :gsub("［坐标X］", tostring(math.floor(end_pos.x)))
        :gsub("［坐标Y］", tostring(math.floor(end_pos.y)))
        :gsub("［坐标Z］", tostring(math.floor(end_pos.z)))
    )
    

    local start_point, finish_point = {x=pos.x, z=pos.z}, {x=end_pos.x, z=end_pos.z}
    local LW = calculateDimensions(start_point, finish_point)
    if LW.length == 0 or LW.width == 0 then
        player:say(messages.create_territory.invalid_size)
        return
    end

    local area = calculateSurfaceArea(start_point, finish_point)
    local bottom_left_corner = getBottomLeftCorner(start_point, finish_point)
    local center = calculateCenter(start_point, finish_point)
    local need_money = area * one_money    
    player:say(messages.create_territory.details
        :gsub("［长］", tostring(LW.length))
        :gsub("［宽］", tostring(LW.width))
        :gsub("［面积］", tostring(area))
        :gsub("［价值］", tostring(need_money))
        :gsub("［货币名称］", tostring(money_name))
        :gsub("［左下角X］", tostring(bottom_left_corner.x))
        :gsub("［左下角Z］", tostring(bottom_left_corner.z))
        :gsub("［中心X］", tostring(center.x))
        :gsub("［中心Z］", tostring(center.z))
    )
    player:say(messages.create_territory.checking_conditions)
    local player_money = tonumber(coromega:send_ws_cmd(("scoreboard players test %s %s * *"):format(chat.name, money_scoreboard),true)["OutputMessages"][1]["Parameters"][1]) or 0
    if LW.length > maxx or LW.width > maxz then
        player:say(messages.create_territory.size_too_large
            :gsub("［最大长度］", tostring(maxx))
            :gsub("［最大宽度］", tostring(maxz))
        )
        player:say(messages.create_territory.creation_failed)
        return
    end
    if player_money < need_money then
        player:say(messages.create_territory.insufficient_funds
            :gsub("［货币名称］", tostring(money_name))
            :gsub("［玩家货币］", tostring(player_money))
        )
        player:say(messages.create_territory.creation_failed)
        return
    end

    local base_plane = {
        start = {x = pos.x, z = pos.z},
        finish = {x = end_pos.x, z = end_pos.z},
        area = area,
        uuid = uuid,
        name = chat.name,
        whitelist = {},
        bottom_left_corner = {x = bottom_left_corner.x, y = math.floor(pos.y), z = bottom_left_corner.z},
        centre = {x = center.x, z = center.z},
        length = LW.length,
        width = LW.width,
        command_block_point = {},
        id = id,
        tip = "",
        dimension = dimension,
        really = true
    }

    local can_create = true
    db:iter(function(key, value)
        local ok = check_overlap(base_plane, json.decode(value))
        if ok then
            can_create = false
            return false
        end
        return true
    end)

    if can_create then
        player:say(messages.create_territory.conditions_passed)
        local tip = player:ask(messages.create_territory.input_tip)
        base_plane.tip=tip
        local all_id = tonumber(coromega:send_ws_cmd(("scoreboard players test %s %s * *"):format(territory_data_name,data_scoreboard),true)["OutputMessages"][1]["Parameters"][1]) or 0
        local id = all_id + 1
        local command_block_point = {x=1,z=1}
        local cb_x = tonumber(coromega:send_ws_cmd(('scoreboard players test "_领地_缓存_x" %s * *'):format(data_scoreboard),true)["OutputMessages"][1]["Parameters"][1]) or 0
        local cb_z = tonumber(coromega:send_ws_cmd(('scoreboard players test "_领地_缓存_z" %s * *'):format(data_scoreboard),true)["OutputMessages"][1]["Parameters"][1]) or 0
        if use_new then
            if id < 3 then
                command_block_point = generate_coordinates(id)
            else
                command_block_point = generate_coordinates_by_x_z(cb_x,cb_z)
            end
            omega.cmds.send_wo_cmd(('scoreboard players set "_领地_缓存_x" %s %d'):format(data_scoreboard,command_block_point.x))
            omega.cmds.send_wo_cmd(('scoreboard players set "_领地_缓存_z" %s %d'):format(data_scoreboard,command_block_point.z))
        else
            command_block_point = generate_coordinates(id)
        end
        base_plane.command_block_point=command_block_point
        omega.cmds.send_wo_cmd(("scoreboard players add %s %s 1"):format(territory_data_name,data_scoreboard))
        omega.cmds.send_wo_cmd(("scoreboard players remove %s %s %d"):format(chat.name, money_scoreboard, need_money))
        player:say(messages.create_territory.registering_territory)

        local base_plane_json = json.encode(base_plane)
        omega.cmds.send_wo_cmd(('scoreboard objectives add "_领地_%s" dummy'):format(chat.name))
        omega.cmds.send_wo_cmd(('scoreboard players set %s "_领地_%s" 1'):format(chat.name, chat.name))
        local err = coromega:place_command_block(
            { x = territory_command_block_x+command_block_point.x, y = territory_command_block_y, z = territory_command_block_z+command_block_point.z},
            "repeating_command_block",
            1,
            {
                need_red_stone = false,
                conditional = false,
                command = ('execute in %s positioned %d -64 %d as @a[m=!1,dx=%d,dy=385,dz=%d] unless score @s "_领地_%s" matches 1..1 rotated as @s at @s run tp ^-3 ^ ^-3'):format(dimension, bottom_left_corner.x, bottom_left_corner.z, LW.length, LW.width, chat.name),
                name = ("_领地_%s_%d"):format(chat.name,id),
                tick_delay = 0,
                track_output = false,
                execute_on_first_tick = true
            }
        )
        local actionbar = {
            rawtext = {
                {
                    text = ("§7你目前正在§e%s§7的领地\n§etip: §f"):format(chat.name)
                },
                {
                    translate = tip
                }
            }
        }
        local err = coromega:place_command_block(
            { x = territory_command_block_x+command_block_point.x, y = territory_command_block_y+1, z = territory_command_block_z+command_block_point.z},
            "repeating_command_block",
            1,
            {
                need_red_stone = false,
                conditional = false,
                command = ('execute in %s positioned %d -64 %d as @a[dx=%d,dy=385,dz=%d] unless score @s "%s" matches 1..1 run titleraw @s actionbar %s'):format(dimension, bottom_left_corner.x, bottom_left_corner.z, LW.length, LW.width, tip_scoreboard, json.encode(actionbar)),
                name = ("_领地_%s_%d"):format(chat.name,id),
                tick_delay = 0,
                track_output = false,
                execute_on_first_tick = true
            }
        )
        local err = coromega:place_command_block(
            { x = territory_command_block_x+command_block_point.x, y = territory_command_block_y+2, z = territory_command_block_z+command_block_point.z},
            "repeating_command_block",
            1,
            {
                need_red_stone = false,
                conditional = false,
                command = ('execute in %s positioned %d -64 %d as @e[dx=%d,dy=385,dz=%d] unless entity @s[x=%d,y=-64,z=%d,dx=%d,dy=385,dz=%d] unless score @s "_领地_%s" matches 1..1 run scoreboard players set @s %s 1'):format(dimension, bottom_left_corner.x - 5, bottom_left_corner.z - 5, LW.length + 10, LW.width + 10, bottom_left_corner.x, bottom_left_corner.z, LW.length, LW.width,chat.name, clear_scoreboard),
                name = ("_领地_%s_%d"):format(chat.name,id),
                tick_delay = 0,
                track_output = false,
                execute_on_first_tick = true
            }
        )
        db:set(uuid, base_plane_json)
        player:say(messages.create_territory.creation_success)
        player:say(messages.create_territory.funds_deducted
            :gsub("［扣除金额］", tostring(need_money))
            :gsub("［货币名称］", tostring(money_name))
            :gsub("［剩余金额］", tostring(player_money - need_money))
        )

    else
        player:say(messages.create_territory.overlap)
        player:say(messages.create_territory.creation_failed)
    end
end)

-- 菜单项：添加领地信任玩家
coromega:when_called_by_game_menu(menu.add_whitelist):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name) -- 获取命令调用者
    local uuid = player:uuid_string() -- 获取调用者的UUID
    local territory = db:get(uuid) -- 从数据库获取调用者的领地信息

    -- 如果调用者没有创建领地，则返回提示信息
    if territory == "" then
        player:say(messages.add_whitelist.no_territory)
        return
    end

    local players = coromega:get_all_online_players() -- 获取所有在线玩家
    local target_player_name = chat.msg[1] -- 获取命令参数中的玩家名字

    -- 检查目标玩家是否存在且不是调用者自己
    local target_player
    if target_player_name then
        for _, p in ipairs(players) do
            if p:name() == target_player_name then
                if p:name() == player:name() then
                    player:say(messages.add_whitelist.cannot_add_self)
                    target_player_name = nil -- 清除输入，准备弹出选择菜单
                else
                    target_player = p -- 找到目标玩家
                end
                break
            end
        end
    end

    -- 如果没有输入参数、输入的玩家不存在或尝试添加自己，则显示在线玩家列表
    if not target_player then
        local display_players = {}
        for _, p in ipairs(players) do
            if p:name() ~= player:name() then
                table.insert(display_players, p)
            end
        end
        player:say(messages.add_whitelist.select_player)
        -- 显示在线玩家列表，并让调用者选择
        for index, p in ipairs(display_players) do
            player:say(messages.add_whitelist.player_list:gsub("［索引］", tostring(index)):gsub("［名字］", tostring(p:name())))
        end

        local response = player:ask(messages.add_whitelist.please)
        if response == "取消" then
            player:say(messages.add_whitelist.cancel)
            return
        end

        local target = tonumber(response)
        if not target or target <= 0 or target > #display_players then
            player:say(messages.add_whitelist.invalid_input)
            return
        end

        -- 根据用户输入选择目标玩家
        target_player = display_players[target]
        target_player_name = target_player:name()
    end

    -- 打印信任玩家信息
    coromega:print(chat.name .. ": 信任玩家" .. target_player_name)
    local territory_json = json.decode(territory)

    -- 获取领地白名单中的所有玩家名字
    local all_whitelist_player_name = {}
    for _, whitelist_player in ipairs(territory_json.whitelist) do
        for name in pairs(whitelist_player) do
            table.insert(all_whitelist_player_name, name)
        end
    end

    -- 检查是否可以添加目标玩家到白名单
    local can_add = true
    for _, whitelist_player in ipairs(all_whitelist_player_name) do
        if target_player_name == whitelist_player then
            can_add = false
            break
        end
    end

    -- 如果可以添加，则更新数据库并通知调用者成功
    if can_add then
        table.insert(territory_json.whitelist, { [target_player_name] = target_player:uuid_string() })
        territory = json.encode(territory_json)
        db:set(uuid, territory)
        omega.cmds.send_wo_cmd(('scoreboard players set %s "_领地_%s" 1'):format(target_player_name, chat.name))
        player:say(messages.add_whitelist.success)
    else
        player:say(messages.add_whitelist.already_exists) -- 否则通知调用者失败
    end
end)

-- 菜单项：删除领地信任玩家
coromega:when_called_by_game_menu({
    triggers = menu.remove_whitelist.triggers,
    argument_hint = menu.remove_whitelist.argument_hint,
    usage = menu.remove_whitelist.usage
}):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    local uuid = player:uuid_string()
    local territory = db:get(uuid)
    if territory == "" then
        player:say(messages.remove_whitelist.no_territory)
        return
    end

    local players = coromega:get_all_online_players()
    local target_player_name = chat.msg[1] or ""
    local target_player

    -- 检查输入的玩家是否有效
    for _, p in ipairs(players) do
        if p:name() == target_player_name then
            target_player = p
            if p:name() == player:name() then
                player:say(messages.remove_whitelist.cannot_remove_self)
                target_player = nil
            end
            break
        end
    end

    -- 如果没有有效玩家，则提示玩家选择
    if not target_player then
        
        player:say(messages.remove_whitelist.select_player)
        local display_players = {}
        for _, p in ipairs(players) do
            if p:name() ~= player:name() then
                table.insert(display_players, p)
            end
        end

        -- 显示在线玩家列表，并让调用者选择
        for index, p in ipairs(display_players) do
            player:say(messages.remove_whitelist.player_list:gsub("［索引］", tostring(index)):gsub("［名字］", tostring(p:name())))
        end
        
        local response = player:ask(messages.remove_whitelist.please)
        if response == "取消" then
            player:say(messages.remove_whitelist.cancel)
            return
        end

        local target = tonumber(response)
        if not target or target < 1 or target > #players then
            player:say(messages.remove_whitelist.invalid_input)
            return
        end

        target_player = display_players[target]
    end

    target_player_name = target_player:name()
    coromega:print(chat.name .. ": 删除信任玩家" .. target_player_name)
    local territory_json = json.decode(territory)
    local whitelist = territory_json.whitelist

    -- 从白名单中移除玩家
    for i, wp in ipairs(whitelist) do
        if wp[target_player_name] then
            table.remove(whitelist, i)
            territory = json.encode(territory_json)
            db:set(uuid, territory)
            omega.cmds.send_wo_cmd(('scoreboard players set %s "_领地_%s" 0'):format(target_player_name, chat.name))
            player:say(messages.remove_whitelist.remove_success)
            return
        end
    end

    -- 如果玩家不在白名单中，则提示
    player:say(messages.remove_whitelist.player_not_in_whitelist)
end)

-- 菜单项：列出领地信任玩家
coromega:when_called_by_game_menu(menu.list_whitelist):start_new(function(chat)
    -- 获取命令发起者的玩家对象
    local player = coromega:get_player_by_name(chat.name)
    -- 获取玩家UUID
    local uuid = player:uuid_string()
    -- 从数据库获取玩家的领地信息
    local territory = db:get(uuid)
    -- 如果没有领地信息，则通知玩家并退出
    if territory == "" then
        player:say(messages.list_whitelist.no_territory)
        return
    end
    
    -- 解析领地信息的JSON数据
    local territory_json = json.decode(territory)
    -- 初始化信任玩家名字列表
    local all_whitelist_player_name = {}
    
    -- 遍历领地信任玩家列表
    for _, whitelist in ipairs(territory_json.whitelist) do
        -- 遍历信任玩家对象中的名字
        for name in pairs(whitelist) do
            -- 将信任玩家的名字添加到列表中
            table.insert(all_whitelist_player_name, name)
        end
    end
    
    -- 如果信任玩家列表为空，则通知玩家并退出
    if #all_whitelist_player_name == 0 then
        player:say(messages.list_whitelist.no_whitelist)
        return
    end
    
    -- 通知玩家信任玩家列表的标题
    player:say(messages.list_whitelist.whitelist_header)
    -- 遍历信任玩家列表并通知玩家每个信任玩家的名字
    for _, name in ipairs(all_whitelist_player_name) do
        player:say(name)
    end
end)

-- 菜单项：废除领地
coromega:when_called_by_game_menu(menu.remove_territory):start_new(function(chat)
    -- 获取触发菜单的玩家对象
    local player = coromega:get_player_by_name(chat.name)
    -- 获取玩家的UUID
    local uuid = player:uuid_string()
    -- 从数据库获取玩家的领地信息
    local territory = db:get(uuid)
    
    -- 检查玩家是否已经创建了领地
    if not territory or territory == "" then
        player:say(messages.remove_territory.no_territory)
        return
    end
    
    -- 询问玩家是否确认删除领地
    local confirm = player:ask(messages.remove_territory.confirm_deletion)
    -- 如果玩家确认删除，则继续执行删除操作
    if confirm == "是" or confirm == "y" then
        player:say(messages.remove_territory.deleting)
    else
        -- 如果玩家取消删除，则退出函数
        player:say(messages.remove_territory.cancel_deletion)
        return
    end
    
    -- 解析领地信息为JSON格式
    local territory_json = json.decode(territory)
    -- 获取领地面积
    local territory_area = territory_json.area
    -- 计算删除领地后应返还的金额
    local remove_money = territory_area * remove_one_money
    
    -- 执行删除领地的相关命令
    omega.cmds.send_wo_cmd(('scoreboard objectives remove "_领地_%s"'):format(chat.name))
    omega.cmds.send_wo_cmd(('fill %d %d %d %d %d %d air'):format(territory_command_block_x + territory_json.command_block_point.x, territory_command_block_y, territory_command_block_z + territory_json.command_block_point.z, territory_command_block_x + territory_json.command_block_point.x, territory_command_block_y + 3, territory_command_block_z + territory_json.command_block_point.z))
    -- 从数据库中删除领地记录
    db:delete(uuid)
    -- 将返还的金额加到玩家的计分板上
    omega.cmds.send_wo_cmd(('scoreboard players add %s %s %d'):format(chat.name, money_scoreboard, remove_money))
    
    -- 向玩家显示删除领地成功消息
    player:say(messages.remove_territory.success:gsub("［金额］", tostring(remove_money)):gsub("［货币单位］", money_name))
end)

-- 菜单项：领地返回
coromega:when_called_by_game_menu(menu.return_territory):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    local uuid = player:uuid_string()
    local territory = db:get(uuid)
    if territory == "" then
        player:say(messages.return_territory.no_territory)
        return
    end
    local territory_json=json.decode(territory)
    omega.cmds.send_wo_cmd(('tp %s %d %d %d '):format(chat.name,territory_json.centre.x,territory_json.bottom_left_corner.y,territory_json.centre.z))
    player:say(messages.return_territory.returned)
end)

-- 菜单项：创建假领地
coromega:when_called_by_game_menu({
    triggers = menu.create_fake_territory.triggers,
    argument_hint = menu.create_fake_territory.argument_hint,
    usage = menu.create_fake_territory.usage
}):start_new(function(chat)
    -- 获取执行命令的玩家对象
    local player = coromega:get_player_by_name(chat.name)
    -- 检查玩家是否有OP权限
    if not player:is_op() then
        player:say(messages.create_fake_territory.no_permission)
        return
    end

    -- 获取玩家当前位置
    local pos = player:get_pos().position
    -- 记录起点坐标
    local start_pos = {x = math.floor(pos.x), y = math.floor(pos.y), z = math.floor(pos.z), dimension = player:get_pos().dimension}
    -- 发送起点坐标信息给玩家，并替换标记字
    player:say(messages.create_fake_territory.recorded_start_pos:gsub("［X坐标］", tostring(start_pos.x)):gsub("［Y坐标］", tostring(start_pos.y)):gsub("［Z坐标］", tostring(start_pos.z)))
    omega.cmds.send_wo_cmd(("scoreboard players set %s %s 1"):format(chat.name,creating_scoreboard))
    if show_create_territory_tip then
        coromega:start_new(function()
            local exit = false
            while true do
                if exit then
                    break
                end
                coromega:sleep(0.3)
                omega.cmds.send_ws_cmd_with_resp(("scoreboard players test %s %s * *"):format(chat.name, creating_scoreboard), function(output)
                    if output_to_score(output) == 1 then
                        omega.cmds.send_ws_cmd_with_resp(("querytarget @a[name=%s]"):format(chat.name), function(output)
                            local creating_pos=json.decode(ud2lua(output:user_data().OutputMessages)[1]["Parameters"][1])[1]["position"]
                            local LW=calculateDimensions({x=math.floor(pos.x),z=math.floor(pos.z)}, {x=math.floor(creating_pos.x),z=math.floor(creating_pos.z)})
                            local actionbar = {
                                rawtext = {
                                    {
                                        text = messages.create_fake_territory.size_tip
                                            :gsub("［坐标X］", tostring(math.floor(creating_pos.x)))
                                            :gsub("［坐标Y］", tostring(math.floor(creating_pos.y)))
                                            :gsub("［坐标Z］", tostring(math.floor(creating_pos.z)))
                                            :gsub("［长］", tostring(LW.length))
                                            :gsub("［宽］", tostring(LW.width))
                                            :gsub("［面积］", tostring(LW.length*LW.width))
                                    }
                                }
                            }
                            omega.cmds.send_wo_cmd(("titleraw @a[name=%s] actionbar %s"):format(chat.name,json.encode(actionbar)))
                        end)
                    else
                        exit = true
                        return
                    end
                end)
            end
        end)
    end
    -- 询问玩家是否继续，或者取消操作
    local exit = player:ask(messages.create_fake_territory.move_to_next_point)
    omega.cmds.send_wo_cmd(("scoreboard players set %s %s 0"):format(chat.name,creating_scoreboard))
    -- 如果玩家选择取消，则退出操作
    if exit == "取消" then
        player:say(messages.create_fake_territory.exit_creation)
        return
    end

    -- 获取玩家移动后的终点位置
    local end_pos = player:get_pos().position
    -- 记录终点坐标
    local end_pos_data = {x = math.floor(end_pos.x), y = math.floor(end_pos.y), z = math.floor(end_pos.z), dimension = player:get_pos().dimension}
    -- 发送终点坐标信息给玩家，并替换标记字
    player:say(messages.create_fake_territory.recorded_end_pos:gsub("［X坐标］", tostring(end_pos_data.x)):gsub("［Y坐标］", tostring(end_pos_data.y)):gsub("［Z坐标］", tostring(end_pos_data.z)))

    -- 检查起点和终点的维度是否一致
    if start_pos.dimension ~= end_pos_data.dimension then
        player:say(messages.create_fake_territory.dimension_mismatch)
        return
    end

    -- 计算假领地的尺寸
    local dimensions = calculateDimensions({x = start_pos.x, z = start_pos.z}, {x = end_pos_data.x, z = end_pos_data.z})
    -- 如果长或宽为零，则退出操作
    if dimensions.length == 0 or dimensions.width == 0 then
        player:say(messages.create_fake_territory.invalid_dimensions)
        return
    end

    -- 计算假领地的面积
    local area = calculateSurfaceArea({x = start_pos.x, z = start_pos.z}, {x = end_pos_data.x, z = end_pos_data.z})
    -- 获取假领地左下角坐标
    local bottom_left_corner = getBottomLeftCorner({x = start_pos.x, z = start_pos.z}, {x = end_pos_data.x, z = end_pos_data.z})
    -- 获取假领地中心点坐标
    local center = calculateCenter({x = start_pos.x, z = start_pos.z}, {x = end_pos_data.x, z = end_pos_data.z})

    -- 构建信息消息，并替换标记字
    player:say(messages.create_fake_territory.info_message:gsub("［长］", tostring(dimensions.length)):gsub("［宽］", tostring(dimensions.width)):gsub("［面积］", tostring(area)):gsub("［X坐标］", tostring(bottom_left_corner.x)):gsub("［Z坐标］", tostring(bottom_left_corner.z)):gsub("［X坐标］", tostring(center.x)):gsub("［Z坐标］", tostring(center.z)))

    -- 请求玩家输入假领地的名称
    local display_name = player:ask(messages.create_fake_territory.input_display_name)
    -- 通知玩家正在检查假领地创建条件
    player:say(messages.create_fake_territory.checking_conditions)

    omega.cmds.send_ws_cmd_with_resp(("scoreboard players test %s %s * *"):format(fake_territory_data_name,data_scoreboard), function(output)
        local id = output_to_score(output) + 1
        local base_plane = {
            start = {x = start_pos.x, z = start_pos.z},
            finish = {x = end_pos_data.x, z = end_pos_data.z},
            uuid = player:uuid_string(),
            name = chat.name,
            display_name = display_name,
            whitelist = {},
            bottom_left_corner = {x = bottom_left_corner.x, y = start_pos.y, z = bottom_left_corner.z},
            centre = {x = center.x, z = center.z},
            length = dimensions.length,
            width = dimensions.width,
            id = id,
            dimension = start_pos.dimension,
            really = false
        }
        local can_create = true
        db:iter(function(key, value)
            local check = json.decode(value)
            -- coromega:print(check)
            if check_overlap(base_plane, check) then
                can_create = false
                return false
            end
            return true
        end)

        if can_create then
            player:say(messages.create_fake_territory.conditions_passed)
            player:say(messages.create_fake_territory.registering)
            db:set(("假领地［编号］"):gsub("［编号］",tostring(id)), json.encode(base_plane))
            omega.cmds.send_wo_cmd(("scoreboard players add %s %s 1"):format(fake_territory_data_name,data_scoreboard))
            player:say(messages.create_fake_territory.creation_success)
        else
            player:say(messages.create_fake_territory.overlap_error)
            player:say(messages.create_fake_territory.creation_failed)
        end
    end)
end)

-- 菜单项：废除假领地
coromega:when_called_by_game_menu({
    triggers = menu.remove_fake_territory.triggers,
    argument_hint = menu.remove_fake_territory.argument_hint,
    usage = menu.remove_fake_territory.usage,
}):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    if not player:is_op() then
        player:say(messages.remove_fake_territory.no_permission)
        return
    end
    local fake_territorys = {}
    local fake_territory_names = {}
    db:iter(function(key, value)
        local territory = json.decode(value)
        if not territory.really then
            table.insert(fake_territorys, territory)
            table.insert(fake_territory_names, key)
        end
        return true
    end)
    if not next(fake_territorys) or not next(fake_territory_names) then
        player:say(messages.remove_fake_territory.no_fake_territory)
        return
    end
    player:say(messages.remove_fake_territory.all_fake_territories)
    local display_index = 0
    for index, fake_territory in ipairs(fake_territorys) do
        local coordinates = {
            x = fake_territory.bottom_left_corner.x,
            y = fake_territory.bottom_left_corner.y,
            z = fake_territory.bottom_left_corner.z
        }
        player:say(messages.remove_fake_territory.display:gsub("［索引］",tostring(index)):gsub("［名字］",fake_territory.display_name):gsub("［X坐标］",tostring(coordinates.x)):gsub("［Y坐标］",tostring(coordinates.y)):gsub("［Z坐标］",tostring(coordinates.z)):gsub("［长］",tostring(fake_territory.length)):gsub("［宽］",tostring(fake_territory.width)):gsub("［创建者］",fake_territory.name))
        display_index = display_index + 1
    end
    local reply = player:ask(messages.remove_fake_territory.please)
    if reply == "取消" then
        player:say(messages.remove_fake_territory.cancel_deletion)
        return
    end
    local target = tonumber(reply)
    if not target or target <= 0 or target > display_index then
        player:say(messages.remove_fake_territory.invalid_input)
        return
    end
    db:delete(fake_territory_names[target])
    player:say(messages.remove_fake_territory.delete_success)
end)

-- 菜单项：列出假领地
coromega:when_called_by_game_menu({
    triggers = menu.list_fake_territory.triggers,
    argument_hint = menu.list_fake_territory.argument_hint,
    usage = menu.list_fake_territory.usage,
}):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    if not player:is_op() then
        player:say(messages.list_fake_territory.no_permission)
        return
    end
    local fake_territorys = {}
    db:iter(function(key, value)
        local territory = json.decode(value)
        if not territory.really then
            table.insert(fake_territorys, territory)
        end
        return true
    end)
    if not next(fake_territorys) then
        player:say(messages.list_fake_territory.no_fake_territory)
        return
    end
    player:say(messages.list_fake_territory.list_title)
    for index, fake_territory in ipairs(fake_territorys) do
        local coordinates = {
            x = fake_territory.bottom_left_corner.x,
            y = fake_territory.bottom_left_corner.y,
            z = fake_territory.bottom_left_corner.z
        }
        player:say(messages.list_fake_territory.display:gsub("［索引］",tostring(index)):gsub("［名字］",fake_territory.display_name):gsub("［X坐标］",tostring(coordinates.x)):gsub("［Y坐标］",tostring(coordinates.y)):gsub("［Z坐标］",tostring(coordinates.z)):gsub("［长］",tostring(fake_territory.length)):gsub("［宽］",tostring(fake_territory.width)):gsub("［创建者］",fake_territory.name))
    end
end)

-- 菜单项：列出玩家领地
coromega:when_called_by_game_menu({
    triggers = menu.list_territory.triggers,
    argument_hint = menu.list_territory.argument_hint,
    usage = menu.list_territory.usage,
}):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    if not player:is_op() then
        player:say(messages.list_territory.no_permission)
        return
    end
    local territorys = {}
    db:iter(function(key, value)
        local territory = json.decode(value)
        if territory.really then
            table.insert(territorys, territory)
        end
        return true
    end)
    if not next(territorys) then
        player:say(messages.list_territory.no_territory)
        return
    end
    player:say(messages.list_territory.list_title)
    for index, territory in ipairs(territorys) do
        local coordinates = {
            x = territory.bottom_left_corner.x,
            y = territory.bottom_left_corner.y,
            z = territory.bottom_left_corner.z
        }
        if territory.tip == nil then territory_json.tip = "无法获取" end
        player:say(messages.list_territory.display:gsub("［索引］",tostring(index)):gsub("［提示］",territory.tip):gsub("［X坐标］",tostring(coordinates.x)):gsub("［Y坐标］",tostring(coordinates.y)):gsub("［Z坐标］",tostring(coordinates.z)):gsub("［长］",tostring(territory.length)):gsub("［宽］",tostring(territory.width)):gsub("［创建者］",territory.name))
    end
end)

-- 菜单项：废除玩家领地
coromega:when_called_by_game_menu({
    triggers = menu.remove_player_territory.triggers,
    argument_hint = menu.remove_player_territory.argument_hint,
    usage = menu.remove_player_territory.usage,
}):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    if not player:is_op() then
        player:say(messages.remove_player_territory.no_permission)
        return
    end
    local territorys = {}
    local territory_names = {}
    db:iter(function(key, value)
        local territory = json.decode(value)
        if territory.really then
            table.insert(territorys, territory)
            table.insert(territory_names, key)
        end
        return true
    end)
    if not next(territorys) or not next(territory_names) then
        player:say(messages.remove_player_territory.no_territories)
        return
    end
    player:say(messages.remove_player_territory.list_header)
    local display_index = 0
    for index, territory in ipairs(territorys) do
        player:say(messages.remove_player_territory.display:gsub("［索引］", tostring(index)):gsub("［主人］", territory.name):gsub("［X坐标］", tostring(territory.bottom_left_corner.x)):gsub("［Y坐标］", tostring(territory.bottom_left_corner.y)):gsub("［Z坐标］", tostring(territory.bottom_left_corner.z)):gsub("［面积］", tostring(territory.area)))
        display_index = display_index + 1
    end
    local reply = player:ask(messages.remove_player_territory.please)
    if reply == "取消" then
        player:say(messages.remove_player_territory.cancel)
        return
    end
    local target = tonumber(reply)
    if not target or target <= 0 or target > display_index then
        player:say(messages.remove_player_territory.invalid_input)
        return
    end
    local confirm = player:ask(messages.remove_player_territory.confirm_delete)
    if confirm == "是" or confirm == "y" then
        player:say(messages.remove_player_territory.deleting)
    else
        player:say(messages.remove_player_territory.cancel)
        return
    end
    local territory_json = json.decode(db:get(territory_names[target]))
    omega.cmds.send_wo_cmd(('scoreboard objectives remove "_领地_%s"'):format(territory_json.name))
    omega.cmds.send_wo_cmd(('fill %d %d %d %d %d %d air'):format(territory_command_block_x + territory_json.command_block_point.x, territory_command_block_y, territory_command_block_z + territory_json.command_block_point.z, territory_command_block_x + territory_json.command_block_point.x, territory_command_block_y + 3, territory_command_block_z + territory_json.command_block_point.z))
    db:delete(territory_names[target])
    player:say(messages.remove_player_territory.delete_success)
end)

-- 菜单项：开启领地主人提示
coromega:when_called_by_game_menu(menu.enable_territory_owner_hint):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    omega.cmds.send_wo_cmd(("scoreboard players set %s %s 0"):format(chat.name,tip_scoreboard))
    player:say(messages.territory_owner_hint.enabled)
end)

-- 菜单项：关闭领地主人提示
coromega:when_called_by_game_menu(menu.disable_territory_owner_hint):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    omega.cmds.send_wo_cmd(("scoreboard players set %s %s 1"):format(chat.name,tip_scoreboard))
    player:say(messages.territory_owner_hint.disabled)
end)

-- 菜单项：重置领地
coromega:when_called_by_game_menu({
    triggers = menu.reset_territories.triggers,
    argument_hint = menu.reset_territories.argument_hint,
    usage = menu.reset_territories.usage
}):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    if not player:is_op() then
        player:say(messages.reset_territories.no_permission)
        return
    end

    local territorys = {}
    local territory_names = {}
    db:iter(function(key, value)
        local territory = json.decode(value)
        if territory.really then
            table.insert(territorys, territory)
            table.insert(territory_names, key)
        end
        return true
    end)

    if not next(territorys) or not next(territory_names) then
        player:say(messages.reset_territories.no_territories)
        return
    end

    local confirm = player:ask(messages.reset_territories.confirm_delete)
    if confirm ~= "是" and confirm ~= "y" then
        player:say(messages.reset_territories.exited_deletion)
        return
    end

    local confirm2 = player:ask(messages.reset_territories.confirm_delete_again)
    if confirm2 ~= "是" and confirm2 ~= "y" then
        player:say(messages.reset_territories.exited_deletion)
        return
    end

    local confirm3 = player:ask(messages.reset_territories.confirm_no_mistake)
    if confirm3 ~= "是" and confirm3 ~= "y" then
        player:say(messages.reset_territories.exited_deletion)
        return
    end

    local confirm4 = player:ask(messages.reset_territories.final_confirm)
    if confirm4 ~= "是" and confirm4 ~= "y" then
        player:say(messages.reset_territories.exited_deletion)
        return
    end

    player:say(messages.reset_territories.deleting_territories)

    for index, territory_name in ipairs(territory_names) do
        local territory = db:get(territory_name)
        local territory_json = json.decode(territory)
        player:say(messages.reset_territories.deleting_specific_territory:gsub("［索引］",tostring(index)):gsub("［主人］",territory_json.name))
        omega.cmds.send_wo_cmd(('scoreboard objectives remove "_领地_%s"'):format(territory_json.name))
        omega.cmds.send_wo_cmd(('fill %d %d %d %d %d %d air'):format(territory_command_block_x + territory_json.command_block_point.x, territory_command_block_y, territory_command_block_z + territory_json.command_block_point.z, territory_command_block_x + territory_json.command_block_point.x, territory_command_block_y + 3, territory_command_block_z + territory_json.command_block_point.z))
        db:delete(territory_name)
    end

    omega.cmds.send_wo_cmd(("scoreboard players set %s %s 0"):format(territory_data_name,data_scoreboard))
    omega.cmds.send_wo_cmd(('scoreboard players set "_领地_缓存_x" %s 0'):format(data_scoreboard))
    omega.cmds.send_wo_cmd(('scoreboard players set "_领地_缓存_z" %s 0'):format(data_scoreboard))
    player:say(messages.reset_territories.all_territories_deleted)
end)

-- 菜单项：重置假领地
coromega:when_called_by_game_menu({
    triggers = menu.reset_fake_territories.triggers,
    argument_hint = menu.reset_fake_territories.argument_hint,
    usage = menu.reset_fake_territories.usage
}):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    local module_messages = messages.reset_fake_territories

    if not player:is_op() then
        player:say(module_messages.no_permission)
        return
    end

    local fake_territory_names = {}
    db:iter(function(key, value)
        local territory = json.decode(value)
        if not territory.really then
            table.insert(fake_territory_names, key)
        end
        return true
    end)

    if not next(fake_territory_names) then
        player:say(module_messages.no_fake_territories)
        return
    end

    local confirm = function(msg)
        local response = player:ask(msg)
        return response == "是" or response == "y"
    end

    if not confirm(module_messages.confirm_start) then
        player:say(module_messages.exit_deletion)
        return
    end

    if not confirm(module_messages.confirm_really) then
        player:say(module_messages.exit_deletion)
        return
    end

    if not confirm(module_messages.confirm_sure) then
        player:say(module_messages.exit_deletion)
        return
    end

    if not confirm(module_messages.confirm_final) then
        player:say(module_messages.exit_deletion)
        return
    end

    player:say(module_messages.deleting_progress)
    for index, fake_territory_name in ipairs(fake_territory_names) do
        player:say(module_messages.deleting_single:gsub("［索引］",tostring(index)))
        db:delete(fake_territory_name)
    end

    omega.cmds.send_wo_cmd(("scoreboard players set %s %s 0"):format(fake_territory_data_name,data_scoreboard))
    player:say(module_messages.all_deleted)
end)

-- 菜单项: 修改领地提示文本
coromega:when_called_by_game_menu(menu.change_territory_tip):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name) -- 获取命令调用者
    local uuid = player:uuid_string() -- 获取调用者的UUID
    local territory = db:get(uuid) -- 从数据库获取调用者的领地信息

    -- 如果调用者没有创建领地，则返回提示信息
    if territory == "" then
        player:say(messages.change_territory_tip.no_territory)
        return
    end
    local tip = chat.msg[1] or nil
    if not tip or tip == "" then
        tip = player:ask(messages.change_territory_tip.please)
    end
    player:say(messages.change_territory_tip.wait)
    local territory_json = json.decode(territory)
    territory_json.tip = tip
    local actionbar = {
        rawtext = {
            {
                text = ("§e< §7你目前正在§e%s§7的领地 §e>\n§7---------------------------\n>> §g领地提示: §f"):format(chat.name)
            },
            {
                translate = tip
            }
        }
    }
    -- coromega:print(json.encode(actionbar))
    local err = coromega:place_command_block(
        { x = territory_command_block_x+territory_json.command_block_point.x, y = territory_command_block_y+1, z = territory_command_block_z+territory_json.command_block_point.z},
        "repeating_command_block",
        1,
        {
            need_red_stone = false,
            conditional = false,
            command = ('execute in %s positioned %d -64 %d as @a[dx=%d,dy=385,dz=%d] unless score @s "%s" matches 1..1 run titleraw @s actionbar %s'):format(territory_json.dimension, territory_json.bottom_left_corner.x, territory_json.bottom_left_corner.z, territory_json.length, territory_json.width, tip_scoreboard, json.encode(actionbar)),
            name = ("_领地_%s_%d"):format(chat.name,territory_json.id),
            tick_delay = 0,
            track_output = false,
            execute_on_first_tick = true
        }
    )
    player:say(messages.change_territory_tip.success:gsub("［提示文本］",tip))
    db:set(uuid,json.encode(territory_json))
end)

-- 菜单项：领地信息
coromega:when_called_by_game_menu(menu.my_territory):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name) -- 获取命令调用者
    local uuid = player:uuid_string() -- 获取调用者的UUID
    local territory = db:get(uuid) -- 从数据库获取调用者的领地信息

    -- 如果调用者没有创建领地，则返回提示信息
    if territory == "" then
        player:say(messages.my_territory.no_territory)
        return
    end
    -- coromega:print(territory)
    local territory_json = json.decode(territory)
    coromega:print(json.encode(territory_json))
    coromega:print(messages.my_territory.info)
    if territory_json.tip == nil then territory_json.tip = "无法获取" end
    player:say(messages.my_territory.info
        :gsub("［长］", tostring(territory_json.length))
        :gsub("［宽］", tostring(territory_json.width))
        :gsub("［面积］", tostring(territory_json.area))
        :gsub("［价值］", tostring(remove_one_money*territory_json.area))
        :gsub("［货币名称］", tostring(money_name))
        :gsub("［左下角X］", tostring(territory_json.bottom_left_corner.x))
        :gsub("［左下角Z］", tostring(territory_json.bottom_left_corner.z))
        :gsub("［中心X］", tostring(territory_json.centre.x))
        :gsub("［中心Z］", tostring(territory_json.centre.z))
        :gsub("［提示文本］",territory_json.tip)
    )
end)

-- 菜单项：初始化领地
coromega:when_called_by_game_menu(menu.initialize_territorial_system):start_new(function(chat)
    local player = coromega:get_player_by_name(chat.name)
    if not player:is_op() then
        player:say(messages.initialize_territorial_system.no_permission)
        return
    end
    initialize_territorial_system()
end)

coromega:run()