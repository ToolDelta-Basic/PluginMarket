from .BDXConverter.Operation.PlaceCommandBlockWithCommandBlockData import (
    PlaceCommandBlockWithCommandBlockData,
)
from .BDXConverter.Operation.structOfChest import ChestData, ChestSlot


def load_chest(chest_data: dict):
    chest = ChestData()
    # TODO: 暂定箱子槽位数为 27;
    chest.slotCount = 27
    for items in chest_data["Items"]:
        slot = load_chest_slot(items)
        chest.chestData.append(slot)
    return chest


def load_chest_slot(chest_slot_data: dict):
    slot = ChestSlot()
    slot.slotID = chest_slot_data["Slot"]
    slot.itemName = chest_slot_data["Name"]
    slot.count = chest_slot_data["Count"]
    if block_data := chest_slot_data.get("Block"):
        slot.data = block_data["val"]
    else:
        slot.data = chest_slot_data["Damage"]
    return slot


def load_command_block(cb_data: dict, cb_state: dict):
    op = PlaceCommandBlockWithCommandBlockData()
    op.command = cb_data["Command"]
    op.conditional = cb_state["conditional_bit"]
    op.customName = cb_data["CustomName"]
    op.executeOnFirstTick = cb_data["ExecuteOnFirstTick"]
    op.lastOutput = cb_data["LastOutput"]
    op.needsRedstone = not cb_data["auto"]
    op.tickDelay = cb_data["TickDelay"]
    op.trackOutput = cb_data["TrackOutput"]
    # op.data, op.mode
    return op

# {
#     "Findable": 0,
#     "IsIgnoreShuffle": 0,
#     "IsOpened": 1,
#     "Items": [
#         {
#             "Block": {
#                 "name": "minecraft:diamond_block",
#                 "states": {},
#                 "val": 0,
#                 "version": 18100737
#             },
#             "Count": 1,
#             "Damage": 0,
#             "Name": "minecraft:diamond_block",
#             "Slot": 0,
#             "WasPickedUp": 0
#         },
#         {
#             "Block": {
#                 "name": "minecraft:redstone_block",
#                 "states": {},
#                 "val": 0,
#                 "version": 18100737
#             },
#             "Count": 8,
#             "Damage": 0,
#             "Name": "minecraft:redstone_block",
#             "Slot": 1,
#             "WasPickedUp": 0
#         },
#         {
#             "Block": {
#                 "name": "minecraft:repeating_command_block",
#                 "states": {
#                     "conditional_bit": 0,
#                     "facing_direction": 0
#                 },
#                 "val": 0,
#                 "version": 18100737
#             },
#             "Count": 1,
#             "Damage": 0,
#             "Name": "minecraft:repeating_command_block",
#             "Slot": 2,
#             "WasPickedUp": 0,
#             "tag": {
#                 "Command": "",
#                 "CustomName": "",
#                 "ExecuteOnFirstTick": 1,
#                 "LPCommandMode": 0,
#                 "LPCondionalMode": 0,
#                 "LPRedstoneMode": 0,
#                 "LastExecution": 0,
#                 "LastOutput": "",
#                 "LastOutputParams": [],
#                 "SuccessCount": 0,
#                 "TickDelay": 0,
#                 "TrackOutput": 1,
#                 "Version": 36,
#                 "auto": 1,
#                 "conditionMet": 1,
#                 "conditionalMode": 0,
#                 "display": {
#                     "Lore": [
#                         "(+DATA)"
#                     ]
#                 },
#                 "powered": 0
#             }
#         },
#         {
#             "Block": {
#                 "name": "minecraft:chain_command_block",
#                 "states": {
#                     "conditional_bit": 0,
#                     "facing_direction": 0
#                 },
#                 "val": 0,
#                 "version": 18100737
#             },
#             "Count": 1,
#             "Damage": 0,
#             "Name": "minecraft:chain_command_block",
#             "Slot": 3,
#             "WasPickedUp": 0,
#             "tag": {
#                 "Command": "good",
#                 "CustomName": "",
#                 "ExecuteOnFirstTick": 0,
#                 "LPCommandMode": 0,
#                 "LPCondionalMode": 0,
#                 "LPRedstoneMode": 0,
#                 "LastExecution": 0,
#                 "LastOutput": "commands.generic.syntax",
#                 "LastOutputParams": [
#                     "",
#                     "good",
#                     ""
#                 ],
#                 "SuccessCount": 0,
#                 "TickDelay": 0,
#                 "TrackOutput": 1,
#                 "Version": 36,
#                 "auto": 1,
#                 "conditionMet": 0,
#                 "conditionalMode": 0,
#                 "display": {
#                     "Lore": [
#                         "(+DATA)"
#                     ]
#                 },
#                 "powered": 0
#             }
#         },
#         {
#             "Block": {
#                 "name": "minecraft:tnt",
#                 "states": {
#                     "allow_underwater_bit": 0,
#                     "explode_bit": 0
#                 },
#                 "val": 0,
#                 "version": 18100737
#             },
#             "Count": 64,
#             "Damage": 0,
#             "Name": "minecraft:tnt",
#             "Slot": 4,
#             "Name": "minecraft:tnt",
#             "Slot": 4,
#             "Slot": 4,
#             "WasPickedUp": 0
#             "WasPickedUp": 0
#         },
#         {
#         },
#         {
#             "Count": 16,
#             "Count": 16,
#             "Damage": 0,
#             "Name": "minecraft:oak_sign",
#             "Slot": 5,
#             "WasPickedUp": 0
#         }
#     ],
#     "id": "Chest",
#     "isMovable": 1,
#     "x": 50,
#     "y": -48,
#     "z": 51
# }

# {
#   "Command": "",
#   "CustomName": "",
#   "ExecuteOnFirstTick": 0,
#   "LPCommandMode": 0,
#   "LPCondionalMode": 0,
#   "LPRedstoneMode": 0,
#   "LastExecution": 0,
#   "LastOutput": "",
#   "LastOutputParams": [],
#   "SuccessCount": 0,
#   "TickDelay": 0,
#   "TrackOutput": 1,
#   "Version": 36,
#   "auto": 0,
#   "conditionMet": 0,
#   "conditionalMode": 0,
#   "id": "CommandBlock",
#   "isMovable": 1,
#   "powered": 0,
#   "x": 80,
#   "y": -60,
#   "z": 6
# }
