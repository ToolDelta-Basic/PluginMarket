local omega = require("omega")
local json = require("json")
--- @type Coromega
local coromega = require("coromega").from(omega)

local is_print_config = coromega.config["加载插件时是否在终端显示配置"] or false
if is_print_config == true then
    print("config of 全物品商店:  ",json.encode(coromega.config))
end

-- 如果你需要调试请将下面一段解除注释，关于调试的方法请参考文档
-- local dbg = require('emmy_core')
-- dbg.tcpConnect('localhost', 9966)
-- print("waiting...")
-- for i=1,1000 do -- 调试器需要一些时间来建立连接并交换所有信息
--     -- 如果始终无法命中断点，你可以尝试将 1000 改的更大
--     print(".")
-- end
-- print("end")




--                   ꧁༺❀ 天枢 ༒ 公益 ❀༻꧂
--§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■

--本插件作者：style_天枢
--本插件为免费开源的NeOmega插件，严禁倒卖，违者必究
--使用时请注意修改服务器名称、货币名称、数据库存储类型等配置噢
--为方便读者阅读，本插件在重要部分均已标注说明注释
--如果您发现了bug，欢迎反馈，反馈邮箱：< 485429738@qq.com >

--§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■
--                   ꧁༺❀ By NeOmega ❀༻꧂





local store_trigger_words = coromega.config["商店触发词(在游戏内输入下列触发词即可唤起商店)"] or { "商店","商城","商场","store","shop" }               --调用各种配置，若要修改配置，请前往store[LuaLoader]-1.json
local store_usage = coromega.config["商店提示信息(这串信息将会显示在omg菜单关于商店的描述中)"] or "全物品商店系统"
local database_type = coromega.config["您希望使用___存储玩家的账户余额信息 ( 1:NeOmega的data数据库; 2:记分板 )"] or 2
if database_type ~= 1 and database_type ~= 2 then database_type = 2 end
local coin_scoreboard_name = coromega.config["货币记分板名称"] or "金币"
local coin_scoreboard_display_name = coromega.config["货币记分板显示名称"] or "§e金币"
local player_balance_db_name = coromega.config["<玩家余额信息>数据库名称"] or "玩家余额信息"
local player_transfer_db_name = coromega.config["<玩家转账信息>数据库名称"] or "玩家转账信息"
local total_sell_goods = coromega.config["回收商店信息"]
local total_buy_goods = coromega.config["购买商店信息"]
local serve_name_cn = coromega.config["商店中文名"] or "§b沃§e尔§a玛"
local serve_name_en = coromega.config["商店英文名"] or "§l§b❐ All§eIt§aem §dStore"
local hello_word = coromega.config["进入商店欢迎词"] or "§eＳｅｒｖｅｒ§7>> §d[Store] §b欢迎光临§e全物品§a商店系统§d✦✧~"
local coin_name = coromega.config["货币名(请注意，此货币名仅用于显示在商店中，与记分板无关)"] or "金币"
local input_timeout = coromega.config["回复超时__秒自动关闭商店"] or 60
local sell_items_per_page = coromega.config["回收商店栏目每页显示物品数量"] or 10
local buy_items_per_page = coromega.config["购买商店栏目每页显示物品数量"] or 10
local rank_players_per_page = coromega.config["玩家余额排行每页显示玩家数量"] or 20
local rank_max_num = coromega.config["玩家余额排行只展示前___名玩家"] or 100
local sell_max_num = coromega.config["回收物品时允许输入的最大数量"] or 999
local buy_max_num = coromega.config["购买物品时允许输入的最大数量"] or 999
local is_banned_sell_store = coromega.config["是否禁用<回收商店>"] or false
local is_banned_buy_store = coromega.config["是否禁用<购买商店>"] or false
local is_banned_query_balance = coromega.config["是否禁用<查询余额>"] or false
local is_banned_transfer_balance_system = coromega.config["是否禁用<转账系统>"] or false
local is_banned_player_balance_rank = coromega.config["是否禁用<余额排行>"] or false
local is_banned_initiate_transfer = coromega.config["若开启转账系统，是否禁用<发起转账>"] or false
local is_banned_withdraw_transfer = coromega.config["若开启转账系统，是否禁用<撤回转账>"] or false
local is_new_player_default_not_rank = coromega.config["新玩家默认不参与余额排行"] or false
local decimal_places = coromega.config["显示余额时保留几位小数(不改变真实余额数据，仅显示到该位数)"] or 2
local max_decimal_places = coromega.config["玩家余额最多保留几位小数(改变真实余额数据，超出后多余的小数部分会直接被删掉！)"] or 5
local is_banned_shield_words_correct = coromega.config["是否禁用<屏蔽词校正>"] or false
local shield_words_correct_separators = coromega.config["屏蔽词校正分隔符(建议使用中文或英文字母，使用标点符号或特殊符号如#网易仍会屏蔽)"] or {"Z","z"}
local is_banned_store_blacklist = coromega.config["是否禁用<商店黑名单>"] or false
local store_blacklist_tag_name = coromega.config["商店黑名单标签名称"] or "ban_store"
local is_banned_discount = coromega.config["是否禁用<打折/涨价功能>"] or false
local sell_store_rate = coromega.config["回收商店价格倍率"] or 1
local buy_store_rate = coromega.config["购买商店价格倍率"] or 1
if is_banned_discount == true then sell_store_rate = 1 buy_store_rate = 1 end
local is_banned_transfer_tax = coromega.config["是否禁用<转账收税功能>"] or false
local transfer_tax_rate = coromega.config["转账税率"] or 0.001
if is_banned_transfer_tax == true then transfer_tax_rate = 0 end
local is_banned_sell_store_refund = coromega.config["是否禁用<回收商店>退款功能"] or false
local sell_store_refund_time = coromega.config["<回收商店>交易完成后___秒内允许退款"] or 120
local is_banned_buy_store_refund = coromega.config["是否禁用<购买商店>退款功能"] or false
local buy_store_refund_time = coromega.config["<购买商店>交易完成后___秒内允许退款"] or 120

