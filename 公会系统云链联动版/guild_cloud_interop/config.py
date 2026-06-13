"""Runtime configuration loader for the guild plugin.

ToolDelta creates the runtime config file from DEFAULT_CONFIG when the
plugin is loaded. Do not ship a plugin-local ``plugin config`` directory.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from tooldelta import cfg, fmts


PLUGIN_ENABLED_KEY = "是否启用插件"

DEFAULT_CONFIG_JSON = (
    r'''{
    "配置版本":  "0.1.7",
    "动态载入设置":  {
                   "是否启用动态载入配置文件（仅用于本插件）":  true,
                   "动态载入检测时间间隔（单位：秒）":  5
               },
    "基础配置":  {
                 "是否启用插件":  false,
                 "公会菜单唤醒词":  [
                                    ".公会"
                                ],
                 "积分计分板名称":  "money",
                 "缓存有效时间秒":  300,
                 "批量保存间隔秒":  5,
                 "批量保存最大数量":  10
             },
    "功能开关":  {
                 "公会仓库":  true,
                 "公会据点":  true,
                 "公会捐献":  true,
                 "公会任务":  true,
                 "公会效果":  true,
                 "公会排行":  true
             },
    "公会配置":  {
                 "公会最大成员数":  30,
                 "在线成员每次增加经验":  10,
                 "在线经验增加间隔秒":  600,
                 "每日登录经验":  5,
                 "捐献转经验倍率":  0.1,
                 "每页显示数量":  6,
                 "公会各等级升级所需经验":  {
                                     "2":  100,
                                     "3":  200,
                                     "4":  400,
                                     "5":  800,
                                     "6":  1600,
                                     "7":  3200,
                                     "8":  6400,
                                     "9":  12800,
                                     "10":  25600
                                 }
             },
    "创建配置":  {
                 "创建公会消耗积分":  5000,
                 "创建冷却秒":  300,
                 "最短公会名长度":  2,
                 "最长公会名长度":  20,
                 "禁止公会名列表":  [
                                 "管理员",
                                 "系统",
                                 "官方"
                             ],
                 "禁止公会名包含词":  [
                                  "admin",
                                  "operator"
                              ],
                 "启用同名模糊检测":  true,
                 "模糊检测最小相似度":  0.88,
                 "创建后全服公告":  true
             },
    "仓库配置":  {
                 "初始容量":  54,
                 "每级增加容量":  0,
                 "交易税率":  0.05,
                 "市场配置":  {
                              "启用交易日志":  true,
                              "交易日志保留数量":  120,
                              "启用撤回出售":  true,
                              "只允许撤回自己的物品":  false,
                              "撤回后返还物品":  true,
                              "允许购买自己出售的物品":  false,
                              "单个成员最大上架数量":  18,
                              "单次出售最大数量":  64,
                              "单笔价格下限":  1,
                              "单笔价格上限":  100000,
                              "建议价最小倍率":  0.2,
                              "建议价最大倍率":  5.0,
                              "高价交易审计倍率":  3.0
                          }
             },
    "经验配置":  {
                 "在线经验":  {
                              "每次增加经验":  10,
                              "增加间隔秒":  600
                          },
                 "登录经验":  {
                              "每日登录经验":  5
                          },
                 "捐献经验":  {
                              "转经验倍率":  0.1
                          }
             },
    "据点配置":  {
                 "维度名称映射":  {
                                "0":  "主世界",
                                "1":  "地狱",
                                "2":  "末地"
                            }
             },
    "效果系统":  {
                 "刷新间隔秒":  3600,
                 "效果列表":  {
                              "speed":  {
                                            "name":  "速度提升",
                                            "levels":  {
                                                           "1":  1,
                                                           "2":  2
                                                       },
                                            "costs":  {
                                                          "1":  10,
                                                          "2":  20
                                                      }
                                        },
                              "haste":  {
                                            "name":  "急迫",
                                            "levels":  {
                                                           "1":  1,
                                                           "2":  2
                                                       },
                                            "costs":  {
                                                          "1":  10,
                                                          "2":  20
                                                      }
                                        },
                              "strength":  {
                                               "name":  "力量",
                                               "levels":  {
                                                              "1":  1,
                                                              "2":  2
                                                          },
                                               "costs":  {
                                                             "1":  10,
                                                             "2":  20
                                                         }
                                           },
                              "resistance":  {
                                                 "name":  "抗性提升",
                                                 "levels":  {
                                                                "1":  1,
                                                                "2":  2
                                                            },
                                                 "costs":  {
                                                               "1":  10,
                                                               "2":  20
                                                           }
                                             },
                              "regeneration":  {
                                                   "name":  "生命恢复",
                                                   "levels":  {
                                                                  "1":  1,
                                                                  "2":  2
                                                              },
                                                   "costs":  {
                                                                 "1":  10,
                                                                 "2":  20
                                                             }
                                               },
                              "night_vision":  {
                                                   "name":  "夜视",
                                                   "levels":  {
                                                                  "1":  1,
                                                                  "2":  2
                                                              },
                                                   "costs":  {
                                                                 "1":  10,
                                                                 "2":  20
                                                             }
                                               },
                              "jump_boost":  {
                                                 "name":  "跳跃提升",
                                                 "levels":  {
                                                                "1":  1,
                                                                "2":  2
                                                            },
                                                 "costs":  {
                                                               "1":  10,
                                                               "2":  20
                                                           }
                                             }
                          }
             },
    "申请配置":  {
                 "启用离线申请队列":  true,
                 "申请有效期秒":  86400,
                 "重复申请冷却秒":  300,
                 "每个玩家最多待处理申请数":  3,
                 "每个公会最多待处理申请数":  30,
                 "申请理由最大长度":  60,
                 "满员时自动拒绝新申请":  true,
                 "申请提交后通知在线管理员":  true,
                 "批准后通知全体在线成员":  true,
                 "拒绝后保留记录":  true
             },
    "任务系统":  {
                 "启用自动任务模板":  true,
                 "自动任务生成间隔秒":  86400,
                 "每次生成自动任务数量":  3,
                 "自动任务最大同时存在数量":  6,
                 "自动任务默认有效期秒":  172800,
                 "成员每日可完成任务数量":  5,
                 "创建任务名称最大长度":  20,
                 "创建任务描述最大长度":  100,
                 "创建任务目标数量上限":  10000,
                 "创建任务贡献奖励上限":  1000,
                 "创建任务经验奖励上限":  1000,
                 "自动任务模板列表":  [
                                  {
                                      "name":  "每日仓库交易",
                                      "description":  "完成一次公会仓库交易",
                                      "task_type":  "trade",
                                      "target":  "trade_count",
                                      "target_count":  1,
                                      "reward_exp":  30,
                                      "reward_contribution":  10
                                  },
                                  {
                                      "name":  "钻石补给",
                                      "description":  "收集钻石补给公会",
                                      "task_type":  "collect",
                                      "target":  "minecraft:diamond",
                                      "target_count":  8,
                                      "reward_exp":  80,
                                      "reward_contribution":  25
                                  },
                                  {
                                      "name":  "基础建材",
                                      "description":  "提交圆石作为公会建材",
                                      "task_type":  "collect",
                                      "target":  "minecraft:cobblestone",
                                      "target_count":  64,
                                      "reward_exp":  40,
                                      "reward_contribution":  12
                                  }
                              ]
             },
    "权限系统":  {
                 "职位权限配置":  {
                                "会长":  {
                                           "踢出成员权限":  true,
                                           "处理/同意加入公会申请权限":  true,
                                           "设置公会公告权限":  true,
                                           "管理公会任务权限":  true,
                                           "公会仓库使用权限":  true,
                                           "设置公会据点权限":  true,
                                           "返回公会据点权限":  true,
                                           "购买公会效果权限":  true,
                                           "设置仓库物品价值权限":  true,
                                           "出售仓库物品权限":  true,
                                           "购买仓库物品权限":  true,
                                           "撤回自己出售物品权限":  true,
                                           "撤回任意仓库物品权限":  true,
                                           "处理加入申请队列权限":  true,
                                           "查看审计日志权限":  true,
                                           "设置成员职位权限":  true,
                                           "转让会长权限":  true,
                                           "创建公会任务权限":  true,
                                           "删除公会任务权限":  true,
                                           "强制完成公会任务权限":  true
                                       },
                                "副会长":  {
                                            "踢出成员权限":  true,
                                            "处理/同意加入公会申请权限":  true,
                                            "设置公会公告权限":  true,
                                            "管理公会任务权限":  true,
                                            "公会仓库使用权限":  true,
                                            "设置公会据点权限":  false,
                                            "返回公会据点权限":  true,
                                            "购买公会效果权限":  true,
                                            "设置仓库物品价值权限":  true,
                                            "出售仓库物品权限":  true,
                                            "购买仓库物品权限":  true,
                                            "撤回自己出售物品权限":  true,
                                            "撤回任意仓库物品权限":  true,
                                            "处理加入申请队列权限":  true,
                                            "查看审计日志权限":  true,
                                            "设置成员职位权限":  true,
                                            "转让会长权限":  false,
                                            "创建公会任务权限":  true,
                                            "删除公会任务权限":  true,
                                            "强制完成公会任务权限":  true
                                        },
                                "长老":  {
                                           "踢出成员权限":  false,
                                           "处理/同意加入公会申请权限":  true,
                                           "设置公会公告权限":  true,
                                           "管理公会任务权限":  true,
                                           "公会仓库使用权限":  true,
                                           "设置公会据点权限":  false,
                                           "返回公会据点权限":  true,
                                           "购买公会效果权限":  true,
                                           "设置仓库物品价值权限":  false,
                                           "出售仓库物品权限":  true,
                                           "购买仓库物品权限":  true,
                                           "撤回自己出售物品权限":  true,
                                           "撤回任意仓库物品权限":  false,
                                           "处理加入申请队列权限":  true,
                                           "查看审计日志权限":  false,
                                           "设置成员职位权限":  false,
                                           "转让会长权限":  false,
                                           "创建公会任务权限":  true,
                                           "删除公会任务权限":  false,
                                           "强制完成公会任务权限":  false
                                       },
                                "成员":  {
                                           "踢出成员权限":  false,
                                           "处理/同意加入公会申请权限":  false,
                                           "设置公会公告权限":  false,
                                           "管理公会任务权限":  false,
                                           "公会仓库使用权限":  true,
                                           "设置公会据点权限":  false,
                                           "返回公会据点权限":  true,
                                           "购买公会效果权限":  false,
                                           "设置仓库物品价值权限":  false,
                                           "出售仓库物品权限":  true,
                                           "购买仓库物品权限":  true,
                                           "撤回自己出售物品权限":  true,
                                           "撤回任意仓库物品权限":  false,
                                           "处理加入申请队列权限":  false,
                                           "查看审计日志权限":  false,
                                           "设置成员职位权限":  false,
                                           "转让会长权限":  false,
                                           "创建公会任务权限":  false,
                                           "删除公会任务权限":  false,
                                           "强制完成公会任务权限":  false
                                       }
                            }
             },
    "数据安全":  {
                 "启用保存前备份":  true,
                 "备份目录名":  "公会数据备份",
                 "最大备份数量":  10,
                 "强制保存时也备份":  true,
                 "启用异常数据跳过":  true,
                 "启动时自动修复缺失字段":  true,
                 "修复前写入备份":  true,
                 "审计日志保留数量":  200
             },
    "提示词配置":  {
                  "已有公会提示词":  "§c❀ §r你已经有公会了",
                  "快捷创建缺少名称提示词":  "§a❀ §r请输入公会名称，例如: 公会创建 我的公会",
                  "快捷创建名称长度无效提示词":  "§c❀ §r公会名必须在2-16个字符之间",
'''
    r'''                  "创建公会余额不足提示词":  "§c❀ §r创建公会需要 '''
    r'''§e{consume}§r 点 §b{scoreboard}§r 计分板积分\n§c❀ §r当前余额: §f{balance}",
'''
    r'''                  "创建公会提示词":  "§a❀ §r创建公会将消耗 §e{consume} '''
    r'''§b{scoreboard} \n§a❀ §r当前余额: §f{balance}\n§a❀ §r输入 §a确认§7 继续创建，输入 §cq§7 取消",
'''
    r'''                  "创建公会回复超时提示词":  "§c❀ §r回复超时，已取消创建公会",
                  "创建公会取消提示词":  "§c❀ §r已取消创建公会",
                  "创建公会输入名称提示词":  "§a❀ §r请输入公会名字:\n§a❀ §r要求: 2-20个字符，不能包含特殊符号",
                  "创建公会名称无效提示词":  "§c❀ §r{error}",
                  "创建公会二次余额不足提示词": "§c❀ §r当前 §b{scoreboard}§r '''
    r'''余额不足，需要 §e{consume}§r，当前 §f{balance}",
                  "创建公会成功提示词":  "§a❀ §r已创建公会 §e{guild}",
                  "创建公会全服公告提示词":  "§a❀ §r§e{player}§r 创建了公会 §e{guild}§r！",
                  "创建公会名称已存在提示词":  "§c❀ §r该公会名已存在",
                  "菜单回复超时提示词":  "§c❀ §r回复超时！已退出公会系统",
                  "无效指令提示词":  "§c❀ §r无效的指令",
                  "通用分页为空提示词":  "§c❀ §r{title}为空",
                  "通用分页超时提示词":  "§c❀ §r操作超时",
                  "通用分页退出提示词":  "§a❀ §r已退出",
                  "通用分页无效选择提示词":  "§c❀ §r无效的选择",
                  "公会列表为空提示词":  "§c❀ §r公会列表为空",
                  "公会列表分页超时提示词":  "§c❀ §r操作超时",
                  "公会列表分页退出提示词":  "§a❀ §r已退出"
              },
    "功能列表配置":  {
                   "菜单标题":  "公会管理系统",
                   "游客身份显示":  "[§7游客§f]",
                   "成员身份显示模板":  "[{rank}§f] §e{guild}",
                   "输入数字提示模板":  "§a❀ §r输入 §e[1-{count}]§r 之间的数字选择功能",
                   "输入名称提示词":  "§a❀ §r也可输入功能名称，输入 §cq §r退出",
                   "基础功能":  {
                                "创建":  {
                                           "名称":  "创建",
                                           "描述":  "创建自己的公会"
                                       },
                                "列表":  {
                                           "名称":  "列表",
                                           "描述":  "查看所有公会"
                                       },
                                "查看":  {
                                           "名称":  "查看",
                                           "描述":  "查看公会详情"
                                       },
                                "成员":  {
                                           "名称":  "成员",
                                           "描述":  "查看成员列表"
                                       },
                                "日志":  {
                                           "名称":  "日志",
                                           "描述":  "查看公会日志"
                                       },
                                "公告":  {
                                           "名称":  "公告",
                                           "描述":  "查看/设置公告"
                                       },
                                "加入":  {
                                           "名称":  "加入",
                                           "描述":  "加入一个公会"
                                       },
                                "退出":  {
                                           "名称":  "退出",
                                           "描述":  "退出当前公会"
                                       },
                                "管理":  {
                                           "名称":  "管理",
                                           "描述":  "管理公会成员"
                                       },
                                "解散":  {
                                           "名称":  "解散",
                                           "描述":  "解散公会"
                                       }
                            },
                   "可选功能":  {
                                "仓库":  {
                                           "名称":  "仓库",
                                           "描述":  "公会仓库"
                                       },
                                "据点":  {
                                           "名称":  "据点",
                                           "描述":  "据点相关操作"
                                       },
                                "捐献":  {
                                           "名称":  "捐献",
                                           "描述":  "捐献物品到公会"
                                       },
                                "任务":  {
                                           "名称":  "任务",
                                           "描述":  "公会任务系统"
                                       },
                                "效果":  {
                                           "名称":  "效果",
                                           "描述":  "通过钻石获得效果增益"
                                       },
                                "排行":  {
                                           "名称":  "排行",
                                           "描述":  "查看公会排行榜"
                                       }
                            }
               },
    "经济系统":  {
                 "默认物品价值":  {
                                "minecraft:diamond":  50,
                                "minecraft:emerald":  25,
                                "minecraft:gold_ingot":  10,
                                "minecraft:iron_ingot":  5,
                                "minecraft:copper_ingot":  2,
                                "minecraft:coal":  1,
                                "minecraft:redstone":  2,
                                "minecraft:lapis_lazuli":  3,
                                "minecraft:quartz":  2,
                                "minecraft:netherite_ingot":  200,
                                "minecraft:ancient_debris":  150,
                                "minecraft:ender_pearl":  20,
                                "minecraft:blaze_rod":  15,
                                "minecraft:ghast_tear":  25,
                                "minecraft:shulker_shell":  100,
                                "minecraft:nautilus_shell":  30,
                                "minecraft:heart_of_the_sea":  150,
                                "minecraft:stone":  1,
                                "minecraft:cobblestone":  1,
                                "minecraft:dirt":  1,
                                "minecraft:sand":  1,
                                "minecraft:gravel":  1,
                                "minecraft:obsidian":  10,
                                "minecraft:crying_obsidian":  15,
                                "minecraft:netherrack":  1,
                                "minecraft:end_stone":  5,
                                "minecraft:oak_log":  2,
                                "minecraft:birch_log":  2,
                                "minecraft:spruce_log":  2,
                                "minecraft:jungle_log":  2,
                                "minecraft:acacia_log":  2,
                                "minecraft:dark_oak_log":  2,
                                "minecraft:oak_planks":  1,
                                "minecraft:birch_planks":  1,
                                "minecraft:spruce_planks":  1,
                                "minecraft:jungle_planks":  1,
                                "minecraft:acacia_planks":  1,
                                "minecraft:dark_oak_planks":  1,
                                "minecraft:apple":  2,
                                "minecraft:golden_apple":  20,
                                "minecraft:enchanted_golden_apple":  100,
                                "minecraft:bread":  3,
                                "minecraft:beef":  3,
                                "minecraft:cooked_beef":  5,
                                "minecraft:porkchop":  3,
                                "minecraft:cooked_porkchop":  5,
                                "minecraft:chicken":  2,
                                "minecraft:cooked_chicken":  4,
                                "minecraft:cod":  2,
                                "minecraft:cooked_cod":  4,
                                "minecraft:salmon":  3,
                                "minecraft:cooked_salmon":  5,
                                "minecraft:carrot":  1,
                                "minecraft:golden_carrot":  8,
                                "minecraft:potato":  1,
                                "minecraft:baked_potato":  2,
                                "minecraft:diamond_block":  450,
                                "minecraft:emerald_block":  225,
                                "minecraft:gold_block":  90,
                                "minecraft:iron_block":  45,
                                "minecraft:copper_block":  18,
                                "minecraft:coal_block":  9,
                                "minecraft:redstone_block":  18,
                                "minecraft:lapis_block":  27,
                                "minecraft:quartz_block":  18,
                                "minecraft:netherite_block":  1800,
                                "minecraft:string":  1,
                                "minecraft:leather":  3,
                                "minecraft:feather":  2,
                                "minecraft:gunpowder":  5,
                                "minecraft:bone":  2,
                                "minecraft:bone_meal":  1,
                                "minecraft:spider_eye":  3,
                                "minecraft:slime_ball":  8,
                                "minecraft:magma_cream":  10,
                                "minecraft:wheat":  1,
                                "minecraft:wheat_seeds":  1,
                                "minecraft:sugar_cane":  2,
                                "minecraft:bamboo":  1,
                                "minecraft:kelp":  1,
                                "minecraft:cactus":  2
                            },
                 "中文物品名称":  {
                                "钻石":  "minecraft:diamond",
                                "绿宝石":  "minecraft:emerald",
                                "金锭":  "minecraft:gold_ingot",
                                "铁锭":  "minecraft:iron_ingot",
                                "铜锭":  "minecraft:copper_ingot",
                                "煤炭":  "minecraft:coal",
                                "木炭":  "minecraft:charcoal",
                                "红石":  "minecraft:redstone",
                                "青金石":  "minecraft:lapis_lazuli",
                                "石英":  "minecraft:quartz",
                                "下界合金锭":  "minecraft:netherite_ingot",
                                "远古残骸":  "minecraft:ancient_debris",
                                "下界石英":  "minecraft:nether_quartz",
                                "紫水晶碎片":  "minecraft:amethyst_shard",
                                "紫水晶":  "minecraft:amethyst_shard",
                                "末影珍珠":  "minecraft:ender_pearl",
                                "烈焰棒":  "minecraft:blaze_rod",
                                "恶魂之泪":  "minecraft:ghast_tear",
                                "潜影贝壳":  "minecraft:shulker_shell",
                                "鹦鹉螺壳":  "minecraft:nautilus_shell",
                                "海洋之心":  "minecraft:heart_of_the_sea",
                                "圆石":  "minecraft:cobblestone",
                                "石头":  "minecraft:stone",
                                "花岗岩":  "minecraft:granite",
                                "闪长岩":  "minecraft:diorite",
                                "安山岩":  "minecraft:andesite",
                                "深板岩":  "minecraft:deepslate",
                                "黑石":  "minecraft:blackstone",
                                "玄武岩":  "minecraft:basalt",
                                "末地石":  "minecraft:end_stone",
                                "下界岩":  "minecraft:netherrack",
                                "灵魂沙":  "minecraft:soul_sand",
                                "灵魂土":  "minecraft:soul_soil",
                                "橡木原木":  "minecraft:oak_log",
                                "白桦原木":  "minecraft:birch_log",
                                "云杉原木":  "minecraft:spruce_log",
                                "丛林原木":  "minecraft:jungle_log",
                                "金合欢原木":  "minecraft:acacia_log",
                                "深色橡木原木":  "minecraft:dark_oak_log",
                                "绯红菌柄":  "minecraft:crimson_stem",
                                "诡异菌柄":  "minecraft:warped_stem",
                                "橡木木板":  "minecraft:oak_planks",
                                "白桦木板":  "minecraft:birch_planks",
                                "云杉木板":  "minecraft:spruce_planks",
                                "丛林木板":  "minecraft:jungle_planks",
                                "金合欢木板":  "minecraft:acacia_planks",
                                "深色橡木木板":  "minecraft:dark_oak_planks",
                                "苹果":  "minecraft:apple",
                                "金苹果":  "minecraft:golden_apple",
                                "附魔金苹果":  "minecraft:enchanted_golden_apple",
                                "面包":  "minecraft:bread",
                                "牛肉":  "minecraft:beef",
                                "熟牛肉":  "minecraft:cooked_beef",
                                "猪肉":  "minecraft:porkchop",
                                "熟猪肉":  "minecraft:cooked_porkchop",
                                "鸡肉":  "minecraft:chicken",
                                "熟鸡肉":  "minecraft:cooked_chicken",
                                "羊肉":  "minecraft:mutton",
                                "熟羊肉":  "minecraft:cooked_mutton",
                                "鱼":  "minecraft:cod",
                                "熟鱼":  "minecraft:cooked_cod",
                                "鲑鱼":  "minecraft:salmon",
                                "熟鲑鱼":  "minecraft:cooked_salmon",
                                "胡萝卜":  "minecraft:carrot",
                                "金胡萝卜":  "minecraft:golden_carrot",
                                "土豆":  "minecraft:potato",
                                "烤土豆":  "minecraft:baked_potato",
                                "甜菜根":  "minecraft:beetroot",
                                "甜菜汤":  "minecraft:beetroot_soup",
                                "蘑菇煲":  "minecraft:mushroom_stew",
                                "兔肉煲":  "minecraft:rabbit_stew",
                                "木棍":  "minecraft:stick",
                                "线":  "minecraft:string",
                                "皮革":  "minecraft:leather",
                                "羽毛":  "minecraft:feather",
                                "火药":  "minecraft:gunpowder",
                                "骨头":  "minecraft:bone",
                                "骨粉":  "minecraft:bone_meal",
                                "蜘蛛眼":  "minecraft:spider_eye",
                                "腐肉":  "minecraft:rotten_flesh",
                                "史莱姆球":  "minecraft:slime_ball",
                                "岩浆膏":  "minecraft:magma_cream",
                                "小麦":  "minecraft:wheat",
                                "小麦种子":  "minecraft:wheat_seeds",
                                "南瓜":  "minecraft:pumpkin",
                                "南瓜种子":  "minecraft:pumpkin_seeds",
                                "西瓜":  "minecraft:melon",
                                "西瓜种子":  "minecraft:melon_seeds",
                                "甘蔗":  "minecraft:sugar_cane",
                                "竹子":  "minecraft:bamboo",
                                "海带":  "minecraft:kelp",
                                "仙人掌":  "minecraft:cactus",
                                "墨囊":  "minecraft:ink_sac",
                                "玫瑰红":  "minecraft:red_dye",
                                "橙色染料":  "minecraft:orange_dye",
                                "黄色染料":  "minecraft:yellow_dye",
                                "黄绿色染料":  "minecraft:lime_dye",
                                "绿色染料":  "minecraft:green_dye",
                                "青色染料":  "minecraft:cyan_dye",
                                "淡蓝色染料":  "minecraft:light_blue_dye",
                                "蓝色染料":  "minecraft:blue_dye",
                                "紫色染料":  "minecraft:purple_dye",
                                "品红色染料":  "minecraft:magenta_dye",
                                "粉红色染料":  "minecraft:pink_dye",
                                "白色染料":  "minecraft:white_dye",
                                "淡灰色染料":  "minecraft:light_gray_dye",
                                "灰色染料":  "minecraft:gray_dye",
                                "黑色染料":  "minecraft:black_dye",
                                "棕色染料":  "minecraft:brown_dye",
                                "泥土":  "minecraft:dirt",
                                "草方块":  "minecraft:grass_block",
                                "沙子":  "minecraft:sand",
                                "红沙":  "minecraft:red_sand",
                                "砂砾":  "minecraft:gravel",
                                "粘土":  "minecraft:clay",
                                "雪球":  "minecraft:snowball",
                                "冰":  "minecraft:ice",
                                "浮冰":  "minecraft:packed_ice",
                                "蓝冰":  "minecraft:blue_ice",
                                "黑曜石":  "minecraft:obsidian",
                                "哭泣的黑曜石":  "minecraft:crying_obsidian",
                                "基岩":  "minecraft:bedrock",
                                "海绵":  "minecraft:sponge",
                                "湿海绵":  "minecraft:wet_sponge",
                                "钻石块":  "minecraft:diamond_block",
                                "绿宝石块":  "minecraft:emerald_block",
                                "金块":  "minecraft:gold_block",
                                "铁块":  "minecraft:iron_block",
                                "铜块":  "minecraft:copper_block",
                                "煤炭块":  "minecraft:coal_block",
                                "红石块":  "minecraft:redstone_block",
                                "青金石块":  "minecraft:lapis_block",
                                "石英块":  "minecraft:quartz_block",
                                "下界合金块":  "minecraft:netherite_block"
                            },
                 "物品别名":  {
                              "钻":  "钻石",
                              "diamond":  "钻石",
                              "钻石锭":  "钻石",
                              "绿宝":  "绿宝石",
                              "emerald":  "绿宝石",
                              "村民币":  "绿宝石",
                              "翡翠":  "绿宝石",
                              "金":  "金锭",
                              "gold":  "金锭",
                              "黄金":  "金锭",
                              "金子":  "金锭",
                              "铁":  "铁锭",
                              "iron":  "铁锭",
                              "铜":  "铜锭",
                              "copper":  "铜锭",
                              "煤":  "煤炭",
                              "coal":  "煤炭",
                              "煤块":  "煤炭",
                              "红石粉":  "红石",
                              "redstone":  "红石",
                              "青金":  "青金石",
                              "lapis":  "青金石",
                              "蓝宝石":  "青金石",
                              "石英晶体":  "石英",
                              "quartz":  "石英",
                              "下界合金":  "下界合金锭",
                              "netherite":  "下界合金锭",
                              "合金":  "下界合金锭",
                              "下合金":  "下界合金锭",
                              "残骸":  "远古残骸",
                              "ancient_debris":  "远古残骸",
                              "远古":  "远古残骸",
                              "橡木":  "橡木原木",
                              "oak":  "橡木原木",
                              "白桦":  "白桦原木",
                              "birch":  "白桦原木",
                              "云杉":  "云杉原木",
                              "spruce":  "云杉原木",
                              "丛林":  "丛林原木",
                              "jungle":  "丛林原木",
                              "金合欢":  "金合欢原木",
                              "acacia":  "金合欢原木",
                              "深色橡木":  "深色橡木原木",
                              "dark_oak":  "深色橡木原木",
                              "苹果":  "苹果",
                              "apple":  "苹果",
                              "金苹":  "金苹果",
                              "golden_apple":  "金苹果",
                              "附魔苹果":  "附魔金苹果",
                              "神苹":  "附魔金苹果",
                              "notch苹果":  "附魔金苹果",
                              "石":  "石头",
                              "stone":  "石头",
                              "泥":  "泥土",
                              "dirt":  "泥土",
                              "土":  "泥土",
                              "沙":  "沙子",
                              "sand":  "沙子",
                              "末影珠":  "末影珍珠",
                              "ender_pearl":  "末影珍珠",
                              "传送珠":  "末影珍珠",
                              "烈焰":  "烈焰棒",
                              "blaze_rod":  "烈焰棒",
                              "火棒":  "烈焰棒",
                              "恶魂泪":  "恶魂之泪",
                              "ghast_tear":  "恶魂之泪",
                              "鬼泪":  "恶魂之泪"
                          }
             }
}'''
)
DEFAULT_CONFIG: dict[str, Any] = json.loads(DEFAULT_CONFIG_JSON)

LEVEL_EXP_CONFIG_KEY = "公会各等级升级所需经验"

CONFIG_ATTRIBUTE_ALIASES = {
    "GUILD_LEVEL_EXP": LEVEL_EXP_CONFIG_KEY,
    "GUILD_MENU_TRIGGER": "公会菜单唤醒词",
    "GUILD_CREATION_COST": "创建公会消耗积分",
    "MAX_GUILD_MEMBERS": "公会最大成员数",
    "GUILD_SCOREBOARD": "积分计分板名称",
    "GUILD_FUNCTION_VAULT": "公会仓库",
    "GUILD_FUNCTION_BASE": "公会据点",
    "GUILD_FUNCTION_DONATION": "公会捐献",
    "GUILD_FUNCTION_TASKS": "公会任务",
    "GUILD_FUNCTION_EFFECT": "公会效果",
    "GUILD_FUNCTION_RANKINGS": "公会排行",
    "EXP_PER_ONLINE_MEMBER": "在线成员每次增加经验",
    "EXP_UPDATE_INTERVAL": "在线经验增加间隔秒",
    "DAILY_LOGIN_EXP": "每日登录经验",
    "DONATION_EXP_RATE": "捐献转经验倍率",
    "ITEMS_PER_PAGE": "每页显示数量",
    "VAULT_INITIAL_SLOTS": "初始容量",
    "VAULT_SLOTS_PER_LEVEL": "每级增加容量",
    "VAULT_TRADE_TAX": "交易税率",
    "DIMENSION_NAMES": "维度名称映射",
    "CACHE_DURATION": "缓存有效时间秒",
    "EFFECT_REFRESH_INTERVAL": "刷新间隔秒",
    "EFFECTS_CONFIG": "效果列表",
    "BATCH_SAVE_INTERVAL": "批量保存间隔秒",
    "MAX_BATCH_SIZE": "批量保存最大数量",
    "PERMISSIONS": "职位权限配置",
    "GUILD_CREATE_CONFIG": "创建配置",
    "GUILD_JOIN_REQUEST_CONFIG": "申请配置",
    "GUILD_VAULT_CONFIG": "市场配置",
    "GUILD_TASK_CONFIG": "任务系统",
    "GUILD_DATA_SAFETY_CONFIG": "数据安全",
    "PROMPT_CONFIG": "提示词配置",
    "MENU_CONFIG": "功能列表配置",
    "DEFAULT_ITEM_VALUES": "默认物品价值",
    "CHINESE_ITEM_NAMES": "中文物品名称",
    "ITEM_ALIASES": "物品别名",
}

CONFIG_ATTRIBUTE_KEYS = {
    config_key: attr_name for attr_name,
    config_key in CONFIG_ATTRIBUTE_ALIASES.items()}

REMOVED_CONFIG_ATTRIBUTES = ("GUILD_LEVELS",)

CONFIG_VERSION_KEY = "配置版本"
GROUPED_CONFIG_VERSION = "0.1.7"
CONFIG_FILE_DIR = "插件配置文件"
RUNTIME_CONFIG_RELOAD_INTERVAL = 5
DYNAMIC_LOAD_SETTINGS_KEY = "动态载入设置"
DYNAMIC_LOAD_ENABLED_KEY = "是否启用动态载入配置文件（仅用于本插件）"
DYNAMIC_LOAD_INTERVAL_KEY = "动态载入检测时间间隔（单位：秒）"
DYNAMIC_LOAD_DEFAULT = {
    DYNAMIC_LOAD_ENABLED_KEY: True,
    DYNAMIC_LOAD_INTERVAL_KEY: RUNTIME_CONFIG_RELOAD_INTERVAL,
}


def _merge_config(raw: Any, default: Any) -> Any:
    """Implement the merge config operation."""
    if isinstance(default, dict):
        merged = {
            key: _merge_config(raw.get(key) if isinstance(raw, dict) else None, value)
            for key, value in default.items()
        }

        if isinstance(raw, dict):
            for key, value in raw.items():
                if key not in merged:
                    merged[key] = copy.deepcopy(value)

        return merged

    return copy.deepcopy(raw) if raw is not None else copy.deepcopy(default)


def _normalize_bool(value: Any, fallback: bool) -> bool:
    """Normalize bool values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "y", "on", "启用", "是", "真"):
            return True
        if text in ("false", "0", "no", "n", "off", "禁用", "否", "假"):
            return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    return bool(fallback)