local messages = {
    store_options = {
        top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
        sever_info = serve_name_en.."         §r§aBy §bstyle_天枢",
        sell_store = "§l§b[ §e1§b ] 回收商店 §r§e在此回收您的物品来获得余额",
        buy_store = "§l§b[ §e2§b ] 购买商店 §r§e可购买您需要的物品噢~",
        query_balance = "§l§b[ §e3§b ] 查询余额 §r§e来看看您的账户有多少钱吧~",
        transfer_balance = "§l§b[ §e4§b ] 转账系统 §r§e将您的余额转至他人账户上",
        balance_rank = "§l§b[ §e5§b ] 余额排行 §r§e看看您的余额能排第几名吧~",
        bottom_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧",
        choose_option = "§a❀ §b输入 §e[1-5]§b 之间的数字以选择",
        leave_store = "§a❀ §b输入 §c取消 §b退出商店",
        input_err = "§c❀ 您输入的文本无法被识别，请重新输入"
    },
    sell_store_options = {
        top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
        info = "§d❐ §a共发现 §b%s §a项物品可以回收 §f丨 §b您的余额： §e%s "..coin_name,
        item_value = "§l§b[ §e%s§b ] §r§%s 1 %s 可兑换 %s "..coin_name,
        middle_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧",
        pages = "§l§a[ §ePre§a ] §b上页§r§f▶ §7%s/%s §f◀§l§b下页 §a[ §eNext §a]",
        input_cnitem_or_number = "§a❀ §b输入 §e物品名称 §b或 §e[1-%s] §a之间的数字编号 §e回收物品 §c(只能回收上述物品)",
        pre_page = "§a❀ §b输入 §dPre §e转到上一页",
        next_page = "§a❀ §b输入 §dNext §e转到下一页",
        change_page = "§a❀ §b输入 §d数字+页 §e转到任意页",
        leave_store = "§a❀ §b输入 §c取消 §e退出商店",
        bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
        input = "§a❀ 请输入_",
        is_first_page = "§c❀ 已经是第一页啦~",
        is_final_page = "§c❀ 已经是最后一页啦~",
        page_not_exist = "§c❀ 不存在第%s页！请重新输入！",
        input_err = "§c❀ 请输入正确的物品名称或编号",
        sell_number = "§d❀ §a请输入您想回收 §b%s §e(单价: %s "..coin_name.." 编号: %s) §a的数量 可填范围 §e[1-"..sell_max_num.."]",
        leave_store2 = "§d❀ §b输入 §c取消 §b退出商店",
        input_err2 = "§c❀ 物品数量格式有误，请重新输入",
        item_not_enough = "§c❀ 您背包内的 %s 数量不足 %s 个"
    },
    buy_store_front = {
        top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
        info = "§d❐ §a您可以进行§b以下操作",
        input_cnitem = "§a❀ §b输入您想购买的物品中文名称 §e(可以少字但不要打错字) §a系统将自动进行搜索",
        input_number = "§a❀ §b输入对应物品的编号 §e(如果您不知道编号是多少 §a建议直接输入中文进行搜索)",
        leave_store = "§a❀ §b输入 §c取消 §b退出商店",
        bottom_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
    },
    buy_store_options = {
        top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
        info = "§d❐ §a共发现 §b%s §a项商品 §f丨 §b您的余额： §e%s "..coin_name,
        item_value = "§l§b[ §e%s§b ] §r§b%s §f丨 §a单价 §e%s "..coin_name,
        middle_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧",
        pages = "§l§a[ §ePre§a ] §b上页§r§f▶ §7%s/%s §f◀§l§b下页 §a[ §eNext §a]",
        input_number = "§a❀ §b输入商品前面的数字编号 §e购买商品",
        input_cnitem = "§a❀ §b输入任意物品中文名称 §e再次搜索商品",
        pre_page = "§a❀ §b输入 §dPre §e转到上一页",
        next_page = "§a❀ §b输入 §dNext §e转到下一页",
        change_page = "§a❀ §b输入 §d数字+页 §e转到任意页",
        leave_store = "§a❀ §b输入 §c取消 §e退出商店",
        bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
        input = "§a❀ 请输入_",
        item_not_sell = "§c❀ 此物品 (%s 编号: %s) 暂不售卖！",
        is_first_page = "§c❀ 已经是第一页啦~",
        is_final_page = "§c❀ 已经是最后一页啦~",
        page_not_exist = "§c❀ 不存在第%s页！请重新输入！",
        item_not_found = "§c❀ 没有找到匹配的物品",
        buy_number = "§d❀ §a请输入您想购买 §b%s §e(单价: %s "..coin_name.." 编号: %s) §a的数量 可填范围 §e[1-"..buy_max_num.."]",
        leave_store2 = "§d❀ §b输入 §c取消 §b退出商店",
        input_err2 = "§c❀ 物品数量格式有误，请重新输入",
        balance_not_enough = "§c❀ 您的账户余额不足 %s "..coin_name
    },
    query_balance = {
        top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
        hello_word = "§d❐ §e玩家 §b%s §a您好!",
        info = "§d❐ §b您的 §e账户余额： §d%s "..coin_name,
        bottom_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧"
    },
    transfer_balance_system = {
        transfer_balance_system_options = {
            top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
            initiate_transfer = "§l§b[ §e1§b ] §r§a发起转账 §e将您的余额转让给他人",
            withdraw_transfer = "§l§b[ §e2§b ] §r§c撤回转账 §e我要撤销我的转账 §b只有对方暂未接收转账的情况下才能撤回",
            bottom_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧",
            choose_option = "§a❀ §b输入 §e[1-2]§b 之间的数字以选择",
            leave_store = "§a❀ §b输入 §c取消 §b退出商店",
            input_err = "§c❀ 您输入的文本无法被识别，请重新输入"
        },
        initiate_transfer_options = {
            top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
            info = "§d❐ §b如果您想转账给在线玩家 §e请输入玩家名称前的编号",
            online_player_names = "§l§b[ §e%s§b ] §r§a%s",
            bottom_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧",
            if_player_offline = "§a❀ §b如果该玩家已下线 §e请输入该玩家的全名 §c不要打错字！",
            leave_store = "§a❀ §b输入 §c取消 §e退出商店",
            transfer_balance = "§d❀ §a请输入您想转账给 §b%s §a的金额 §b您的余额: §e[ %s "..coin_name.." ]",
            leave_store2 = "§d❀ §b输入 §c取消 §b退出商店",
            balance_not_enough = "§c❀ 您的账户余额不足 %s "..coin_name,
            transfer_format_err = "§c❀ 转账金额格式有误，请输入正整数！"
        },
        withdraw_transfer_options = {
            top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
            info = "§d❐ §b检测到您有以下转账尚未被接收 §c若要撤销 §e请输入前面的编号",
            transfer_list = "§l§b[ §e%s§b ] §r§b转账 §a金额 §e%s "..coin_name.." §b至 §a%s",
            bottom_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧",
            choose_option = "§a❀ §b输入 §e[1-%s]§b 之间的数字以选择",
            leave_store = "§a❀ §b输入 §c取消 §e退出商店",
            input_err = "§c❀ 您输入的文本无法被识别，请重新输入",
            transfer_not_found = "§c❀ 您没有发起过转账或您的转账已全部被接收"
        }
    },
    balance_rank = {
        top_framework = "\n§d✧✦§f〓〓§b〓〓〓§9〓〓〓§1〓〓"..serve_name_cn.."§1〓〓§9〓〓〓§b〓〓〓§f〓〓§d✦✧",
        info_yes = "§d❐ §b每页将展示 §a%s名 §b玩家 §f丨 §e您是否参与排名 §f[§a✔§f]",
        info_no = "§d❐ §b每页将展示 §a%s名 §b玩家 §f丨 §e您是否参与排名 §f[§c✘§f]",
        caller_balance_rank = "§l§b[ §d%s§b ] §r§a%s §b余额 §e%s "..coin_name.." ",
        separator = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
        player_balance_rank = "§l§b[ §e%s§b ] §r§a%s §b余额 §e%s "..coin_name.." ",
        middle_framework = "§d✧✦§f〓〓§b〓〓〓§9〓〓〓〓§1〓〓〓〓〓〓§9〓〓〓〓§b〓〓〓§f〓〓§d✦✧",
        pages = "§l§a[ §ePre§a ] §b上页§r§f▶ §7%s/%s §f◀§l§b下页 §a[ §eNext §a]",
        rank_yes = "§a❀ §b输入 §ery §a参与余额排行并保存",
        rank_no = "§a❀ §b输入 §ern §c退出余额排行并保存",
        pre_page = "§a❀ §b输入 §dPre §e转到上一页",
        next_page = "§a❀ §b输入 §dNext §e转到下一页",
        change_page = "§a❀ §b输入 §d数字+页 §e转到任意页",
        leave_store = "§a❀ §b输入 §c取消 §e退出商店",
        bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
        input = "§e❀ §d输入其他任意文本可关闭排行榜显示",
        is_first_page = "§c❀ 已经是第一页啦~",
        is_final_page = "§c❀ 已经是最后一页啦~",
        page_not_exist = "§c❀ 不存在第%s页！请重新输入！",
        input_other = "§a❀ 已关闭排行榜~",
        rank_yes_success = "§a❀ 您已成功参与排名！",
        rank_no_success = "§c❀ 您已退出了排名qwq"
    },
    found_transfer = {
        top_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
        info ="§d❐ §b玩家 §e%s §b向您发来了一笔转账 §f丨 §e转账金额: %s "..coin_name,
        transfer_tax = "§d❀ §b当前税率: §e%s §f丨 §b预计您可以收到: §e%s"..coin_name,
        receive_balance = "§a❀ §b输入 §ey §a接受转账并添加至您的余额中",
        refuse_transfer = "§a❀ §b输入 §en §c拒绝接受转账 余额将退回至对方账户",
        other_input = "§a❀ §b输入 §e其他任意字符 §b暂不处理",
        bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
        refuse_transfer2 = "§c❀ 您拒绝了来自 %s 的转账"
    },
    receipt = {
        sell_store_receipt = {
            top_framework = "\n§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            receipt_info = "§d❐ §b%s §e您好 §f丨 §a这是您的账单 ",
            type = "§a❀ §b类型: §d回收商店",
            item = "§a❀ §b物品: §e%s",
            value = "§a❀ §b单价: §f%s",
            number = "§a❀ §b数量: §e%s",
            balance_change = "§a❀ §b余额: §f%s §a+ %s → §b%s "..coin_name,
            bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            goodbye_word = "§a❀ 欢迎下次光临~ qwq",
            refund_word = "§c❀ 如果您卖错了东西，请在%s秒内输入\"退款\"，输入其他任何文本或到时间后将自动结束交易"
        },
        sell_store_refund_receipt = {
            top_framework = "\n§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            receipt_info = "§d❐ §b%s §e您好 §f丨 §a这是您的账单 ",
            type = "§a❀ §b类型: §d回收商店 §f丨 §c已退款",
            item = "§a❀ §b物品: §e%s",
            value = "§a❀ §b单价: §f%s",
            number = "§a❀ §b数量: §e%s",
            balance_change = "§a❀ §b余额: §f%s §c- %s → §b%s "..coin_name,
            bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            goodbye_word = "§a❀ 本次交易已结束~ qwq",
            balance_not_enough = "§c❀ 您的账户余额不足 %s "..coin_name
        },
        buy_store_receipt = {
            top_framework = "\n§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            receipt_info = "§d❐ §b%s §e您好 §f丨 §a这是您的账单 ",
            type = "§a❀ §b类型: §d购买商店",
            item = "§a❀ §b物品: §e%s",
            value = "§a❀ §b单价: §f%s",
            number = "§a❀ §b数量: §e%s",
            balance_change = "§a❀ §b余额: §f%s §c- %s → §b%s "..coin_name,
            bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            goodbye_word = "§a❀ 欢迎下次光临~ qwq",
            refund_word = "§c❀ 如果您买错了东西，请在%s秒内输入\"退款\"，输入其他任何文本或到时间后将自动结束交易"
        },
        buy_store_refund_receipt = {
            top_framework = "\n§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            receipt_info = "§d❐ §b%s §e您好 §f丨 §a这是您的账单 ",
            type = "§a❀ §b类型: §d购买商店 §f丨 §c已退款",
            item = "§a❀ §b物品: §e%s",
            value = "§a❀ §b单价: §f%s",
            number = "§a❀ §b数量: §e%s",
            balance_change = "§a❀ §b余额: §f%s §a+ %s → §b%s "..coin_name,
            bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            goodbye_word = "§a❀ 本次交易已结束~ qwq",
            item_not_enough = "§c❀ 您背包内的 %s 数量不足 %s 个"
        },
        receive_transfer_receipt = {
            top_framework = "\n§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            receipt_info = "§d❐ §b%s §e您好 §f丨 §a这是您的转账收款单 ",
            condition = "§a❀ §b状态: §d已接收",
            orig_player = "§a❀ §b发起者: §e%s",
            target_player = "§a❀ §b接收者: §e%s",
            transfer_balance = "§a❀ §b转账金额: §6%s",
            balance_change = "§a❀ §b您的余额: §f%s §a+ %s → §b%s "..coin_name,
            bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■"
        },
        refuse_transfer_receipt = {
            top_framework = "\n§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            receipt_info = "§d❐ §b%s §e您好 §f丨 §a这是您的转账申请单 ",
            condition = "§a❀ §b状态: §c被拒绝",
            orig_player = "§a❀ §b发起者: §e%s",
            target_player = "§a❀ §b接收者: §e%s",
            transfer_balance = "§a❀ §b转账金额: §6%s",
            balance_change = "§a❀ §b您的余额: §f%s §a+ %s → §b%s "..coin_name,
            bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■"
        },
        initiate_transfer_receipt = {
            top_framework = "\n§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            receipt_info = "§d❐ §b%s §e您好 §f丨 §a这是您的转账申请单 ",
            condition = "§a❀ §b状态: §a已发出",
            orig_player = "§a❀ §b发起者: §e%s",
            target_player = "§a❀ §b接收者: §e%s",
            transfer_balance = "§a❀ §b转账金额: §6%s",
            balance_change = "§a❀ §b您的余额: §f%s §c- %s → §b%s "..coin_name,
            bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            tip = "§d❐ §b当对方上线后可选择是否接收转账 §a在此之前您可随时§c撤销这笔转账"
        },
        withdraw_transfer_receipt = {
            top_framework = "\n§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■",
            receipt_info = "§d❐ §b%s §e您好 §f丨 §a这是您的转账申请单 ",
            condition = "§a❀ §b状态: §c已撤销",
            orig_player = "§a❀ §b发起者: §e%s",
            target_player = "§a❀ §b接收者: §e%s",
            transfer_balance = "§a❀ §b转账金额: §6%s",
            balance_change = "§a❀ §b您的余额: §f%s §a+ %s → §b%s "..coin_name,
            bottom_framework = "§c■•〓〓§6〓〓〓§e〓〓〓〓§f〓〓〓〓〓〓§e〓〓〓〓§6〓〓〓§c〓〓•■"
        }
    },
    close_store = {
        timeout = "§c❀ 回复超时，已自动退出商店",
        cancel = "§c❀ 已退出商店",
        transfer_timeout = "§c❀ 回复超时，已自动退出，重新唤起商店可继续处理转账",
        not_sell_store = "§c❀ 哎呀~回收商店被关闭啦，请联系腐竹开启噢~",
        not_buy_store = "§c❀ 哎呀~购买商店被关闭啦，请联系腐竹开启噢~",
        not_query_balance = "§c❀ 哎呀~查询余额功能被关闭啦，请联系腐竹开启噢~",
        not_transfer_balance_system = "§c❀ 哎呀~转账系统被关闭啦，请联系腐竹开启噢~",
        not_balance_rank = "§c❀ 哎呀~余额排行功能被关闭啦，请联系腐竹开启噢~",
        not_initiate_transfer = "§c❀ 哎呀~发起转账功能被关闭啦，请联系腐竹开启噢~",
        not_withdraw_transfer = "§c❀ 哎呀~撤回转账功能被关闭啦，请联系腐竹开启噢~",
        blacklist_info = "§c❀ 您被管理员禁止使用商店功能，详情请联系服务器管理员噢~"
    },
    shield_words_correct = {
        info1 = "§e❀ §7看起来您的消息可能被屏蔽了qnq，我们为您提供了屏蔽词校正功能",
        info2 = "§e❀ §7您可以在文本中添加分隔符\"%s\"来输入屏蔽词，如输入\"%s64\"可被识别为64"
    }
}

local function is_positive_integer(str)               --定义函数：判断输入值是否是正整数，用于判断物品数量、物品编号等数值
    if str == nil then
        return false
    else
        return string.match(str, "^[1-9]%d*$") ~= nil
    end
end

local function is_Positive_Number(str)               --定义函数：判断输入值是否是正数，用于判断金额
    local num = tonumber(str)
    if num and num > 0 then
        return true
    else
        return false
    end
end

local function is_Number_Page(str)               --定义函数：判断输入值是否是“数字+页”格式，用于后面的商店栏目翻页
    return string.match(str, "^%d+页$") ~= nil
end

local function remove_Separator(str)               --定义函数：删除文本中的屏蔽词分隔符，用于绕过屏蔽词识别玩家的屏蔽词输入
    if is_banned_shield_words_correct == false then
        if str == nil then
            return nil               --返回空字符串，避免gsub函数输入nil而出现报错
        else
            local pattern = "[" .. table.concat(shield_words_correct_separators) .. "]"
            return string.gsub(str, pattern, "")
        end
    elseif is_banned_shield_words_correct == true then
        return str
    end
end

local function format_To_Decimal_Places(num)               --定义函数：给玩家余额保留[decimal_places]位小数
    local formatted = string.format("%."..decimal_places.."f", num)
    formatted = formatted:gsub("(%.[1-9]*)0+$", "%1")  -- 去除末尾多余的0
    formatted = formatted:gsub("%.$", "")  -- 如果只剩下小数点，去掉小数点
    return formatted
end

local player_input_list = {}