def _normalize_str(
        value: Any,
        fallback: str,
        *,
        allow_empty: bool = False) -> str:
    """Normalize str values."""
    if value is None:
        return fallback
    text = str(value).strip()
    if text or allow_empty:
        return text
    return fallback


def _normalize_number(value: Any, fallback: int | float) -> int | float:
    """Normalize number values."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    if number.is_integer():
        return int(number)
    return number


def _normalize_positive_int(value: Any, fallback: int) -> int:
    """Normalize positive int values."""
    if isinstance(value, bool):
        return fallback
    try:
        result = int(value)
    except (TypeError, ValueError):
        return fallback
    return result if result > 0 else fallback


def _normalize_non_negative_int(value: Any, fallback: int) -> int:
    """Normalize non negative int values."""
    if isinstance(value, bool):
        return fallback
    try:
        result = int(value)
    except (TypeError, ValueError):
        return fallback
    return result if result >= 0 else fallback


def _normalize_string_list(
        value: Any,
        fallback: list[str],
        *,
        allow_empty: bool = False) -> list[str]:
    """Normalize string list values."""
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, list):
        candidates = value
    else:
        return copy.deepcopy(fallback)

    result: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in result:
            result.append(text)
    if result or allow_empty:
        return result
    return copy.deepcopy(fallback)


def _normalize_any_key_dict(
        raw: Any, fallback: dict[str, Any], value_normalizer) -> dict[str, Any]:
    """Normalize any key dict values."""
    source = raw if isinstance(raw, dict) else fallback
    default_values = fallback if isinstance(fallback, dict) else {}
    result: dict[str, Any] = {}
    for key, value in source.items():
        text_key = str(key)
        fallback_value = default_values.get(text_key)
        if fallback_value is None and default_values:
            fallback_value = next(iter(default_values.values()))
        result[text_key] = value_normalizer(value, fallback_value)
    return result


def _normalize_menu_items(
        raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """Normalize menu items values."""
    source = _merge_config(raw, fallback)
    result: dict[str, Any] = {}
    for key, item_fallback in fallback.items():
        item = source.get(key) if isinstance(source, dict) else None
        if not isinstance(item, dict):
            item = {}
        result[key] = {
            "名称": _normalize_str(
                item.get("名称"),
                item_fallback["名称"]),
            "描述": _normalize_str(
                item.get("描述"),
                item_fallback["描述"],
                allow_empty=True),
        }
    return result


def _trim_fixed_keys(raw: dict[str, Any],
                     default: dict[str, Any]) -> dict[str, Any]:
    """Implement the trim fixed keys operation."""
    return {
        key: raw.get(key, copy.deepcopy(value))
        for key, value in default.items()
    }


def _normalize_market_config(
        raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """Normalize market config values."""
    raw = raw if isinstance(raw, dict) else {}
    result = copy.deepcopy(fallback)
    bool_keys = (
        "启用交易日志",
        "启用撤回出售",
        "只允许撤回自己的物品",
        "撤回后返还物品",
        "允许购买自己出售的物品",
    )
    positive_int_keys = (
        "交易日志保留数量",
        "单个成员最大上架数量",
        "单次出售最大数量",
        "单笔价格下限",
        "单笔价格上限",
    )
    number_keys = (
        "建议价最小倍率",
        "建议价最大倍率",
        "高价交易审计倍率",
    )
    for key in bool_keys:
        result[key] = _normalize_bool(raw.get(key, result[key]), result[key])
    for key in positive_int_keys:
        result[key] = _normalize_positive_int(
            raw.get(key, result[key]), result[key])
    for key in number_keys:
        result[key] = _normalize_number(raw.get(key, result[key]), result[key])
    return result


def _normalize_effects_config(
        raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """Normalize effects config values."""
    source = raw if isinstance(raw, dict) else fallback
    default_effect = next(iter(fallback.values())) if fallback else {}
    result: dict[str, Any] = {}
    for effect_id, effect_cfg in source.items():
        if not isinstance(effect_cfg, dict):
            effect_cfg = {}
        default = fallback.get(str(effect_id), default_effect)
        result[str(effect_id)] = {
            "name": _normalize_str(
                effect_cfg.get("name"),
                default.get("name", str(effect_id)),
            ),
            "levels": _normalize_any_key_dict(
                effect_cfg.get("levels"),
                default.get("levels", {}),
                lambda value, fallback_value: _normalize_non_negative_int(
                    value,
                    int(fallback_value or 0),
                ),
            ),
            "costs": _normalize_any_key_dict(
                effect_cfg.get("costs"),
                default.get("costs", {}),
                lambda value, fallback_value: _normalize_non_negative_int(
                    value,
                    int(fallback_value or 0),
                ),
            ),
        }
    return result


def _normalize_permissions(
        raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """Normalize permissions values."""
    source = raw if isinstance(raw, dict) else fallback
    default_role = next(iter(fallback.values())) if fallback else {}
    result: dict[str, dict[str, bool]] = {}
    for role, permissions in source.items():
        if not isinstance(permissions, dict):
            permissions = {}
        default_permissions = fallback.get(str(role), default_role)
        merged_permissions = _merge_config(permissions, default_permissions)
        result[str(role)] = {
            str(key): _normalize_bool(value, bool(default_permissions.get(key, False)))
            for key, value in merged_permissions.items()
        }
    return result


def _normalize_task_templates(
        raw: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize task templates values."""
    source = raw if isinstance(raw, list) else fallback
    default_template = fallback[0] if fallback else {}
    result: list[dict[str, Any]] = []
    for template in source:
        if not isinstance(template, dict):
            continue
        default = _merge_config(template, default_template)
        result.append(
            {
                "name": _normalize_str(
                    template.get("name"),
                    default["name"]),
                "description": _normalize_str(
                    template.get("description"),
                    default["description"]),
                "task_type": _normalize_str(
                    template.get("task_type"),
                    default["task_type"]),
                "target": _normalize_str(
                    template.get("target"),
                    default["target"]),
                "target_count": _normalize_positive_int(
                    template.get("target_count"),
                    default["target_count"],
                ),
                "reward_exp": _normalize_non_negative_int(
                    template.get("reward_exp"),
                    default["reward_exp"],
                ),
                "reward_contribution": _normalize_non_negative_int(
                    template.get("reward_contribution"),
                    default["reward_contribution"],
                ),
            })
    return result or copy.deepcopy(fallback)