coromega:when_called_by_game_menu({               --建立游戏内菜单：即在游戏聊天栏内输入"商店","商城","商场","store","shop"等词可触发商店系统
    triggers = store_trigger_words,
    argument_hint = "",
    usage = store_usage,
})
:start_new(function(chat)
    local caller_name = chat.name               --获取正在使用商店的玩家名称
    local caller = coromega:get_player_by_name(caller_name)               --获取正在使用商店的玩家对象
    local caller_uuid = caller:uuid_string()               --获取正在使用商店的玩家uuid
    player_input_list[caller_uuid] = {}

    if is_banned_store_blacklist == false then
        if caller:check({"tag="..store_blacklist_tag_name}) == true then
            caller:say(messages.close_store.blacklist_info)
            do return end
        end
    end

    player_balance_db = nil

    if database_type == 2 then               --2:玩家余额信息存储在记分板

        omega.cmds.send_wo_cmd(("scoreboard objectives add \"%s\" dummy \"%s\""):format(coin_scoreboard_name,coin_scoreboard_display_name))               --若选用数据库类型为记分板，则创建记分板
        local caller_balance = tonumber(coromega:send_ws_cmd(("scoreboard players test \"%s\" \"%s\" * *"):format(caller_name, coin_scoreboard_name),true)["OutputMessages"][1]["Parameters"][1]) or 0
        player_balance_db = coromega:key_value_db(player_balance_db_name.."_记分板_临时存储数据库")               --创建并访问“玩家余额信息_记分板_临时存储数据库”数据库
        local has_balance_test = player_balance_db:get(caller_uuid)               --检测玩家有无“余额”数据，若无余额，将其余额设置为0，防止后续调用时出现空值(nil)而出现报错
        if not has_balance_test or has_balance_test == "" then
            player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=0,is_balance_rank=not(is_new_player_default_not_rank)})
            coromega:log(("玩家 %s (%s) 首次访问商店~"):format(caller_name,caller_uuid))
        end
        player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=caller_balance,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})

    elseif database_type == 1 then               --1:玩家余额信息存储在NeOmega的data数据库

        player_balance_db = coromega:key_value_db(player_balance_db_name)               --创建并访问“玩家余额信息”数据库
        local has_balance_test = player_balance_db:get(caller_uuid)               --检测玩家有无“余额”数据，若无余额，将其余额设置为0，防止后续调用时出现空值(nil)而出现报错
        if not has_balance_test or has_balance_test == "" then
            player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=0,is_balance_rank=not(is_new_player_default_not_rank)})
            coromega:log(("玩家 %s (%s) 首次访问商店~"):format(caller_name,caller_uuid))
        end

    end

    local player_transfer_db = coromega:key_value_db(player_transfer_db_name)               --创建并访问“玩家转账信息”数据库

    if player_balance_db:get(caller_uuid).is_balance_rank == nil then               --更新内容：玩家余额排行，给之前没有is_balance_rank项的玩家添加这一项
        local caller_balance = tonumber(player_balance_db:get(caller_uuid).caller_balance)
        player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=caller_balance,is_balance_rank=not(is_new_player_default_not_rank)})
    end

    if player_balance_db:get(caller_uuid).caller_name ~= caller_name then               --如果玩家改名了，同步修改其数据库中的名称
        local caller_balance = tonumber(player_balance_db:get(caller_uuid).caller_balance)
        coromega:log(("发现玩家 %s 改名为 %s (%s), 其账户余额: %s "..coin_name):format(player_balance_db:get(caller_uuid).caller_name,caller_name,caller_uuid,caller_balance))
        player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=caller_balance,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})
    end

    if player_balance_db:get(caller_uuid).caller_balance < 0 then               --如果玩家余额为负数(如超出长整型变量的上限导致余额溢出)，将余额设置为0，请放心，如果您的余额真的达到了2^31-1，我们会保留您的余额，这一条是为了防止记分板被人为扣分而出现负值
        player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=0,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})
    end

    if (player_balance_db:get(caller_uuid).caller_balance * 10 ^ max_decimal_places) % 1 ~= 0 then               --为防止余额过长，最多保留[max_decimal_places]位小数
        local caller_balance = tonumber(player_balance_db:get(caller_uuid).caller_balance)
        local formatted_caller_balance = string.format("%."..max_decimal_places.."f", caller_balance)
        local formatted_caller_balance = formatted_caller_balance:gsub("(%.[1-9]*)0+$", "%1")  -- 去除末尾多余的0
        local formatted_caller_balance = formatted_caller_balance:gsub("%.$", "")  -- 如果只剩下小数点，去掉小数点
        player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=tonumber(formatted_caller_balance),is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})
    end

    local resumable = coromega:get_resume()

    coromega:start_new(function()

        caller:say(hello_word)               --显示进入商店欢迎词

        player_input_list[caller_uuid].transfer_collection_project = {}               --[]行用于判断玩家是否收到转账信息，可跳过此部分直接阅读后续代码，转账系统本体的代码位于[]行
        player_input_list[caller_uuid].transfer_is_refused_and_wait_for_recycle_project = {}               --用于判断玩家是否存在被拒绝的转账

        player_transfer_db:iter(function(key, value)               --遍历转账数据库

            if value.transfer_target_player_uuid == caller_uuid and value.is_transfer_accepted == false then               --逐一判断uuid或名称是否匹配，is_transfer_accepted参数具有4种值(true:转账已领取;false:转账已发出但未领取;refuse:转账被拒收;withdraw:转账被撤回)
                player_input_list[caller_uuid].transfer_collection_project[key] = value
            elseif value.transfer_target_player_name == caller_name and value.is_transfer_accepted == false then
                player_input_list[caller_uuid].transfer_collection_project[key] = value
            end

            if value.transfer_orig_player_uuid == caller_uuid and value.is_transfer_accepted == "refuse_and_wait_for_recycle" then
                player_input_list[caller_uuid].transfer_is_refused_and_wait_for_recycle_project[key] = value
            end

            local next = true
            return next
        end)

        if next(player_input_list[caller_uuid].transfer_is_refused_and_wait_for_recycle_project) ~= nil then               --若发现玩家有被退回的转账，则执行下列代码；若玩家没有被退回的转账，直接跳过

            for key, value in pairs(player_input_list[caller_uuid].transfer_is_refused_and_wait_for_recycle_project) do

                coromega:send_wo_cmd(("playsound beacon.deactivate \"%s\""):format(caller_name))               --Minecraft音效指令
                coromega:send_wo_cmd(("playsound respawn_anchor.charge \"%s\""):format(caller_name))

                player_input_list[caller_uuid].caller_balance = tonumber(player_balance_db:get(caller_uuid).caller_balance)
                player_input_list[caller_uuid].transfer_balance = tonumber(value.transfer_balance)

                player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=player_input_list[caller_uuid].caller_balance+player_input_list[caller_uuid].transfer_balance,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})
                player_transfer_db:set(key,{transfer_orig_player_name=caller_name,transfer_orig_player_uuid=caller_uuid,transfer_target_player_name=value.transfer_target_player_name,transfer_target_player_uuid=value.transfer_target_player_uuid,transfer_balance=player_input_list[caller_uuid].transfer_balance,is_transfer_accepted="refuse_and_recycle_success"})
                coromega:log(("玩家 %s (%s) 转给 %s (%s) 的价值 %s "..coin_name.." 的转账被对方拒绝, 金额已原路退回"):format(caller_name,caller_uuid,value.transfer_target_player_name,value.transfer_target_player_uuid,player_input_list[caller_uuid].transfer_balance))

                caller:say(messages.receipt.refuse_transfer_receipt.top_framework)
                caller:say((messages.receipt.refuse_transfer_receipt.receipt_info):format(caller_name))
                caller:say(messages.receipt.refuse_transfer_receipt.condition)
                caller:say((messages.receipt.refuse_transfer_receipt.orig_player):format(caller_name))
                caller:say((messages.receipt.refuse_transfer_receipt.target_player):format(value.transfer_target_player_name))
                caller:say((messages.receipt.refuse_transfer_receipt.transfer_balance):format(player_input_list[caller_uuid].transfer_balance))
                caller:say((messages.receipt.refuse_transfer_receipt.balance_change):format(player_input_list[caller_uuid].caller_balance,player_input_list[caller_uuid].transfer_balance,player_input_list[caller_uuid].caller_balance+player_input_list[caller_uuid].transfer_balance))
                caller:say(messages.receipt.refuse_transfer_receipt.bottom_framework)

            end
        end

        if next(player_input_list[caller_uuid].transfer_collection_project) ~= nil then               --若发现玩家有未领取的转账，则执行下列代码；若玩家没有需要领取的转账，直接跳过

            for key, value in pairs(player_input_list[caller_uuid].transfer_collection_project) do               --遍历转账数据库

                coromega:send_wo_cmd(("playsound beacon.deactivate \"%s\""):format(caller_name))               --Minecraft音效指令
                coromega:send_wo_cmd(("playsound respawn_anchor.charge \"%s\""):format(caller_name))

                player_input_list[caller_uuid].caller_balance = tonumber(player_balance_db:get(caller_uuid).caller_balance)
                player_input_list[caller_uuid].transfer_balance = tonumber(value.transfer_balance)
                player_input_list[caller_uuid].get_balance_after_tax = player_input_list[caller_uuid].transfer_balance*(1-transfer_tax_rate)

                caller:say(messages.found_transfer.top_framework)
                caller:say((messages.found_transfer.info):format(value.transfer_orig_player_name,player_input_list[caller_uuid].transfer_balance))
                caller:say((messages.found_transfer.transfer_tax):format(transfer_tax_rate,player_input_list[caller_uuid].get_balance_after_tax))
                caller:say(messages.found_transfer.receive_balance)
                caller:say(messages.found_transfer.refuse_transfer)
                caller:say(messages.found_transfer.other_input)
                local input = caller:ask(messages.found_transfer.bottom_framework,input_timeout)               --给玩家显示转账信息

                if input == nil then               --回复超时自动退出
                    caller:say(messages.close_store.transfer_timeout)
                    resumable("Author style_stars") do return end
                elseif input == "y" then               --给目标玩家添加余额，将本条转账信息标记为“接受true”

                    player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=player_input_list[caller_uuid].caller_balance+player_input_list[caller_uuid].get_balance_after_tax,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})
                    player_transfer_db:set(key,{transfer_orig_player_name=value.transfer_orig_player_name,transfer_orig_player_uuid=value.transfer_orig_player_uuid,transfer_target_player_name=caller_name,transfer_target_player_uuid=caller_uuid,transfer_balance=player_input_list[caller_uuid].transfer_balance,is_transfer_accepted=true})
                    coromega:log(("玩家 %s (%s) 转给 %s (%s) 的价值 %s "..coin_name.." 的转账已被接受, 当前税率: %s, 实际收款金额: %s "..coin_name):format(value.transfer_orig_player_name,value.transfer_orig_player_uuid,caller_name,caller_uuid,player_input_list[caller_uuid].transfer_balance,transfer_tax_rate,player_input_list[caller_uuid].get_balance_after_tax))

                    caller:say(messages.receipt.receive_transfer_receipt.top_framework)
                    caller:say((messages.receipt.receive_transfer_receipt.receipt_info):format(caller_name))
                    caller:say(messages.receipt.receive_transfer_receipt.condition)
                    caller:say((messages.receipt.receive_transfer_receipt.orig_player):format(value.transfer_orig_player_name))
                    caller:say((messages.receipt.receive_transfer_receipt.target_player):format(caller_name))
                    caller:say((messages.receipt.receive_transfer_receipt.transfer_balance):format(player_input_list[caller_uuid].get_balance_after_tax))
                    caller:say((messages.receipt.receive_transfer_receipt.balance_change):format(player_input_list[caller_uuid].caller_balance,player_input_list[caller_uuid].get_balance_after_tax,player_input_list[caller_uuid].caller_balance+player_input_list[caller_uuid].get_balance_after_tax))
                    caller:say(messages.receipt.receive_transfer_receipt.bottom_framework)

                elseif input == "n" then               --将余额退回转账发出玩家，将本条转账信息标记为“拒绝refuse_and_wait_for_recycle”

                    player_transfer_db:set(key,{transfer_orig_player_name=value.transfer_orig_player_name,transfer_orig_player_uuid=value.transfer_orig_player_uuid,transfer_target_player_name=caller_name,transfer_target_player_uuid=caller_uuid,transfer_balance=player_input_list[caller_uuid].transfer_balance,is_transfer_accepted="refuse_and_wait_for_recycle"})
                    caller:say((messages.found_transfer.refuse_transfer2):format(value.transfer_orig_player_name))

                end
            end
        end

        player_input_list[caller_uuid] = {}

        while true do

            caller:say(messages.store_options.top_framework)               --显示商店一级页面
            caller:say(messages.store_options.sever_info)
            caller:say(messages.store_options.sell_store)
            caller:say(messages.store_options.buy_store)
            caller:say(messages.store_options.query_balance)
            caller:say(messages.store_options.transfer_balance)
            caller:say(messages.store_options.balance_rank)
            caller:say(messages.store_options.bottom_framework)
            caller:say(messages.store_options.choose_option)
            local input = caller:ask(messages.store_options.leave_store,input_timeout)

            if input == nil then               --超过1分钟不回复自动退出

                caller:say(messages.close_store.timeout)

                resumable("Author style_stars") do return end

            elseif input == "取消" then

                caller:say(messages.close_store.cancel)

                resumable("Author style_stars") do return end

            elseif input == "1" or input == "回收" or input == "回收商店" then

                if is_banned_sell_store == true then
                    caller:say(messages.close_store.not_sell_store)
                    resumable("Author style_stars") do return end
                end

                pairs_test = nil
                skip_display = nil
                caller_inventory_item_number = nil

                player_input_list[caller_uuid].page = 1

                while true do

                    player_input_list[caller_uuid].sell_results = {}               --获取回收物品的表对象，方便后续遍历显示和商店栏目翻页
                    for key,value in pairs(total_sell_goods) do
                        table.insert(player_input_list[caller_uuid].sell_results, value)
                    end

                    player_input_list[caller_uuid].total_pages = math.ceil(#player_input_list[caller_uuid].sell_results / sell_items_per_page)               --计算页码相关参数
                    local start_index = (player_input_list[caller_uuid].page - 1) * sell_items_per_page + 1
                    local end_index = math.min(start_index + sell_items_per_page - 1, #player_input_list[caller_uuid].sell_results)

                    if skip_display ~= true then

                        caller:say(messages.sell_store_options.top_framework)               --显示可回收物品信息
                        caller:say((messages.sell_store_options.info):format(#player_input_list[caller_uuid].sell_results,format_To_Decimal_Places(player_balance_db:get(caller_uuid).caller_balance)))
                        for i = start_index, end_index do
                            local item = player_input_list[caller_uuid].sell_results[i]
                            caller:say((messages.sell_store_options.item_value):format(item.index,item.color_code,item.cnitem,format_To_Decimal_Places(item.value*sell_store_rate)))
                        end
                        caller:say(messages.sell_store_options.middle_framework)
                        caller:say((messages.sell_store_options.pages):format(player_input_list[caller_uuid].page,player_input_list[caller_uuid].total_pages))
                        caller:say((messages.sell_store_options.input_cnitem_or_number):format(#player_input_list[caller_uuid].sell_results))
                        caller:say(messages.sell_store_options.pre_page)
                        caller:say(messages.sell_store_options.next_page)
                        caller:say(messages.sell_store_options.change_page)
                        caller:say(messages.sell_store_options.leave_store)
                        caller:say(messages.sell_store_options.bottom_framework)

                    end

                    player_input_list[caller_uuid].sell_store_options = remove_Separator(caller:ask(messages.sell_store_options.input,input_timeout))               --获取玩家输入（物品名称/物品序号）
                    if player_input_list[caller_uuid].sell_store_options == nil then               --超过1分钟不回复自动退出
                        caller:say(messages.close_store.timeout)
                        resumable("Author style_stars") do return end
                    elseif player_input_list[caller_uuid].sell_store_options == "取消" then               --输入取消退出商店
                        caller:say(messages.close_store.cancel)
                        resumable("Author style_stars") do return end
                    elseif player_input_list[caller_uuid].sell_store_options == "***" and is_banned_shield_words_correct == false then               --输入屏蔽词触发屏蔽词校正功能
                        caller:say(messages.shield_words_correct.info1)
                        caller:say((messages.shield_words_correct.info2):format(shield_words_correct_separators[1],shield_words_correct_separators[1]))
                        skip_display = true
                    elseif player_input_list[caller_uuid].sell_store_options == "Pre" or player_input_list[caller_uuid].sell_store_options == "Pr" or player_input_list[caller_uuid].sell_store_options == "P" or player_input_list[caller_uuid].sell_store_options == "pre" or player_input_list[caller_uuid].sell_store_options == "pr" or player_input_list[caller_uuid].sell_store_options == "p" then
                        if player_input_list[caller_uuid].page > 1 then               --翻到上一页
                            player_input_list[caller_uuid].page = player_input_list[caller_uuid].page - 1
                            skip_display = nil
                        else
                            caller:say(messages.sell_store_options.is_first_page)
                            skip_display = true
                        end
                    elseif player_input_list[caller_uuid].sell_store_options == "Next" or player_input_list[caller_uuid].sell_store_options == "Nex" or player_input_list[caller_uuid].sell_store_options == "Ne" or player_input_list[caller_uuid].sell_store_options == "N" or player_input_list[caller_uuid].sell_store_options == "next" or player_input_list[caller_uuid].sell_store_options == "nex" or player_input_list[caller_uuid].sell_store_options == "ne" or player_input_list[caller_uuid].sell_store_options == "n" then
                        if player_input_list[caller_uuid].page < player_input_list[caller_uuid].total_pages then               --翻到下一页
                            player_input_list[caller_uuid].page = player_input_list[caller_uuid].page + 1
                            skip_display = nil
                        else
                            caller:say(messages.sell_store_options.is_final_page)
                            skip_display = true
                        end
                    elseif is_Number_Page(player_input_list[caller_uuid].sell_store_options) == true then
                        local input_page = tonumber(string.match(player_input_list[caller_uuid].sell_store_options, "^(%d+)页$"))               --翻任意页
                        if input_page >= 1 and input_page <= player_input_list[caller_uuid].total_pages then
                            player_input_list[caller_uuid].page = input_page
                            skip_display = nil
                        else
                            caller:say((messages.sell_store_options.page_not_exist):format(input_page))
                            skip_display = true
                        end
                    else
                        for key,value in pairs(total_sell_goods) do               --如果玩家输入物品序号，获取物品相关信息
                            if player_input_list[caller_uuid].sell_store_options == value.index then
                                player_input_list[caller_uuid].sell_cnitem = value.cnitem
                                player_input_list[caller_uuid].sell_item = value.item
                                player_input_list[caller_uuid].sell_data = value.data
                                player_input_list[caller_uuid].sell_value = value.value
                                player_input_list[caller_uuid].sell_index = value.index
                                pairs_test = true
                                break
                            elseif player_input_list[caller_uuid].sell_store_options == value.cnitem then               --如果玩家输入物品中文名称，同样也可获取物品相关信息
                                player_input_list[caller_uuid].sell_cnitem = value.cnitem
                                player_input_list[caller_uuid].sell_item = value.item
                                player_input_list[caller_uuid].sell_data = value.data
                                player_input_list[caller_uuid].sell_value = value.value
                                player_input_list[caller_uuid].sell_index = value.index
                                pairs_test = true
                                break
                            end
                        end
                        if pairs_test == true then               --成功获取物品信息后跳出while循环
                            break
                        else
                            caller:say(messages.sell_store_options.input_err)               --无法识别玩家输入，重新进入while循环
                            skip_display = true
                        end
                    end
                end

                while true do
                    caller:say((messages.sell_store_options.sell_number):format(player_input_list[caller_uuid].sell_cnitem,format_To_Decimal_Places(player_input_list[caller_uuid].sell_value*sell_store_rate),player_input_list[caller_uuid].sell_index))
                    player_input_list[caller_uuid].sell_number = remove_Separator(caller:ask(messages.sell_store_options.leave_store2,input_timeout))               --获取玩家输入（物品数量）
                    if player_input_list[caller_uuid].sell_number == nil then
                        caller:say(messages.close_store.timeout)
                        resumable("Author style_stars") do return end
                    elseif player_input_list[caller_uuid].sell_number == "取消" then
                        caller:say(messages.close_store.cancel)
                        resumable("Author style_stars") do return end
                    elseif player_input_list[caller_uuid].sell_number == "***" and is_banned_shield_words_correct == false then               --输入屏蔽词触发屏蔽词校正功能
                        caller:say(messages.shield_words_correct.info1)
                        caller:say((messages.shield_words_correct.info2):format(shield_words_correct_separators[1],shield_words_correct_separators[1]))
                    elseif is_positive_integer(player_input_list[caller_uuid].sell_number) == true and tonumber(player_input_list[caller_uuid].sell_number) <= sell_max_num then               --必须是正整数且<=sell_max_num才能进入下一步
                        break
                    end
                        caller:say(messages.sell_store_options.input_err2)
                end

                local caller_inventory_item_number = coromega:send_ws_cmd(("clear \"%s\" %s %s 0"):format(caller_name,player_input_list[caller_uuid].sell_item,player_input_list[caller_uuid].sell_data),true)["OutputMessages"][1]["Parameters"][2]

                if is_positive_integer(caller_inventory_item_number) == true then
                    caller_inventory_item_number = tonumber(caller_inventory_item_number) / 2
                else
                    caller_inventory_item_number = 0
                end
                if caller_inventory_item_number >= tonumber(player_input_list[caller_uuid].sell_number) then
                    local get_coin = tonumber(player_input_list[caller_uuid].sell_value) * tonumber(player_input_list[caller_uuid].sell_number) * sell_store_rate              --单价x数量=获得的金额
                    local orig_coin = player_balance_db:get(caller_uuid).caller_balance               --获得原有余额
                    local total_coin = tonumber(orig_coin) + get_coin               --把新获得金额和原有余额加起来
                    player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=total_coin,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})               --修改玩家余额信息
                    coromega:log(("玩家 %s (%s) 回收了 %s个 %s (物品ID:%s , 数据值:%s , 单价:%s), 账户余额： %s + %s → %s"..coin_name):format(caller_name,caller_uuid,player_input_list[caller_uuid].sell_number,player_input_list[caller_uuid].sell_cnitem,player_input_list[caller_uuid].sell_item,player_input_list[caller_uuid].sell_data,player_input_list[caller_uuid].sell_value,orig_coin,get_coin,total_coin))
                    coromega:send_wo_cmd(("clear \"%s\" %s %s %s"):format(caller_name,player_input_list[caller_uuid].sell_item,player_input_list[caller_uuid].sell_data,player_input_list[caller_uuid].sell_number))               --清除对应物品

                    caller:say(messages.receipt.sell_store_receipt.top_framework)               --生成账单
                    caller:say((messages.receipt.sell_store_receipt.receipt_info):format(caller_name))
                    caller:say(messages.receipt.sell_store_receipt.type)
                    caller:say((messages.receipt.sell_store_receipt.item):format(player_input_list[caller_uuid].sell_cnitem))
                    caller:say((messages.receipt.sell_store_receipt.value):format(format_To_Decimal_Places(player_input_list[caller_uuid].sell_value*sell_store_rate)))
                    caller:say((messages.receipt.sell_store_receipt.number):format(player_input_list[caller_uuid].sell_number))
                    caller:say((messages.receipt.sell_store_receipt.balance_change):format(format_To_Decimal_Places(orig_coin),format_To_Decimal_Places(get_coin),format_To_Decimal_Places(total_coin)))
                    caller:say(messages.receipt.sell_store_receipt.bottom_framework)
                    caller:say(messages.receipt.sell_store_receipt.goodbye_word)

                    coromega:send_wo_cmd(("playsound beacon.deactivate \"%s\""):format(caller_name))               --Minecraft音效指令
                    coromega:send_wo_cmd(("playsound respawn_anchor.charge \"%s\""):format(caller_name))

                    if is_banned_sell_store_refund == true then
                        resumable("Author style_stars") do return end
                    end

                    caller:say((messages.receipt.sell_store_receipt.refund_word):format(sell_store_refund_time))
                    player_input_list[caller_uuid].sell_store_refund_input = caller:ask("",sell_store_refund_time)

                    if player_input_list[caller_uuid].sell_store_refund_input == "退款" then               --如果退款

                        local refund_spend_coin = tonumber(player_input_list[caller_uuid].sell_value) * tonumber(player_input_list[caller_uuid].sell_number) * sell_store_rate               --单价x数量=花费的金额
                        local refund_orig_coin = tonumber(player_balance_db:get(caller_uuid).caller_balance)               --获得退款时原有余额
                        if refund_spend_coin <= refund_orig_coin then               --余额足够才能退款
                            local refund_total_coin = refund_orig_coin - refund_spend_coin               --剩余余额=原有余额-花费的金额
                            player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=refund_total_coin,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})               --修改玩家余额信息
                            coromega:log(("玩家 %s (%s) 发出了退款, 账户余额： %s - %s → %s"..coin_name):format(caller_name,caller_uuid,refund_orig_coin,refund_spend_coin,refund_total_coin))
                            coromega:send_wo_cmd(("give \"%s\" %s %s %s"):format(caller_name,player_input_list[caller_uuid].sell_item,player_input_list[caller_uuid].sell_number,player_input_list[caller_uuid].sell_data))               --给予玩家对应物品

                            caller:say(messages.receipt.sell_store_refund_receipt.top_framework)
                            caller:say((messages.receipt.sell_store_refund_receipt.receipt_info):format(caller_name))
                            caller:say(messages.receipt.sell_store_refund_receipt.type)
                            caller:say((messages.receipt.sell_store_refund_receipt.item):format(player_input_list[caller_uuid].sell_cnitem))
                            caller:say((messages.receipt.sell_store_refund_receipt.value):format(format_To_Decimal_Places(player_input_list[caller_uuid].sell_value*sell_store_rate)))
                            caller:say((messages.receipt.sell_store_refund_receipt.number):format(player_input_list[caller_uuid].sell_number))
                            caller:say((messages.receipt.sell_store_refund_receipt.balance_change):format(format_To_Decimal_Places(refund_orig_coin),format_To_Decimal_Places(refund_spend_coin),format_To_Decimal_Places(refund_total_coin)))
                            caller:say(messages.receipt.sell_store_refund_receipt.bottom_framework)
                            caller:say(messages.receipt.sell_store_refund_receipt.goodbye_word)

                        else
                            caller:say((messages.receipt.sell_store_refund_receipt.balance_not_enough):format(refund_spend_coin))               --余额不足提示
                            coromega:send_wo_cmd(("playsound respawn_anchor.deplete \"%s\""):format(caller_name))
                        end

                    else
                        caller:say(messages.receipt.sell_store_refund_receipt.goodbye_word)
                    end

                else
                    caller:say((messages.sell_store_options.item_not_enough):format(player_input_list[caller_uuid].sell_cnitem,player_input_list[caller_uuid].sell_number))               --物品数量不足显示
                    coromega:send_wo_cmd(("playsound respawn_anchor.deplete \"%s\""):format(caller_name))
                end

                player_input_list[caller_uuid] = {}
                resumable("Author style_stars") do return end

            elseif input == "2" or input == "购买" or input == "购买商店" then

                if is_banned_buy_store == true then
                    caller:say(messages.close_store.not_buy_store)
                    resumable("Author style_stars") do return end
                end

                skip_display = nil
                refund_caller_inventory_item_number = nil

                while true do

                    caller:say(messages.buy_store_front.top_framework)               --显示页面
                    caller:say(messages.buy_store_front.info)
                    caller:say(messages.buy_store_front.input_cnitem)
                    caller:say(messages.buy_store_front.input_number)
                    caller:say(messages.buy_store_front.leave_store)
                    player_input_list[caller_uuid].buy_cnitem_search = remove_Separator(caller:ask(messages.buy_store_front.bottom_framework,input_timeout))

                    if player_input_list[caller_uuid].buy_cnitem_search == nil then
                        caller:say(messages.close_store.timeout)
                        resumable("Author style_stars") do return end
                    elseif player_input_list[caller_uuid].buy_cnitem_search == "取消" then
                        caller:say(messages.close_store.cancel)
                        resumable("Author style_stars") do return end
                    elseif player_input_list[caller_uuid].buy_cnitem_search == "***" and is_banned_shield_words_correct == false then               --输入屏蔽词触发屏蔽词校正功能
                        caller:say(messages.shield_words_correct.info1)
                        caller:say((messages.shield_words_correct.info2):format(shield_words_correct_separators[1],shield_words_correct_separators[1]))
                    else
                        break
                    end

                end

                player_input_list[caller_uuid].page = 1               --先在while循环外面定义页码为1，等一下默认显示的就是第1页

                while true do

                    player_input_list[caller_uuid].search_results = {}
                    for key, value in pairs(total_buy_goods) do
                        if player_input_list[caller_uuid].buy_cnitem_search == value.index then               --如果玩家直接输入了商品编号，跳过商品显示，直接到下一步输入商品数量，商品的编号是固定的，这一步是为了方便记得编号的玩家跳过搜索直接购买商品
                            if tonumber(value.value) ~= nil then               --当商品的value值是正数时才可购买，如果是0，则免费赠送，如果是“暂不出售”等任意字符或者其他任何负数都不能购买
                                if is_Positive_Number(value.value*buy_store_rate) == true or value.value*buy_store_rate == 0 then
                                    player_input_list[caller_uuid].search_result = value
                                end
                            else
                                caller:say((messages.buy_store_options.item_not_sell):format(value.cnitem,value.index))               --暂不出售的物品不能购买（比如基岩、末地传送门框架等）
                                resumable("Author style_stars") do return end
                            end
                        elseif string.find(value.cnitem, player_input_list[caller_uuid].buy_cnitem_search) then               --如果玩家输入的是物品中文名称，根据输入词进行模糊搜索，加入表中
                            table.insert(player_input_list[caller_uuid].search_results, value)
                        end
                    end

                    if player_input_list[caller_uuid].search_result == nil then               --如果玩家直接输入了商品编号，跳过商品显示，直接到下一步输入商品数量，商品的编号是固定的，这一步是为了方便记得编号的玩家跳过搜索直接购买商品

                        if #player_input_list[caller_uuid].search_results > 0 then               --如果能搜到物品，也就是表内对象数量>0
                            player_input_list[caller_uuid].total_pages = math.ceil(#player_input_list[caller_uuid].search_results / buy_items_per_page)               --计算页码相关参数
                            local start_index = (player_input_list[caller_uuid].page - 1) * buy_items_per_page + 1
                            local end_index = math.min(start_index + buy_items_per_page - 1, #player_input_list[caller_uuid].search_results)

                            if skip_display ~= true then               --这个是用来跳过搜索页面显示的，再次搜索商品、上一页、下一页、跳转任意页是不跳过的；但出现“已经是第一页”“已经是最后一页”等报错提示时会自动跳过搜索显示，防止刷屏又显示一次一样的商品
                                caller:say(messages.buy_store_options.top_framework)               --显示搜索到的商品
                                caller:say((messages.buy_store_options.info):format(#player_input_list[caller_uuid].search_results,format_To_Decimal_Places(player_balance_db:get(caller_uuid).caller_balance)))
                                for i = start_index, end_index do
                                    local item = player_input_list[caller_uuid].search_results[i]
                                    if tonumber(item.value) ~= nil then
                                        caller:say((messages.buy_store_options.item_value):format(item.index,item.cnitem,format_To_Decimal_Places(item.value*buy_store_rate)))
                                    else
                                        caller:say((messages.buy_store_options.item_value):format(item.index,item.cnitem,item.value))
                                    end
                                end
                                caller:say(messages.buy_store_options.middle_framework)
                                caller:say((messages.buy_store_options.pages):format(player_input_list[caller_uuid].page,player_input_list[caller_uuid].total_pages))
                                caller:say(messages.buy_store_options.input_number)
                                caller:say(messages.buy_store_options.input_cnitem)
                                caller:say(messages.buy_store_options.pre_page)
                                caller:say(messages.buy_store_options.next_page)
                                caller:say(messages.buy_store_options.change_page)
                                caller:say(messages.buy_store_options.leave_store)
                                caller:say(messages.buy_store_options.bottom_framework)
                            end
                            player_input_list[caller_uuid].buy_store_options = remove_Separator(caller:ask(messages.buy_store_options.input,input_timeout))               --获取玩家输入（物品名称/物品序号）
                            if player_input_list[caller_uuid].buy_store_options == nil then
                                caller:say(messages.close_store.timeout)
                                resumable("Author style_stars") do return end
                            elseif player_input_list[caller_uuid].buy_store_options == "取消" then
                                caller:say(messages.close_store.cancel)
                                resumable("Author style_stars") do return end
                            elseif player_input_list[caller_uuid].buy_store_options == "***" and is_banned_shield_words_correct == false then               --输入屏蔽词触发屏蔽词校正功能
                                caller:say(messages.shield_words_correct.info1)
                                caller:say((messages.shield_words_correct.info2):format(shield_words_correct_separators[1],shield_words_correct_separators[1]))
                                skip_display = true
                            elseif player_input_list[caller_uuid].buy_store_options == "Pre" or player_input_list[caller_uuid].buy_store_options == "Pr" or player_input_list[caller_uuid].buy_store_options == "P" or player_input_list[caller_uuid].buy_store_options == "pre" or player_input_list[caller_uuid].buy_store_options == "pr" or player_input_list[caller_uuid].buy_store_options == "p" then               --翻到上一页
                                if player_input_list[caller_uuid].page > 1 then
                                    player_input_list[caller_uuid].page = player_input_list[caller_uuid].page - 1
                                    skip_display = nil
                                else
                                    caller:say(messages.buy_store_options.is_first_page)
                                    skip_display = true
                                end
                            elseif player_input_list[caller_uuid].buy_store_options == "Next" or player_input_list[caller_uuid].buy_store_options == "Nex" or player_input_list[caller_uuid].buy_store_options == "Ne" or player_input_list[caller_uuid].buy_store_options == "N" or player_input_list[caller_uuid].buy_store_options == "next" or player_input_list[caller_uuid].buy_store_options == "nex" or player_input_list[caller_uuid].buy_store_options == "ne" or player_input_list[caller_uuid].buy_store_options == "n" then               --翻到下一页
                                if player_input_list[caller_uuid].page < player_input_list[caller_uuid].total_pages then
                                    player_input_list[caller_uuid].page = player_input_list[caller_uuid].page + 1
                                    skip_display = nil
                                else
                                    caller:say(messages.buy_store_options.is_final_page)
                                    skip_display = true
                                end
                            elseif is_Number_Page(player_input_list[caller_uuid].buy_store_options) == true then
                                local input_page = tonumber(string.match(player_input_list[caller_uuid].buy_store_options, "^(%d+)页$"))               --翻到任意页
                                if input_page >= 1 and input_page <= player_input_list[caller_uuid].total_pages then
                                    player_input_list[caller_uuid].page = input_page
                                    skip_display = nil
                                else
                                    caller:say((messages.buy_store_options.page_not_exist):format(input_page))
                                    skip_display = true
                                end
                            else
                                player_input_list[caller_uuid].buy_cnitem_search = player_input_list[caller_uuid].buy_store_options               --如果输入商品中文名称，回到上面while循环再次搜索；如果输入商品编号，回到上面while循环检测商品编号的部分，跳过商品显示抵达下一步，这样设计代码是为了尽可能只遍历搜索一次就能获得结果，防止算力浪费，提升插件性能
                                player_input_list[caller_uuid].page = 1
                                skip_display = nil
                            end

                        else
                            caller:say(messages.buy_store_options.item_not_found)               --没找到物品的提示
                            resumable("Author style_stars") do return end
                        end

                    else

                        break

                    end

                end

                while true do
                    caller:say((messages.buy_store_options.buy_number):format(player_input_list[caller_uuid].search_result.cnitem,format_To_Decimal_Places(player_input_list[caller_uuid].search_result.value*buy_store_rate),player_input_list[caller_uuid].search_result.index))
                    player_input_list[caller_uuid].buy_number = remove_Separator(caller:ask(messages.buy_store_options.leave_store2,input_timeout))               --获取玩家输入（物品数量）
                    if player_input_list[caller_uuid].buy_number == nil then
                        caller:say(messages.close_store.timeout)
                        resumable("Author style_stars") do return end
                    elseif player_input_list[caller_uuid].buy_number == "取消" then
                        caller:say(messages.close_store.cancel)
                        resumable("Author style_stars") do return end
                    elseif player_input_list[caller_uuid].buy_number == "***" and is_banned_shield_words_correct == false then               --输入屏蔽词触发屏蔽词校正功能
                        caller:say(messages.shield_words_correct.info1)
                        caller:say((messages.shield_words_correct.info2):format(shield_words_correct_separators[1],shield_words_correct_separators[1]))
                    elseif is_positive_integer(player_input_list[caller_uuid].buy_number) == true and tonumber(player_input_list[caller_uuid].buy_number) <= buy_max_num then               --必须是正整数且<=buy_max_num才能进入下一步
                        break
                    end
                        caller:say(messages.buy_store_options.input_err2)
                end

                local spend_coin = tonumber(player_input_list[caller_uuid].search_result.value) * tonumber(player_input_list[caller_uuid].buy_number) * buy_store_rate               --单价x数量=花费的金额
                local orig_coin = tonumber(player_balance_db:get(caller_uuid).caller_balance)               --获得原有余额
                if spend_coin <= orig_coin then               --余额足够才能购买
                    local total_coin = orig_coin - spend_coin               --剩余余额=原有余额-花费的金额
                    player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=total_coin,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})               --修改玩家余额信息
                    coromega:log(("玩家 %s (%s) 购买了 %s个 %s (物品ID:%s , 数据值:%s , 单价:%s), 账户余额： %s - %s → %s"..coin_name):format(caller_name,caller_uuid,player_input_list[caller_uuid].buy_number,player_input_list[caller_uuid].search_result.cnitem,player_input_list[caller_uuid].search_result.item,player_input_list[caller_uuid].search_result.data,player_input_list[caller_uuid].search_result.value,orig_coin,spend_coin,total_coin))
                    coromega:send_wo_cmd(("give \"%s\" %s %s %s"):format(caller_name,player_input_list[caller_uuid].search_result.item,player_input_list[caller_uuid].buy_number,player_input_list[caller_uuid].search_result.data))               --给予玩家对应物品

                    caller:say(messages.receipt.buy_store_receipt.top_framework)               --生成账单
                    caller:say((messages.receipt.buy_store_receipt.receipt_info):format(caller_name))
                    caller:say(messages.receipt.buy_store_receipt.type)
                    caller:say((messages.receipt.buy_store_receipt.item):format(player_input_list[caller_uuid].search_result.cnitem))
                    caller:say((messages.receipt.buy_store_receipt.value):format(format_To_Decimal_Places(player_input_list[caller_uuid].search_result.value*buy_store_rate)))
                    caller:say((messages.receipt.buy_store_receipt.number):format(player_input_list[caller_uuid].buy_number))
                    caller:say((messages.receipt.buy_store_receipt.balance_change):format(format_To_Decimal_Places(orig_coin),format_To_Decimal_Places(spend_coin),format_To_Decimal_Places(total_coin)))
                    caller:say(messages.receipt.buy_store_receipt.bottom_framework)
                    caller:say(messages.receipt.buy_store_receipt.goodbye_word)

                    coromega:send_wo_cmd(("playsound beacon.deactivate \"%s\""):format(caller_name))               --Minecraft音效指令
                    coromega:send_wo_cmd(("playsound respawn_anchor.charge \"%s\""):format(caller_name))

                    if is_banned_buy_store_refund == true then
                        resumable("Author style_stars") do return end
                    end

                    caller:say((messages.receipt.buy_store_receipt.refund_word):format(buy_store_refund_time))
                    player_input_list[caller_uuid].buy_store_refund_input = caller:ask("",buy_store_refund_time)

                    if player_input_list[caller_uuid].buy_store_refund_input == "退款" then              --如果退款

                        local refund_caller_inventory_item_number = coromega:send_ws_cmd(("clear \"%s\" %s %s 0"):format(caller_name,player_input_list[caller_uuid].search_result.item,player_input_list[caller_uuid].search_result.data),true)["OutputMessages"][1]["Parameters"][2]

                        if is_positive_integer(refund_caller_inventory_item_number) == true then
                            refund_caller_inventory_item_number = tonumber(refund_caller_inventory_item_number) / 2
                        else
                            refund_caller_inventory_item_number = 0
                        end
                        if refund_caller_inventory_item_number >= tonumber(player_input_list[caller_uuid].buy_number) then
                            local refund_get_coin = tonumber(player_input_list[caller_uuid].search_result.value) * tonumber(player_input_list[caller_uuid].buy_number) * buy_store_rate              --单价x数量=获得的金额
                            local refund_orig_coin = player_balance_db:get(caller_uuid).caller_balance               --获得原有余额
                            local refund_total_coin = tonumber(refund_orig_coin) + refund_get_coin               --把新获得金额和原有余额加起来
                            player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=refund_total_coin,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})               --修改玩家余额信息
                            coromega:log(("玩家 %s (%s) 发出了退款, 账户余额： %s + %s → %s"..coin_name):format(caller_name,caller_uuid,refund_orig_coin,refund_get_coin,refund_total_coin))
                            coromega:send_wo_cmd(("clear \"%s\" %s %s %s"):format(caller_name,player_input_list[caller_uuid].search_result.item,player_input_list[caller_uuid].search_result.data,player_input_list[caller_uuid].buy_number))               --清除对应物品

                            caller:say(messages.receipt.buy_store_refund_receipt.top_framework)
                            caller:say((messages.receipt.buy_store_refund_receipt.receipt_info):format(caller_name))
                            caller:say(messages.receipt.buy_store_refund_receipt.type)
                            caller:say((messages.receipt.buy_store_refund_receipt.item):format(player_input_list[caller_uuid].search_result.cnitem))
                            caller:say((messages.receipt.buy_store_refund_receipt.value):format(format_To_Decimal_Places(player_input_list[caller_uuid].search_result.value*buy_store_rate)))
                            caller:say((messages.receipt.buy_store_refund_receipt.number):format(player_input_list[caller_uuid].buy_number))
                            caller:say((messages.receipt.buy_store_refund_receipt.balance_change):format(format_To_Decimal_Places(refund_orig_coin),format_To_Decimal_Places(refund_get_coin),format_To_Decimal_Places(refund_total_coin)))
                            caller:say(messages.receipt.buy_store_refund_receipt.bottom_framework)
                            caller:say(messages.receipt.buy_store_refund_receipt.goodbye_word)

                        else
                            caller:say((messages.receipt.buy_store_refund_receipt.item_not_enough):format(player_input_list[caller_uuid].search_result.cnitem,player_input_list[caller_uuid].buy_number))               --物品数量不足显示
                            coromega:send_wo_cmd(("playsound respawn_anchor.deplete \"%s\""):format(caller_name))
                        end

                    else
                        caller:say(messages.receipt.buy_store_refund_receipt.goodbye_word)
                    end

                else
                    caller:say((messages.buy_store_options.balance_not_enough):format(spend_coin))               --余额不足提示
                    coromega:send_wo_cmd(("playsound respawn_anchor.deplete \"%s\""):format(caller_name))
                end

                player_input_list[caller_uuid] = {}
                resumable("Author style_stars") do return end

            elseif input == "3" or input == "余额" or input == "查询余额" then

                if is_banned_query_balance == true then
                    caller:say(messages.close_store.not_query_balance)
                    resumable("Author style_stars") do return end
                end

                caller:say(messages.query_balance.top_framework)               --查询玩家余额
                caller:say((messages.query_balance.hello_word):format(caller_name))
                caller:say((messages.query_balance.info):format(format_To_Decimal_Places(player_balance_db:get(caller_uuid).caller_balance)))
                caller:say(messages.query_balance.bottom_framework)
                coromega:send_wo_cmd(("playsound beacon.deactivate \"%s\""):format(caller_name))               --Minecraft音效指令
                coromega:send_wo_cmd(("playsound respawn_anchor.charge \"%s\""):format(caller_name))

                resumable("Author style_stars") do return end

            elseif input == "4" or input == "转账" or input == "转账系统" then

                if is_banned_transfer_balance_system == true then
                    caller:say(messages.close_store.not_transfer_balance_system)
                    resumable("Author style_stars") do return end
                end

                transfer_target_player_name = nil
                transfer_target_player_uuid = nil
                transfer_balance = nil
                caller_balance = nil
                after_transfer_balance = nil
                withdraw_transfer_balance = nil
                transfer_index = nil
                index = nil
                transfer_project_test = nil

                while true do

                    caller:say(messages.transfer_balance_system.transfer_balance_system_options.top_framework)
                    caller:say(messages.transfer_balance_system.transfer_balance_system_options.initiate_transfer)
                    caller:say(messages.transfer_balance_system.transfer_balance_system_options.withdraw_transfer)
                    caller:say(messages.transfer_balance_system.transfer_balance_system_options.bottom_framework)
                    caller:say(messages.transfer_balance_system.transfer_balance_system_options.choose_option)
                    local input = caller:ask(messages.transfer_balance_system.transfer_balance_system_options.leave_store,input_timeout)

                    if input == nil then
                        caller:say(messages.close_store.timeout)
                        resumable("Author style_stars") do return end
                    elseif input == "取消" then
                        caller:say(messages.close_store.cancel)
                        resumable("Author style_stars") do return end

                    elseif input == "1" or input == "发起" or input == "发起转账" then

                        if is_banned_initiate_transfer == true then
                            caller:say(messages.close_store.not_initiate_transfer)
                            resumable("Author style_stars") do return end
                        end

                        caller:say(messages.transfer_balance_system.initiate_transfer_options.top_framework)
                        caller:say(messages.transfer_balance_system.initiate_transfer_options.info)
                        local candidates = coromega:get_all_online_players()
                        player_input_list[caller_uuid].selectable_candidates = {}
                        for i, candidate in pairs(candidates) do
                            local index = ("%s"):format(i)
                            local name = candidate:name()
                            local uuid = candidate:uuid_string()
                            player_input_list[caller_uuid].selectable_candidates[index] = {name=name,uuid=uuid}
                            caller:say((messages.transfer_balance_system.initiate_transfer_options.online_player_names):format(index,name))
                        end
                        caller:say(messages.transfer_balance_system.initiate_transfer_options.bottom_framework)
                        caller:say(messages.transfer_balance_system.initiate_transfer_options.if_player_offline)
                        local input = caller:ask(messages.transfer_balance_system.initiate_transfer_options.leave_store,input_timeout)

                        if input == nil then
                            caller:say(messages.close_store.timeout)
                            resumable("Author style_stars") do return end
                        elseif input == "取消" then
                            caller:say(messages.close_store.cancel)
                            resumable("Author style_stars") do return end
                        end

                        for key, value in pairs(player_input_list[caller_uuid].selectable_candidates) do
                            if input == key then
                                player_input_list[caller_uuid].transfer_target_player_name = value.name
                                player_input_list[caller_uuid].transfer_target_player_uuid = value.uuid
                                break
                            end
                        end

                        if player_input_list[caller_uuid].transfer_target_player_name == nil or player_input_list[caller_uuid].transfer_target_player_uuid == nil then
                            player_input_list[caller_uuid].transfer_target_player_name = input
                        end

                        while true do

                            caller:say((messages.transfer_balance_system.initiate_transfer_options.transfer_balance):format(player_input_list[caller_uuid].transfer_target_player_name,player_balance_db:get(caller_uuid).caller_balance))
                            transfer_balance = remove_Separator(caller:ask(messages.transfer_balance_system.initiate_transfer_options.leave_store2,input_timeout))

                            if transfer_balance == nil then
                                caller:say(messages.close_store.timeout)
                                resumable("Author style_stars") do return end
                            elseif transfer_balance == "取消" then
                                caller:say(messages.close_store.cancel)
                                resumable("Author style_stars") do return end
                            elseif transfer_balance == "***" and is_banned_shield_words_correct == false then               --输入屏蔽词触发屏蔽词校正功能
                                caller:say(messages.shield_words_correct.info1)
                                caller:say((messages.shield_words_correct.info2):format(shield_words_correct_separators[1],shield_words_correct_separators[1]))
                                caller:say(messages.transfer_balance_system.initiate_transfer_options.transfer_format_err)

                            elseif is_Positive_Number(transfer_balance) == true then
                                caller_balance = tonumber(player_balance_db:get(caller_uuid).caller_balance)
                                if tonumber(transfer_balance) <= caller_balance then
                                    after_transfer_balance = caller_balance - transfer_balance
                                    break
                                else
                                    caller:say((messages.transfer_balance_system.initiate_transfer_options.balance_not_enough):format(transfer_balance))
                                    resumable("Author style_stars") do return end
                                end
                            else
                                caller:say(messages.transfer_balance_system.initiate_transfer_options.transfer_format_err)
                            end

                        end

                        local player_transfer_db = coromega:key_value_db(player_transfer_db_name)

                        player_transfer_db_index = 0

                        player_transfer_db:iter(function(key, value)
                            player_transfer_db_index = math.max(player_transfer_db_index,tonumber(key))
                            local next = true
                            return next
                        end)

                        player_transfer_db_index = player_transfer_db_index + 1

                        player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=after_transfer_balance,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})
                        player_transfer_db:set(player_transfer_db_index,{transfer_orig_player_name=caller_name,transfer_orig_player_uuid=caller_uuid,transfer_target_player_name=player_input_list[caller_uuid].transfer_target_player_name,transfer_target_player_uuid=player_input_list[caller_uuid].transfer_target_player_uuid,transfer_balance=transfer_balance,is_transfer_accepted=false})
                        coromega:log(("玩家 %s (%s) 向 %s (%s) 发起了价值 %s "..coin_name.." 的转账"):format(caller_name,caller_uuid,player_input_list[caller_uuid].transfer_target_player_name,player_input_list[caller_uuid].transfer_target_player_uuid,transfer_balance))

                        caller:say(messages.receipt.initiate_transfer_receipt.top_framework)
                        caller:say((messages.receipt.initiate_transfer_receipt.receipt_info):format(caller_name))
                        caller:say(messages.receipt.initiate_transfer_receipt.condition)
                        caller:say((messages.receipt.initiate_transfer_receipt.orig_player):format(caller_name))
                        caller:say((messages.receipt.initiate_transfer_receipt.target_player):format(player_input_list[caller_uuid].transfer_target_player_name))
                        caller:say((messages.receipt.initiate_transfer_receipt.transfer_balance):format(transfer_balance))
                        caller:say((messages.receipt.initiate_transfer_receipt.balance_change):format(caller_balance,transfer_balance,after_transfer_balance))
                        caller:say(messages.receipt.initiate_transfer_receipt.bottom_framework)
                        caller:say(messages.receipt.initiate_transfer_receipt.tip)

                        coromega:send_wo_cmd(("playsound beacon.deactivate \"%s\""):format(caller_name))               --Minecraft音效指令
                        coromega:send_wo_cmd(("playsound respawn_anchor.charge \"%s\""):format(caller_name))

                        player_input_list[caller_uuid] = {}
                        resumable("Author style_stars") do return end

                    elseif input == "2" or input == "撤回" or input == "撤回转账" then

                        if is_banned_withdraw_transfer == true then
                            caller:say(messages.close_store.not_withdraw_transfer)
                            resumable("Author style_stars") do return end
                        end

                        player_input_list[caller_uuid].transfer_project = {}
                        player_input_list[caller_uuid].withdraw_transfer_index = 1
                        player_transfer_db:iter(function(key, value)
                            if value.transfer_orig_player_uuid == caller_uuid and value.is_transfer_accepted == false then
                                player_input_list[caller_uuid].transfer_project[player_input_list[caller_uuid].withdraw_transfer_index] = {key=key,value=value}
                                player_input_list[caller_uuid].withdraw_transfer_index = player_input_list[caller_uuid].withdraw_transfer_index + 1
                            end
                            local next = true
                            return next
                        end)

                        if next(player_input_list[caller_uuid].transfer_project) ~= nil then

                            caller:say(messages.transfer_balance_system.withdraw_transfer_options.top_framework)
                            caller:say(messages.transfer_balance_system.withdraw_transfer_options.info)
                            for key, value in pairs(player_input_list[caller_uuid].transfer_project) do
                                caller:say((messages.transfer_balance_system.withdraw_transfer_options.transfer_list):format(key,value.value.transfer_balance,value.value.transfer_target_player_name))
                            end
                            caller:say(messages.transfer_balance_system.withdraw_transfer_options.bottom_framework)

                            while true do

                                caller:say((messages.transfer_balance_system.withdraw_transfer_options.choose_option):format(player_input_list[caller_uuid].withdraw_transfer_index-1))
                                local input = remove_Separator(caller:ask(messages.transfer_balance_system.withdraw_transfer_options.leave_store,input_timeout))

                                if input == nil then
                                    caller:say(messages.close_store.timeout)
                                    resumable("Author style_stars") do return end
                                elseif input == "取消" then
                                    caller:say(messages.close_store.cancel)
                                    resumable("Author style_stars") do return end
                                elseif input == "***" and is_banned_shield_words_correct == false then               --输入屏蔽词触发屏蔽词校正功能
                                    caller:say(messages.shield_words_correct.info1)
                                    caller:say((messages.shield_words_correct.info2):format(shield_words_correct_separators[1],shield_words_correct_separators[1]))
                                end

                                for key, value in pairs(player_input_list[caller_uuid].transfer_project) do
                                    if input == tostring(key) then
                                        caller_balance = tonumber(player_balance_db:get(caller_uuid).caller_balance)
                                        transfer_balance = tonumber(value.value.transfer_balance)
                                        withdraw_transfer_balance = caller_balance + transfer_balance
                                        transfer_index = value.key
                                        transfer_target_player_name = value.value.transfer_target_player_name
                                        transfer_target_player_uuid = value.value.transfer_target_player_uuid
                                        transfer_project_test = true
                                        break
                                    end
                                end

                                if transfer_project_test == true then
                                    break
                                else
                                    caller:say(messages.transfer_balance_system.withdraw_transfer_options.input_err)
                                end

                            end

                            player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=withdraw_transfer_balance,is_balance_rank=player_balance_db:get(caller_uuid).is_balance_rank})
                            player_transfer_db:set(transfer_index,{transfer_orig_player_name=caller_name,transfer_orig_player_uuid=caller_uuid,transfer_target_player_name=transfer_target_player_name,transfer_target_player_uuid=transfer_target_player_uuid,transfer_balance=transfer_balance,is_transfer_accepted="withdraw"})
                            coromega:log(("玩家 %s (%s) 转给 %s (%s) 的价值 %s "..coin_name.." 的转账被撤回, 金额已原路退回"):format(caller_name,caller_uuid,transfer_target_player_name,transfer_target_player_uuid,transfer_balance))

                            caller:say(messages.receipt.withdraw_transfer_receipt.top_framework)
                            caller:say((messages.receipt.withdraw_transfer_receipt.receipt_info):format(caller_name))
                            caller:say(messages.receipt.withdraw_transfer_receipt.condition)
                            caller:say((messages.receipt.withdraw_transfer_receipt.orig_player):format(caller_name))
                            caller:say((messages.receipt.withdraw_transfer_receipt.target_player):format(transfer_target_player_name))
                            caller:say((messages.receipt.withdraw_transfer_receipt.transfer_balance):format(transfer_balance))
                            caller:say((messages.receipt.withdraw_transfer_receipt.balance_change):format(caller_balance,transfer_balance,withdraw_transfer_balance))
                            caller:say(messages.receipt.withdraw_transfer_receipt.bottom_framework)

                            coromega:send_wo_cmd(("playsound beacon.deactivate \"%s\""):format(caller_name))               --Minecraft音效指令
                            coromega:send_wo_cmd(("playsound respawn_anchor.charge \"%s\""):format(caller_name))

                            resumable("Author style_stars") do return end

                        else
                            caller:say(messages.transfer_balance_system.withdraw_transfer_options.transfer_not_found)
                            resumable("Author style_stars") do return end
                        end

                    else
                        caller:say(messages.transfer_balance_system.transfer_balance_system_options.input_err)
                    end

                end

                player_input_list[caller_uuid] = {}
                resumable("Author style_stars") do return end

            elseif input == "5" or input == "排行" or input == "余额排行" then

                if is_banned_player_balance_rank == true then
                    caller:say(messages.close_store.not_balance_rank)
                    resumable("Author style_stars") do return end
                end

                n = nil
                caller_rank = nil
                skip_display = nil

                player_input_list[caller_uuid].page = 1

                while true do

                    player_input_list[caller_uuid].rank_iter_results = {}               --获取玩家余额排行的表对象，方便后续遍历显示和翻页

                    player_balance_db:iter(function(key, value)
                        if value.is_balance_rank ~= false then
                            table.insert(player_input_list[caller_uuid].rank_iter_results, value)
                        end
                        local next = true
                        return next
                    end)

                    table.sort(player_input_list[caller_uuid].rank_iter_results, function(a, b) return a.caller_balance > b.caller_balance end)

                    player_input_list[caller_uuid].rank_results = {}

                    local n = 1
                    for i, v in ipairs(player_input_list[caller_uuid].rank_iter_results) do
                        if  n <= rank_max_num then
                            table.insert(player_input_list[caller_uuid].rank_results, v)
                            n = n + 1
                        end
                    end

                    player_input_list[caller_uuid].total_pages = math.ceil(#player_input_list[caller_uuid].rank_results / rank_players_per_page)               --计算页码相关参数
                    local start_index = (player_input_list[caller_uuid].page - 1) * rank_players_per_page + 1
                    local end_index = math.min(start_index + rank_players_per_page - 1, #player_input_list[caller_uuid].rank_results)

                    if skip_display ~= true then

                        caller:say(messages.balance_rank.top_framework)               --显示排行榜
                        if player_balance_db:get(caller_uuid).is_balance_rank == true then
                            caller:say((messages.balance_rank.info_yes):format(rank_players_per_page))
                            for i, v in ipairs(player_input_list[caller_uuid].rank_results) do
                                if v.caller_name == caller_name then
                                    caller_rank = i
                                end
                            end
                            local caller_balance = player_balance_db:get(caller_uuid).caller_balance
                            caller:say((messages.balance_rank.caller_balance_rank):format(caller_rank,caller_name,format_To_Decimal_Places(caller_balance)))
                            caller:say(messages.balance_rank.separator)
                        else
                            caller:say((messages.balance_rank.info_no):format(rank_players_per_page))
                        end
                        for i, v in ipairs(player_input_list[caller_uuid].rank_results) do
                            if i >= start_index and i <= end_index then
                                caller:say((messages.balance_rank.player_balance_rank):format(i,v.caller_name,format_To_Decimal_Places(v.caller_balance)))
                            end
                        end

                        caller:say(messages.balance_rank.middle_framework)
                        caller:say((messages.balance_rank.pages):format(player_input_list[caller_uuid].page,player_input_list[caller_uuid].total_pages))
                        caller:say(messages.balance_rank.rank_yes)
                        caller:say(messages.balance_rank.rank_no)
                        caller:say(messages.balance_rank.pre_page)
                        caller:say(messages.balance_rank.next_page)
                        caller:say(messages.balance_rank.change_page)
                        caller:say(messages.balance_rank.leave_store)
                        caller:say(messages.balance_rank.bottom_framework)

                    end

                    local input = caller:ask(messages.balance_rank.input,input_timeout)               --获取玩家输入
                    local caller_balance = player_balance_db:get(caller_uuid).caller_balance
                    if input == nil then               --超过1分钟不回复自动退出
                        caller:say(messages.close_store.timeout)
                        resumable("Author style_stars") do return end
                    elseif input == "取消" then               --输入取消退出排行榜
                        caller:say(messages.close_store.cancel)
                        resumable("Author style_stars") do return end
                    elseif input == "ry" or input == "RY" or input == "Ry" or input == "rY" or input == "参与" or input == "参加" or input == "参与排行" or input == "参与余额排行" then
                        player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=caller_balance,is_balance_rank=true})
                        caller:say(messages.balance_rank.rank_yes_success)
                        player_input_list[caller_uuid].page = 1
                        skip_display = nil
                    elseif input == "rn" or input == "RN" or input == "Rn" or input == "rN" or input == "退出" or input == "不参与" or input == "不参加" or input == "退出排行" or input == "退出余额排行" then
                        player_balance_db:set(caller_uuid,{caller_name=caller_name,caller_balance=caller_balance,is_balance_rank=false})
                        caller:say(messages.balance_rank.rank_no_success)
                        player_input_list[caller_uuid].page = 1
                        skip_display = nil
                    elseif input == "Pre" or input == "Pr" or input == "P" or input == "pre" or input == "pr" or input == "p" then
                        if player_input_list[caller_uuid].page > 1 then               --翻到上一页
                            player_input_list[caller_uuid].page = player_input_list[caller_uuid].page - 1
                            skip_display = nil
                        else
                            caller:say(messages.balance_rank.is_first_page)
                            skip_display = true
                        end
                    elseif input == "Next" or input == "Nex" or input == "Ne" or input == "N" or input == "next" or input == "nex" or input == "ne" or input == "n" then
                        if player_input_list[caller_uuid].page < player_input_list[caller_uuid].total_pages then               --翻到下一页
                            player_input_list[caller_uuid].page = player_input_list[caller_uuid].page + 1
                            skip_display = nil
                        else
                            caller:say(messages.balance_rank.is_final_page)
                            skip_display = true
                        end
                    elseif is_Number_Page(input) == true then
                        local input_page = tonumber(string.match(input, "^(%d+)页$"))               --翻任意页
                        if input_page >= 1 and input_page <= player_input_list[caller_uuid].total_pages then
                            player_input_list[caller_uuid].page = input_page
                            skip_display = nil
                        else
                            caller:say((messages.balance_rank.page_not_exist):format(input_page))
                            skip_display = true
                        end
                    else
                        caller:say(messages.balance_rank.input_other)
                        resumable("Author style_stars") do return end
                    end
                end

                player_input_list[caller_uuid] = {}
                resumable("Author style_stars") do return end

            else

                caller:say(messages.store_options.input_err)

            end

        end

    end)

    local ret = coromega:pause()               --使插件暂时在此中断，等待商店全部功能执行完毕，即等待resumable("Author style_stars") do return end被执行后，把玩家余额匹配给记分板

    if database_type == 2 then               --如果玩家余额信息存储在记分板，在插件的最后把临时数据库的余额数据匹配给记分板

        local caller_balance = tonumber(player_balance_db:get(caller_uuid).caller_balance)
        if caller_balance > 2 ^ 31 - 1 then               --如果玩家余额大于长整型变量的上限，则设置为长整型变量最大值
            coromega:send_ws_cmd(("scoreboard players set \"%s\" \"%s\" %s"):format(caller_name, coin_scoreboard_name, 2 ^ 31 - 1))
        else
            coromega:send_ws_cmd(("scoreboard players set \"%s\" \"%s\" %s"):format(caller_name, coin_scoreboard_name, math.floor(caller_balance)))
        end

    end

end)

coromega:run()