def _normalize_grouped_config(  # skipcq: PY-R1000
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Normalize grouped config values."""
    default = DEFAULT_CONFIG
    config = _merge_config(raw, default)
    config = {key: copy.deepcopy(config[key]) for key in default}
    config[CONFIG_VERSION_KEY] = GROUPED_CONFIG_VERSION

    config[DYNAMIC_LOAD_SETTINGS_KEY] = _trim_fixed_keys(
        config[DYNAMIC_LOAD_SETTINGS_KEY],
        default[DYNAMIC_LOAD_SETTINGS_KEY],
    )
    dynamic = config[DYNAMIC_LOAD_SETTINGS_KEY]
    dynamic_default = default[DYNAMIC_LOAD_SETTINGS_KEY]
    dynamic[DYNAMIC_LOAD_ENABLED_KEY] = _normalize_bool(
        dynamic.get(DYNAMIC_LOAD_ENABLED_KEY),
        dynamic_default[DYNAMIC_LOAD_ENABLED_KEY],
    )
    dynamic[DYNAMIC_LOAD_INTERVAL_KEY] = _normalize_positive_int(
        dynamic.get(DYNAMIC_LOAD_INTERVAL_KEY),
        dynamic_default[DYNAMIC_LOAD_INTERVAL_KEY],
    )

    config["基础配置"] = _trim_fixed_keys(config["基础配置"], default["基础配置"])
    base = config["基础配置"]
    base_default = default["基础配置"]
    base["是否启用插件"] = _normalize_bool(
        base.get("是否启用插件"), base_default["是否启用插件"])
    base["公会菜单唤醒词"] = _normalize_string_list(
        base.get("公会菜单唤醒词"),
        base_default["公会菜单唤醒词"],
    )
    base["积分计分板名称"] = _normalize_str(
        base.get("积分计分板名称"),
        base_default["积分计分板名称"])
    for key in ("缓存有效时间秒", "批量保存间隔秒", "批量保存最大数量"):
        base[key] = _normalize_positive_int(base.get(key), base_default[key])

    config["公会配置"] = _trim_fixed_keys(config["公会配置"], default["公会配置"])
    guild = config["公会配置"]
    guild_default = default["公会配置"]
    for key in (
        "公会最大成员数",
        "在线经验增加间隔秒",
        "每页显示数量",
    ):
        guild[key] = _normalize_positive_int(
            guild.get(key), guild_default[key])
    for key in ("在线成员每次增加经验", "每日登录经验"):
        guild[key] = _normalize_non_negative_int(
            guild.get(key), guild_default[key])
    guild["捐献转经验倍率"] = _normalize_number(
        guild.get("捐献转经验倍率"),
        guild_default["捐献转经验倍率"],
    )
    guild[LEVEL_EXP_CONFIG_KEY] = _normalize_any_key_dict(
        guild.get(LEVEL_EXP_CONFIG_KEY),
        guild_default[LEVEL_EXP_CONFIG_KEY],
        lambda value, fallback_value: _normalize_positive_int(
            value, int(fallback_value or 1)),
    )

    config["功能开关"] = _trim_fixed_keys(config["功能开关"], default["功能开关"])
    feature_switches = config["功能开关"]
    for key, fallback in default["功能开关"].items():
        feature_switches[key] = _normalize_bool(
            feature_switches.get(key), fallback)

    config["仓库配置"] = _trim_fixed_keys(config["仓库配置"], default["仓库配置"])
    vault = config["仓库配置"]
    vault_default = default["仓库配置"]
    vault["初始容量"] = _normalize_positive_int(
        vault.get("初始容量"), vault_default["初始容量"])
    vault["每级增加容量"] = _normalize_non_negative_int(
        vault.get("每级增加容量"),
        vault_default["每级增加容量"],
    )
    vault["交易税率"] = _normalize_number(vault.get("交易税率"), vault_default["交易税率"])
    vault["市场配置"] = _normalize_market_config(
        vault.get("市场配置"), vault_default["市场配置"])

    config["经验配置"] = _trim_fixed_keys(config["经验配置"], default["经验配置"])
    config["经验配置"]["在线经验"] = _trim_fixed_keys(
        config["经验配置"]["在线经验"],
        default["经验配置"]["在线经验"],
    )
    config["经验配置"]["登录经验"] = _trim_fixed_keys(
        config["经验配置"]["登录经验"],
        default["经验配置"]["登录经验"],
    )
    config["经验配置"]["捐献经验"] = _trim_fixed_keys(
        config["经验配置"]["捐献经验"],
        default["经验配置"]["捐献经验"],
    )
    exp = config["经验配置"]
    exp_default = default["经验配置"]
    exp["在线经验"]["每次增加经验"] = _normalize_non_negative_int(
        exp["在线经验"].get("每次增加经验"),
        exp_default["在线经验"]["每次增加经验"],
    )
    exp["在线经验"]["增加间隔秒"] = _normalize_positive_int(
        exp["在线经验"].get("增加间隔秒"),
        exp_default["在线经验"]["增加间隔秒"],
    )
    exp["登录经验"]["每日登录经验"] = _normalize_non_negative_int(
        exp["登录经验"].get("每日登录经验"),
        exp_default["登录经验"]["每日登录经验"],
    )
    exp["捐献经验"]["转经验倍率"] = _normalize_number(
        exp["捐献经验"].get("转经验倍率"),
        exp_default["捐献经验"]["转经验倍率"],
    )

    config["据点配置"] = _trim_fixed_keys(config["据点配置"], default["据点配置"])
    config["据点配置"]["维度名称映射"] = _normalize_any_key_dict(
        config["据点配置"].get("维度名称映射"),
        default["据点配置"]["维度名称映射"],
        lambda value,
        fallback_value: _normalize_str(value, str(fallback_value or "")),)

    config["效果系统"] = _trim_fixed_keys(config["效果系统"], default["效果系统"])
    effects = config["效果系统"]
    effects_default = default["效果系统"]
    effects["刷新间隔秒"] = _normalize_positive_int(
        effects.get("刷新间隔秒"),
        effects_default["刷新间隔秒"],
    )
    effects["效果列表"] = _normalize_effects_config(
        effects.get("效果列表"),
        effects_default["效果列表"],
    )

    config["创建配置"] = _trim_fixed_keys(config["创建配置"], default["创建配置"])
    create_cfg = config["创建配置"]
    create_default = default["创建配置"]
    create_cfg["创建公会消耗积分"] = _normalize_non_negative_int(
        create_cfg.get("创建公会消耗积分"),
        create_default["创建公会消耗积分"],
    )
    for key in ("创建冷却秒", "最短公会名长度", "最长公会名长度"):
        create_cfg[key] = _normalize_positive_int(
            create_cfg.get(key), create_default[key])
    create_cfg["禁止公会名列表"] = _normalize_string_list(
        create_cfg.get("禁止公会名列表"),
        create_default["禁止公会名列表"],
        allow_empty=True,
    )
    create_cfg["禁止公会名包含词"] = _normalize_string_list(
        create_cfg.get("禁止公会名包含词"),
        create_default["禁止公会名包含词"],
        allow_empty=True,
    )
    create_cfg["启用同名模糊检测"] = _normalize_bool(
        create_cfg.get("启用同名模糊检测"),
        create_default["启用同名模糊检测"],
    )
    create_cfg["模糊检测最小相似度"] = _normalize_number(
        create_cfg.get("模糊检测最小相似度"),
        create_default["模糊检测最小相似度"],
    )
    create_cfg["创建后全服公告"] = _normalize_bool(
        create_cfg.get("创建后全服公告"),
        create_default["创建后全服公告"],
    )

    config["申请配置"] = _trim_fixed_keys(config["申请配置"], default["申请配置"])
    join_cfg = config["申请配置"]
    join_default = default["申请配置"]
    for key, fallback in join_default.items():
        if isinstance(fallback, bool):
            join_cfg[key] = _normalize_bool(join_cfg.get(key), fallback)
        else:
            join_cfg[key] = _normalize_positive_int(
                join_cfg.get(key), fallback)

    config["任务系统"] = _trim_fixed_keys(config["任务系统"], default["任务系统"])
    task_cfg = config["任务系统"]
    task_default = default["任务系统"]
    task_cfg["启用自动任务模板"] = _normalize_bool(
        task_cfg.get("启用自动任务模板"),
        task_default["启用自动任务模板"],
    )
    for key in (
        "自动任务生成间隔秒",
        "每次生成自动任务数量",
        "自动任务最大同时存在数量",
        "自动任务默认有效期秒",
        "成员每日可完成任务数量",
        "创建任务名称最大长度",
        "创建任务描述最大长度",
        "创建任务目标数量上限",
    ):
        task_cfg[key] = _normalize_positive_int(
            task_cfg.get(key), task_default[key])
    for key in ("创建任务贡献奖励上限", "创建任务经验奖励上限"):
        task_cfg[key] = _normalize_non_negative_int(
            task_cfg.get(key), task_default[key])
    task_cfg["自动任务模板列表"] = _normalize_task_templates(
        task_cfg.get("自动任务模板列表"),
        task_default["自动任务模板列表"],
    )

    config["权限系统"] = _trim_fixed_keys(config["权限系统"], default["权限系统"])
    config["权限系统"]["职位权限配置"] = _normalize_permissions(
        config["权限系统"].get("职位权限配置"),
        default["权限系统"]["职位权限配置"],
    )

    config["数据安全"] = _trim_fixed_keys(config["数据安全"], default["数据安全"])
    safety = config["数据安全"]
    safety_default = default["数据安全"]
    safety["备份目录名"] = _normalize_str(
        safety.get("备份目录名"),
        safety_default["备份目录名"])
    for key in (
        "启用保存前备份",
        "强制保存时也备份",
        "启用异常数据跳过",
        "启动时自动修复缺失字段",
        "修复前写入备份",
    ):
        safety[key] = _normalize_bool(safety.get(key), safety_default[key])
    safety["最大备份数量"] = _normalize_positive_int(
        safety.get("最大备份数量"),
        safety_default["最大备份数量"],
    )
    safety["审计日志保留数量"] = _normalize_positive_int(
        safety.get("审计日志保留数量"),
        safety_default["审计日志保留数量"],
    )

    prompt_config = _merge_config(config.get("提示词配置"), default["提示词配置"])
    config["提示词配置"] = _normalize_any_key_dict(
        prompt_config,
        prompt_config,
        lambda value, fallback_value: _normalize_str(
            value,
            str(fallback_value or ""),
            allow_empty=True,
        ),
    )

    config["功能列表配置"] = _trim_fixed_keys(config["功能列表配置"], default["功能列表配置"])
    menu_config = config["功能列表配置"]
    menu_default = default["功能列表配置"]
    for key in (
        "菜单标题",
        "游客身份显示",
        "成员身份显示模板",
        "输入数字提示模板",
        "输入名称提示词",
    ):
        menu_config[key] = _normalize_str(menu_config.get(
            key), menu_default[key], allow_empty=True)
    menu_config["基础功能"] = _normalize_menu_items(
        menu_config.get("基础功能"),
        menu_default["基础功能"],
    )
    menu_config["可选功能"] = _normalize_menu_items(
        menu_config.get("可选功能"),
        menu_default["可选功能"],
    )

    config["经济系统"] = _trim_fixed_keys(config["经济系统"], default["经济系统"])
    economy = config["经济系统"]
    economy_default = default["经济系统"]
    economy["默认物品价值"] = _normalize_any_key_dict(
        economy.get("默认物品价值"),
        economy_default["默认物品价值"],
        lambda value,
        fallback_value: _normalize_number(
            value,
            fallback_value or 1),
    )
    for key in ("中文物品名称", "物品别名"):
        economy[key] = _normalize_any_key_dict(
            economy.get(key),
            economy_default[key],
            lambda value, fallback_value: _normalize_str(
                value, str(fallback_value or "")),
        )

    return config


def grouped_config_std() -> dict[str, Any]:
    """Return the ToolDelta schema for the grouped guild config."""
    number = (int, float)
    string_map = cfg.AnyKeyValue(str)
    number_map = cfg.AnyKeyValue(number)
    int_map = cfg.AnyKeyValue(cfg.NNInt)
    menu_item_std = {
        "名称": str,
        "描述": str,
    }
    effect_std = cfg.AnyKeyValue(
        {
            "name": str,
            "levels": int_map,
            "costs": int_map,
        }
    )
    permission_std = cfg.AnyKeyValue(cfg.AnyKeyValue(bool))
    task_template_std = {
        "name": str,
        "description": str,
        "task_type": str,
        "target": str,
        "target_count": cfg.PInt,
        "reward_exp": cfg.NNInt,
        "reward_contribution": cfg.NNInt,
    }

    return {
        CONFIG_VERSION_KEY: str,
        DYNAMIC_LOAD_SETTINGS_KEY: {
            DYNAMIC_LOAD_ENABLED_KEY: bool,
            DYNAMIC_LOAD_INTERVAL_KEY: cfg.PInt,
        },
        "基础配置": {
            "是否启用插件": bool,
            "公会菜单唤醒词": cfg.JsonList(str, -1),
            "积分计分板名称": str,
            "缓存有效时间秒": cfg.PInt,
            "批量保存间隔秒": cfg.PInt,
            "批量保存最大数量": cfg.PInt,
        },
        "功能开关": {
            "公会仓库": bool,
            "公会据点": bool,
            "公会捐献": bool,
            "公会任务": bool,
            "公会效果": bool,
            "公会排行": bool,
        },
        "公会配置": {
            "公会最大成员数": cfg.PInt,
            "在线成员每次增加经验": cfg.NNInt,
            "在线经验增加间隔秒": cfg.PInt,
            "每日登录经验": cfg.NNInt,
            "捐献转经验倍率": number,
            "每页显示数量": cfg.PInt,
            LEVEL_EXP_CONFIG_KEY: cfg.AnyKeyValue(cfg.PInt),
        },
        "创建配置": {
            "创建公会消耗积分": cfg.NNInt,
            "创建冷却秒": cfg.PInt,
            "最短公会名长度": cfg.PInt,
            "最长公会名长度": cfg.PInt,
            "禁止公会名列表": cfg.JsonList(str, -1),
            "禁止公会名包含词": cfg.JsonList(str, -1),
            "启用同名模糊检测": bool,
            "模糊检测最小相似度": number,
            "创建后全服公告": bool,
        },
        "仓库配置": {
            "初始容量": cfg.PInt,
            "每级增加容量": cfg.NNInt,
            "交易税率": number,
            "市场配置": {
                "启用交易日志": bool,
                "交易日志保留数量": cfg.PInt,
                "启用撤回出售": bool,
                "只允许撤回自己的物品": bool,
                "撤回后返还物品": bool,
                "允许购买自己出售的物品": bool,
                "单个成员最大上架数量": cfg.PInt,
                "单次出售最大数量": cfg.PInt,
                "单笔价格下限": cfg.PInt,
                "单笔价格上限": cfg.PInt,
                "建议价最小倍率": number,
                "建议价最大倍率": number,
                "高价交易审计倍率": number,
            },
        },
        "经验配置": {
            "在线经验": {
                "每次增加经验": cfg.NNInt,
                "增加间隔秒": cfg.PInt,
            },
            "登录经验": {
                "每日登录经验": cfg.NNInt,
            },
            "捐献经验": {
                "转经验倍率": number,
            },
        },
        "据点配置": {
            "维度名称映射": string_map,
        },
        "效果系统": {
            "刷新间隔秒": cfg.PInt,
            "效果列表": effect_std,
        },
        "申请配置": {
            "启用离线申请队列": bool,
            "申请有效期秒": cfg.PInt,
            "重复申请冷却秒": cfg.PInt,
            "每个玩家最多待处理申请数": cfg.PInt,
            "每个公会最多待处理申请数": cfg.PInt,
            "申请理由最大长度": cfg.PInt,
            "满员时自动拒绝新申请": bool,
            "申请提交后通知在线管理员": bool,
            "批准后通知全体在线成员": bool,
            "拒绝后保留记录": bool,
        },
        "任务系统": {
            "启用自动任务模板": bool,
            "自动任务生成间隔秒": cfg.PInt,
            "每次生成自动任务数量": cfg.PInt,
            "自动任务最大同时存在数量": cfg.PInt,
            "自动任务默认有效期秒": cfg.PInt,
            "成员每日可完成任务数量": cfg.PInt,
            "创建任务名称最大长度": cfg.PInt,
            "创建任务描述最大长度": cfg.PInt,
            "创建任务目标数量上限": cfg.PInt,
            "创建任务贡献奖励上限": cfg.NNInt,
            "创建任务经验奖励上限": cfg.NNInt,
            "自动任务模板列表": cfg.JsonList(task_template_std, -1),
        },
        "权限系统": {
            "职位权限配置": permission_std,
        },
        "数据安全": {
            "启用保存前备份": bool,
            "备份目录名": str,
            "最大备份数量": cfg.PInt,
            "强制保存时也备份": bool,
            "启用异常数据跳过": bool,
            "启动时自动修复缺失字段": bool,
            "修复前写入备份": bool,
            "审计日志保留数量": cfg.PInt,
        },
        "提示词配置": string_map,
        "功能列表配置": {
            "菜单标题": str,
            "游客身份显示": str,
            "成员身份显示模板": str,
            "输入数字提示模板": str,
            "输入名称提示词": str,
            "基础功能": cfg.AnyKeyValue(menu_item_std),
            "可选功能": cfg.AnyKeyValue(menu_item_std),
        },
        "经济系统": {
            "默认物品价值": number_map,
            "中文物品名称": string_map,
            "物品别名": string_map,
        },
    }


def _int_keyed_dict(raw: Any) -> Any:
    """Implement the int keyed dict operation."""
    if not isinstance(raw, dict):
        return raw

    result = {}
    for key, value in raw.items():
        try:
            normalized_key = int(key)
        except (TypeError, ValueError):
            normalized_key = key
        result[normalized_key] = value
    return result


def _require_current_config_format(raw_config: Any) -> None:
    """Implement the require current config format operation."""
    if not isinstance(raw_config, dict):
        raise ValueError("配置项必须是对象")


def _normalize_effect_runtime_config(raw: Any) -> Any:
    """Normalize effect runtime config values."""
    effects = copy.deepcopy(raw)
    if not isinstance(effects, dict):
        return effects

    for effect in effects.values():
        if not isinstance(effect, dict):
            continue
        for key in ("levels", "costs"):
            if key in effect:
                effect[key] = _int_keyed_dict(effect[key])
    return effects


def _build_runtime_config(grouped_config: dict[str, Any]) -> dict[str, Any]:
    """Implement the build runtime config operation."""
    base = grouped_config["基础配置"]
    features = grouped_config["功能开关"]
    guild = grouped_config["公会配置"]
    create = grouped_config["创建配置"]
    vault = grouped_config["仓库配置"]
    exp = grouped_config["经验配置"]
    base_point = grouped_config["据点配置"]
    effects = grouped_config["效果系统"]
    permissions = grouped_config["权限系统"]
    economy = grouped_config["经济系统"]

    return {
        "是否启用插件": copy.deepcopy(base["是否启用插件"]),
        "公会菜单唤醒词": copy.deepcopy(base["公会菜单唤醒词"]),
        "积分计分板名称": copy.deepcopy(base["积分计分板名称"]),
        "缓存有效时间秒": copy.deepcopy(base["缓存有效时间秒"]),
        "批量保存间隔秒": copy.deepcopy(base["批量保存间隔秒"]),
        "批量保存最大数量": copy.deepcopy(base["批量保存最大数量"]),
        "公会仓库": copy.deepcopy(features["公会仓库"]),
        "公会据点": copy.deepcopy(features["公会据点"]),
        "公会捐献": copy.deepcopy(features["公会捐献"]),
        "公会任务": copy.deepcopy(features["公会任务"]),
        "公会效果": copy.deepcopy(features["公会效果"]),
        "公会排行": copy.deepcopy(features["公会排行"]),
        "公会最大成员数": copy.deepcopy(guild["公会最大成员数"]),
        "在线成员每次增加经验": copy.deepcopy(exp["在线经验"]["每次增加经验"]),
        "在线经验增加间隔秒": copy.deepcopy(exp["在线经验"]["增加间隔秒"]),
        "每日登录经验": copy.deepcopy(exp["登录经验"]["每日登录经验"]),
        "捐献转经验倍率": copy.deepcopy(exp["捐献经验"]["转经验倍率"]),
        "每页显示数量": copy.deepcopy(guild["每页显示数量"]),
        LEVEL_EXP_CONFIG_KEY: _int_keyed_dict(guild[LEVEL_EXP_CONFIG_KEY]),
        "创建公会消耗积分": copy.deepcopy(create["创建公会消耗积分"]),
        "创建配置": copy.deepcopy(create),
        "申请配置": copy.deepcopy(grouped_config["申请配置"]),
        "初始容量": copy.deepcopy(vault["初始容量"]),
        "每级增加容量": copy.deepcopy(vault["每级增加容量"]),
        "交易税率": copy.deepcopy(vault["交易税率"]),
        "市场配置": copy.deepcopy(vault["市场配置"]),
        "维度名称映射": _int_keyed_dict(base_point["维度名称映射"]),
        "刷新间隔秒": copy.deepcopy(effects["刷新间隔秒"]),
        "效果列表": _normalize_effect_runtime_config(effects["效果列表"]),
        "任务系统": copy.deepcopy(grouped_config["任务系统"]),
        "职位权限配置": copy.deepcopy(permissions["职位权限配置"]),
        "数据安全": copy.deepcopy(grouped_config["数据安全"]),
        "提示词配置": copy.deepcopy(grouped_config["提示词配置"]),
        "功能列表配置": copy.deepcopy(grouped_config["功能列表配置"]),
        "默认物品价值": copy.deepcopy(economy["默认物品价值"]),
        "中文物品名称": copy.deepcopy(economy["中文物品名称"]),
        "物品别名": copy.deepcopy(economy["物品别名"]),
    }


def _set_config_attributes(
        config_cls: type, normalized_config: dict[str, Any]) -> None:
    """Set config attributes data."""
    for attr_name in REMOVED_CONFIG_ATTRIBUTES:
        if hasattr(config_cls, attr_name):
            delattr(config_cls, attr_name)

    for key, value in normalized_config.items():
        attr_name = CONFIG_ATTRIBUTE_KEYS.get(key, key)
        setattr(config_cls, attr_name, value)


class Config:
    """Runtime facade exposing loaded config as Config.X attributes."""

    _loaded = False
    _config: dict[str, Any] = {}
    _grouped_config: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)

    @classmethod
    def grouped_config_std(cls) -> dict[str, Any]:
        """Implement the grouped config std operation."""
        return grouped_config_std()

    @classmethod
    def is_dynamic_load_enabled(cls) -> bool:
        """Implement the is dynamic load enabled operation."""
        settings = cls._grouped_config.get(DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return DYNAMIC_LOAD_DEFAULT[DYNAMIC_LOAD_ENABLED_KEY]
        return bool(
            settings.get(
                DYNAMIC_LOAD_ENABLED_KEY,
                DYNAMIC_LOAD_DEFAULT[DYNAMIC_LOAD_ENABLED_KEY]))

    @classmethod
    def dynamic_load_interval(cls) -> int:
        """Implement the dynamic load interval operation."""
        settings = cls._grouped_config.get(DYNAMIC_LOAD_SETTINGS_KEY, {})
        if not isinstance(settings, dict):
            return RUNTIME_CONFIG_RELOAD_INTERVAL
        return _normalize_positive_int(
            settings.get(
                DYNAMIC_LOAD_INTERVAL_KEY,
                RUNTIME_CONFIG_RELOAD_INTERVAL),
            RUNTIME_CONFIG_RELOAD_INTERVAL,
        )

    @classmethod
    def load(cls,
             plugin_name: str,
             version: tuple[int,
                            int,
                            int]) -> dict[str,
                                          Any]:
        """Load load data."""
        default_config = copy.deepcopy(DEFAULT_CONFIG)

        try:
            raw_config, _ = cfg.get_plugin_config_and_version(
                plugin_name,
                {},
                default_config,
                version,
            )
        except Exception as err:
            fmts.print_err(
                f"{plugin_name} config load failed, using defaults: {err}")
            raw_config = default_config

        try:
            _require_current_config_format(raw_config)
            grouped_config = _normalize_grouped_config(raw_config)
            cfg.check_auto(cls.grouped_config_std(), grouped_config)
        except Exception as err:
            fmts.print_err(
                f"{plugin_name} config validation failed, using defaults: {err}")
            grouped_config = _normalize_grouped_config({})
            cfg.check_auto(cls.grouped_config_std(), grouped_config)
        cfg.upgrade_plugin_config(plugin_name, grouped_config, version)

        runtime_config = _build_runtime_config(grouped_config)
        _set_config_attributes(cls, runtime_config)

        cls._config = runtime_config
        cls._grouped_config = grouped_config
        cls._loaded = True

        return copy.deepcopy(runtime_config)
