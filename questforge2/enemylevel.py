"""Enemy levels of the whole world (Quest > Enemy levels).

Wandering animals and enemies are created by the enemy script: ``CreateEnemy``
in the SDK (``Scripts\\Common\\Enemies.ech``) takes the average hero level,
adds a small per-group offset and then clamps the result per creature type to
the minimum and maximum of ``InitializeEnemyLevels``. A grey wolf therefore
stops at level 10 no matter how strong the hero is.

The compiled script ships those 90 pairs as 32 bit immediates, in the order of
the SDK source: every ``IL`` call pushes its arguments right to left, so
``45, 4, 1, 11`` is bandits (type 11, uses markers, 4 to 45). This module finds
that run in the retail script, writes new values into it and packs the result
as ``Mods\\EnemyLevels.wd`` with a FRESH GUID (the engine keys scripts by
GUID; with the retail one it would silently keep the original).

Both shipped variants are patched: ``TwoWorldsEnemies.eco`` (the single player
campaign) and ``TwoWorldsEnemies16.eco`` (the 1.6 and network path).

Only newly created enemies get the new levels, so a new game is needed; units
already in a save keep what they had.

4.5.0: the same mod can carry ``RPGCompute.eco`` (rpgcompute.py) with the
hero's experience curve times a factor (expcurve.py) and the values of the
enemies per unit (enemystats.py).
"""

import os
import re
import struct
import time
import zlib

from . import questlimit
from .questlimit import (SEP, build_wd, eco_body, reg_backup, reg_mods,
                         reg_set, wd_entries, wd_read_file)

SOURCE_WD = 'Update16.wd'
FALLBACK_WD = 'Update11-15.wd'
MOD_NAME = 'EnemyLevels.wd'
INNER = (SEP.join(('Scripts', 'Campaigns', 'Missions',
                   'TwoWorldsEnemies.eco')),
         SEP.join(('Scripts', 'Campaigns', 'Missions',
                   'TwoWorldsEnemies16.eco')))
MIN_LEVEL = 1
MAX_LEVEL = 100          # the retail maximum (dragons) and a safe ceiling

# (type number, name in the SDK, uses markers, retail min, retail max,
# group, the units the script creates). The unit names give a row the
# name the game itself shows (see game_name): the SDK calls MO_WOLF_04
# a "Gray Wolf" while the game says "Silver Wolf".
# Generated from the SDK: Scripts\\Common\\Enemies.ech,
# InitializeEnemyLevels and the create chain.
ENTRIES = (
    (11, 'Bandit', 1, 4, 45, 'humans', ('BANDIT_01', 'BANDIT_02', 'BANDIT_03', 'BANDIT_04', 'BANDIT_05')),
    (12, 'Bandit Archer', 1, 4, 40, 'humans', ('BANDIT_A_01', 'BANDIT_A_02', 'BANDIT_A_03', 'BANDIT_A_04', 'BANDIT_A_05')),
    (5, 'Black Bear', 0, 7, 15, 'animals', ('MO_BEAR_01',)),
    (28, 'Black Skeleton', 1, 15, 55, 'undead', ('SKELETON_06',)),
    (29, 'Black Skeleton Archer', 1, 15, 55, 'undead', ('SKELETON_06',)),
    (6, 'Brown Bear', 0, 10, 25, 'animals', ('MO_BEAR_02',)),
    (4, 'Boar', 0, 2, 8, 'animals', ('MO_BOAR_01', 'MO_BOAR_02')),
    (21, 'Boss Skeleton', 1, 6, 25, 'undead', ('SKELETON_04',)),
    (14, 'Bro Warrior', 1, 10, 35, 'humans', ('WARRIOR_01', 'WARRIOR_02', 'WARRIOR_03', 'WARRIOR_04', 'WARRIOR_05')),
    (2, 'Brown Wolf', 0, 1, 6, 'animals', ('MO_WOLF_01', 'MO_WOLF_02')),
    (53, 'Cyclope', 0, 30, 55, 'demons', ('MO_CYCLOPE',)),
    (8, 'Daemon 1', 0, 10, 40, 'demons', ('MO_DAEMON_02_1', 'MO_DAEMON_02_2', 'MO_DAEMON_02_3')),
    (9, 'Daemon 2', 0, 25, 60, 'demons', ('MO_DAEMON_01_1', 'MO_DAEMON_01_2')),
    (10, 'Daemon 3', 0, 30, 75, 'demons', ('MO_DAEMON_03_1', 'MO_DAEMON_03_2', 'MO_DAEMON_03_3')),
    (36, 'Dead Knight', 1, 15, 40, 'undead', ('DEADKNIGHT_01', 'DEADKNIGHT_02', 'DEADKNIGHT_03', 'DEADKNIGHT_04', 'DEADKNIGHT_05')),
    (31, 'Dragon', 0, 40, 100, 'dragons', ('DRAGON_01_1',)),
    (18, 'Dwarf', 0, 6, 15, 'humans', ('DWARF_01', 'DWARF_02')),
    (87, 'Ent', 0, 30, 50, 'animals', ('MO_GOLEM_WOOD_02',)),
    (20, 'Ghoul', 0, 6, 30, 'undead', ('MO_GHOUL_01', 'MO_GHOUL_02', 'MO_GHOUL_03', 'MO_GHOUL_04')),
    (92, 'Ghost Dwarf Enemy', 0, 6, 15, 'undead', ('G_DWARF_01',)),
    (41, 'Goblin', 1, 6, 15, 'greenskins', ('GOBLIN_01',)),
    (42, 'Goblin Archer', 1, 6, 15, 'greenskins', ('GOBLIN_01', 'GOBLIN_02', 'GOBLIN_03', 'GOBLIN_04')),
    (43, 'Goblin Mage', 1, 6, 15, 'greenskins', ('GOBLIN_SH_01', 'GOBLIN_SH_02')),
    (39, 'Goblin 2', 1, 3, 12, 'greenskins', ('GOBLIN_02_01', 'GOBLIN_02_02')),
    (40, 'Goblin 2Archer', 1, 3, 12, 'greenskins', ('GOBLIN_02_01', 'GOBLIN_02_02')),
    (60, 'Golem Flesh', 0, 15, 50, 'demons', ('MO_GOLEM_FLESH_01',)),
    (62, 'Golem Steel', 0, 30, 50, 'demons', ('MO_GOLEM_STEEL_01', 'MO_GOLEM_STEEL_02')),
    (63, 'Golem Stone', 0, 30, 50, 'demons', ('MO_GOLEM_STONE_01', 'MO_GOLEM_STONE_02', 'MO_GOLEM_STONE_03', 'MO_GOLEM_STONE_04')),
    (61, 'Golem Wood', 0, 30, 50, 'demons', ('MO_GOLEM_WOOD_01',)),
    (1, 'Gray Wolf', 0, 6, 10, 'animals', ('MO_WOLF_04',)),
    (35, 'Hellmaster', 1, 30, 60, 'demons', ('HELLMASTER_01', 'HELLMASTER_02')),
    (57, 'Hideous', 0, 25, 75, 'demons', ('MO_HIDEOUS_01',)),
    (24, 'Ice Skeleton', 1, 10, 20, 'undead', ('SKELETON_05',)),
    (25, 'Ice Skeleton Archer', 1, 10, 20, 'undead', ('SKELETON_05',)),
    (46, 'Insect Guy', 1, 10, 40, 'dragons', ('INSECTGUY_01', 'INSECTGUY_02', 'INSECTGUY_03', 'INSECTGUY_04', 'INSECTGUY_05', 'INSECTGUY_06', 'INSECTGUY_07', 'INSECTGUY_08', 'INSECTGUY_09')),
    (47, 'Insect Guy Mage', 1, 10, 40, 'dragons', ('INSECTGUY_SH_01', 'INSECTGUY_SH_02')),
    (50, 'Jackal', 1, 15, 40, 'humans', ('JACKAL_01', 'JACKAL_02', 'JACKAL_03', 'JACKAL_04', 'JACKAL_05', 'JACKAL_06', 'JACKAL_07', 'JACKAL_08', 'JACKAL_09')),
    (51, 'Jackal Mage', 1, 15, 40, 'humans', ('JACKAL_SH_01', 'JACKAL_SH_02')),
    (34, 'Lava Dragon', 0, 40, 100, 'dragons', ('DRAGON_02_2',)),
    (59, 'Lizardman', 0, 25, 50, 'dragons', ('MO_SNAKE_01_1', 'MO_SNAKE_01_2', 'MO_SNAKE_01_3', 'MO_SNAKE_01_4', 'MO_SNAKE_01_5')),
    (58, 'Mantis', 0, 25, 50, 'dragons', ('MO_MANTIS_01', 'MO_MANTIS_02', 'MO_MANTIS_03', 'MO_MANTIS_04')),
    (44, 'Minion', 1, 40, 50, 'demons', ('HELLWARIOR', 'MINION_01', 'MINION_02', 'MINION_03', 'MINION_04', 'MINION_05', 'MINION_06', 'MINION_07', 'MINION_08', 'MINION_09', 'MINION_10', 'MINION_11', 'MINION_12', 'MINION_13', 'MINION_14', 'MINION_15', 'MINION_16', 'MINION_17', 'MINION_18', 'MINION_19', 'MINION_20', 'MINION_21')),
    (45, 'Minion Mage', 1, 40, 50, 'demons', ('MINION_SH_01', 'MINION_SH_02')),
    (17, 'Mummy', 0, 30, 50, 'undead', ('MO_MUMMY_01', 'MO_MUMMY_02', 'MO_MUMMY_03')),
    (13, 'Necro', 1, 15, 50, 'undead', ('NECRO_01', 'NECRO_02')),
    (16, 'Oficer 04', 1, 25, 50, 'humans', ('OFICER_04_01',)),
    (52, 'Ogr', 0, 15, 60, 'greenskins', ('MO_OGR',)),
    (79, 'Orc', 1, 10, 30, 'greenskins', ('ORC_01', 'ORC_02', 'ORC_03', 'ORC_04', 'ORC_05', 'ORC_06', 'ORC_07', 'ORC_01B', 'ORC_02B', 'ORC_03B', 'ORC_04B', 'ORC_05B', 'ORC_06B', 'ORC_07B', 'ORC_01C', 'ORC_02C', 'ORC_03C', 'ORC_04C', 'ORC_05C', 'ORC_06C', 'ORC_07C', 'ORC_01D', 'ORC_02D', 'ORC_03D', 'ORC_04D', 'ORC_05D', 'ORC_06D', 'ORC_07D')),
    (83, 'Orc 2', 1, 20, 40, 'greenskins', ('ORC_02_01', 'ORC_02_02', 'ORC_02_03', 'ORC_02_04', 'ORC_02_05', 'ORC_02_01B', 'ORC_02_02B', 'ORC_02_03B', 'ORC_02_04B', 'ORC_02_05B', 'ORC_02_01C', 'ORC_02_02C', 'ORC_02_03C', 'ORC_02_04C', 'ORC_02_05C', 'ORC_02_01D', 'ORC_02_02D', 'ORC_02_03D', 'ORC_02_04D', 'ORC_02_05D')),
    (85, 'Orc 2Archer', 1, 20, 40, 'greenskins', ('ORC_02_01', 'ORC_02_02', 'ORC_02_03', 'ORC_02_04', 'ORC_02_01B', 'ORC_02_02B', 'ORC_02_03B', 'ORC_02_04B', 'ORC_02_01C', 'ORC_02_02C', 'ORC_02_03C', 'ORC_02_04C', 'ORC_02_01D', 'ORC_02_02D', 'ORC_02_03D', 'ORC_02_04D')),
    (84, 'Orc 2Chief', 1, 25, 50, 'greenskins', ('ORC_02_01', 'ORC_02_02', 'ORC_02_03', 'ORC_02_04', 'ORC_02_05', 'ORC_02_01B', 'ORC_02_02B', 'ORC_02_03B', 'ORC_02_04B', 'ORC_02_05B', 'ORC_02_01C', 'ORC_02_02C', 'ORC_02_03C', 'ORC_02_04C', 'ORC_02_05C', 'ORC_02_01D', 'ORC_02_02D', 'ORC_02_03D', 'ORC_02_04D', 'ORC_02_05D')),
    (86, 'Orc 2Shaman', 1, 20, 30, 'greenskins', ()),
    (81, 'Orc Archer', 1, 10, 30, 'greenskins', ('ORC_01', 'ORC_02', 'ORC_03', 'ORC_04', 'ORC_01B', 'ORC_02B', 'ORC_03B', 'ORC_04B', 'ORC_01C', 'ORC_02C', 'ORC_03C', 'ORC_04C', 'ORC_01D', 'ORC_02D', 'ORC_03D', 'ORC_04D')),
    (80, 'Orc Chief', 1, 20, 40, 'greenskins', ('ORC_01', 'ORC_01B', 'ORC_01C', 'ORC_01D')),
    (82, 'Orc Shaman', 1, 10, 30, 'greenskins', ()),
    (68, 'Raptor 1', 0, 3, 8, 'animals', ('MO_RAPTOR_01_1', 'MO_RAPTOR_01_2', 'MO_RAPTOR_01_3', 'MO_RAPTOR_01_4', 'MO_RAPTOR_01_5', 'MO_RAPTOR_01_6', 'MO_RAPTOR_01_7', 'MO_RAPTOR_01_8')),
    (69, 'Raptor 2', 0, 8, 15, 'animals', ('MO_RAPTOR_02_1', 'MO_RAPTOR_02_2', 'MO_RAPTOR_02_3', 'MO_RAPTOR_02_4', 'MO_RAPTOR_02_5', 'MO_RAPTOR_02_6', 'MO_RAPTOR_02_7', 'MO_RAPTOR_02_8')),
    (70, 'Raptor 3', 0, 15, 20, 'animals', ('MO_RAPTOR_03_1', 'MO_RAPTOR_03_2', 'MO_RAPTOR_03_3', 'MO_RAPTOR_03_4', 'MO_RAPTOR_03_5', 'MO_RAPTOR_03_6', 'MO_RAPTOR_03_7', 'MO_RAPTOR_03_8')),
    (71, 'Raptor 4', 0, 20, 25, 'animals', ('MO_RAPTOR_04_1', 'MO_RAPTOR_04_2', 'MO_RAPTOR_04_3', 'MO_RAPTOR_04_4', 'MO_RAPTOR_04_5', 'MO_RAPTOR_04_6', 'MO_RAPTOR_04_7', 'MO_RAPTOR_04_8')),
    (26, 'Red Skeleton', 1, 18, 25, 'undead', ('SKELETON_06',)),
    (27, 'Red Skeleton Archer', 1, 18, 25, 'undead', ('SKELETON_06',)),
    (37, 'Scorpio', 0, 20, 40, 'other', ('MO_SCORPIO_01', 'MO_SCORPIO_02', 'MO_SCORPIO_03', 'MO_SCORPIO_04')),
    (48, 'Sea Guy', 1, 15, 30, 'dragons', ('SEAGUY_01', 'SEAGUY_02', 'SEAGUY_03', 'SEAGUY_04', 'SEAGUY_05', 'SEAGUY_06', 'SEAGUY_07', 'SEAGUY_08', 'SEAGUY_09')),
    (49, 'Sea Guy Mage', 1, 15, 30, 'dragons', ('SEAGUY_SH_01', 'SEAGUY_SH_02')),
    (22, 'Skeleton', 1, 5, 10, 'undead', ('SKELETON_02', 'SKELETON_03')),
    (23, 'Skeleton Archer', 1, 5, 15, 'undead', ('SKELETON_01',)),
    (75, 'Snow Orc', 1, 15, 25, 'greenskins', ('SNOWORC_01_01', 'SNOWORC_01_02', 'SNOWORC_01_03', 'SNOWORC_01_04', 'SNOWORC_01_05', 'SNOWORC_01_01B', 'SNOWORC_01_02B', 'SNOWORC_01_03B', 'SNOWORC_01_04B', 'SNOWORC_01_05B', 'SNOWORC_01_01C', 'SNOWORC_01_02C', 'SNOWORC_01_03C', 'SNOWORC_01_04C', 'SNOWORC_01_05C', 'SNOWORC_01_01D', 'SNOWORC_01_02D', 'SNOWORC_01_03D', 'SNOWORC_01_04D', 'SNOWORC_01_05D')),
    (77, 'Snow Orc Archer', 1, 15, 25, 'greenskins', ('SNOWORC_01_01', 'SNOWORC_01_02', 'SNOWORC_01_03', 'SNOWORC_01_04', 'SNOWORC_01_01B', 'SNOWORC_01_02B', 'SNOWORC_01_03B', 'SNOWORC_01_04B', 'SNOWORC_01_01C', 'SNOWORC_01_02C', 'SNOWORC_01_03C', 'SNOWORC_01_04C', 'SNOWORC_01_01D', 'SNOWORC_01_02D', 'SNOWORC_01_03D', 'SNOWORC_01_04D')),
    (76, 'Snow Orc Chief', 1, 20, 30, 'greenskins', ('SNOWORC_01_01', 'SNOWORC_01_02', 'SNOWORC_01_03', 'SNOWORC_01_04', 'SNOWORC_01_05', 'SNOWORC_01_01B', 'SNOWORC_01_02B', 'SNOWORC_01_03B', 'SNOWORC_01_04B', 'SNOWORC_01_05B', 'SNOWORC_01_01C', 'SNOWORC_01_02C', 'SNOWORC_01_03C', 'SNOWORC_01_04C', 'SNOWORC_01_05C', 'SNOWORC_01_01D', 'SNOWORC_01_02D', 'SNOWORC_01_03D', 'SNOWORC_01_04D', 'SNOWORC_01_05D')),
    (78, 'Snow Orc Shaman', 1, 15, 25, 'greenskins', ()),
    (15, 'Soldier 04', 1, 10, 15, 'humans', ('SOLDIER_04_01', 'SOLDIER_04_02', 'SOLDIER_04_03', 'SOLDIER_04_04')),
    (38, 'Spider', 0, 10, 30, 'animals', ('MO_SPIDER_01', 'MO_SPIDER_02', 'MO_SPIDER_03', 'MO_SPIDER_04')),
    (33, 'Stone Dragon', 0, 40, 90, 'dragons', ('DRAGON_02_1',)),
    (66, 'Undead Bear', 0, 15, 20, 'undead', ('MO_BEAR_03',)),
    (67, 'Undead Reptile', 0, 10, 15, 'undead', ('MO_RAPTOR_01_1',)),
    (64, 'Undead Wolf', 0, 8, 12, 'undead', ('MO_WOLF_05', 'MO_WOLF_06', 'MO_CERBER_01')),
    (72, 'Vyvern 1', 0, 15, 19, 'dragons', ('MO_VYVERN_01',)),
    (73, 'Vyvern 2', 0, 19, 25, 'dragons', ('MO_VYVERN_02',)),
    (74, 'Vyvern 3', 0, 25, 30, 'dragons', ('MO_VYVERN_03',)),
    (30, 'Vyvern 4', 0, 30, 35, 'dragons', ('DRAGON_03_1',)),
    (7, 'White Bear', 0, 20, 25, 'animals', ('MO_BEAR_04',)),
    (3, 'White Wolf', 0, 10, 15, 'animals', ('MO_WOLF_03',)),
    (19, 'Yeti', 0, 25, 40, 'animals', ('MO_YETI_01_1', 'MO_YETI_01_2', 'MO_YETI_01_3', 'MO_YETI_01_4')),
    (54, 'Zombie 1', 0, 5, 10, 'undead', ('MO_ZOMBIE_01', 'MO_ZOMBIE_02', 'MO_ZOMBIE_03')),
    (55, 'Zombie 2', 0, 10, 20, 'undead', ('MO_ZOMBIE_01',)),
    (56, 'Zombie 3', 0, 20, 30, 'undead', ('MO_ZOMBIE_08',)),
    (88, 'Dragonfly', 0, 10, 10, 'animals', ('DRAGONFLY_01', 'DRAGONFLY_02')),
    (89, 'Deadmeat', 0, 15, 20, 'undead', ('DEADMEAT_01', 'DEADMEAT_02')),
    (90, 'Khan', 0, 20, 20, 'humans', ('KHAN_01', 'KHAN_02')),
    (91, 'Skull', 0, 20, 20, 'undead', ('SKULL_01', 'SKULL_02')),
)


# Ghosts live in their own script (Scripts\\Common\\Ghosts.ech,
# GetGhostCreateString): every kind has its own marker
# MARKER_ENEMY_G_* and its own range, the level is
# clamp(hero average + add, min, max). They carry negative numbers
# here so one dict holds both tables.
# (number, name, added to the hero level, retail min, retail max,
# group, units)
GHOSTS = (
    (-1, 'Ghost Bear', 2, 7, 12, 'ghosts', ('G_MO_BEAR_01',)),
    (-2, 'Ghost Boar', 1, 2, 8, 'ghosts', ('G_MO_BOAR_01',)),
    (-3, 'Ghost Wolf', 0, 1, 4, 'ghosts', ('G_MO_WOLF_01',)),
    (-4, 'Ghost Daemon', 0, 20, 30, 'ghosts', ('G_MO_DAEMON_01_1', 'G_MO_DAEMON_02_1', 'G_MO_DAEMON_03_1')),
    (-5, 'Ghost Goblin 1', 0, 6, 10, 'ghosts', ('G_GOBLIN_01',)),
    (-6, 'Ghost Goblin 2', 0, 2, 4, 'ghosts', ('G_GOBLIN_02_02',)),
    (-7, 'Ghost Insect', 0, 20, 25, 'ghosts', ('G_MO_SCORPIO_01',)),
    (-8, 'Ghost Lizardman', 0, 25, 25, 'ghosts', ('G_MO_SNAKE_01',)),
    (-9, 'Ghost Mantis', 0, 10, 25, 'ghosts', ('G_MO_MANTIS_01',)),
    (-10, 'Ghost Reptile', 0, 10, 15, 'ghosts', ('G_MO_RAPTOR_01_1', 'G_MO_RAPTOR_02_1', 'G_MO_RAPTOR_03_1', 'G_MO_RAPTOR_04_1')),
    (-11, 'Ghost Spider', 0, 5, 20, 'ghosts', ('G_MO_SPIDER_01',)),
    (-12, 'Ghost Yeti', 0, 15, 20, 'ghosts', ('G_MO_YETI_01_1',)),
    (-13, 'Ghost Zombie', 0, 5, 12, 'ghosts', ('G_MO_ZOMBIE_01', 'G_MO_ZOMBIE_02', 'G_MO_ZOMBIE_03')),
    (-14, 'Ghost Skeleton', 0, 3, 10, 'ghosts', ('G_SKELETON_01',)),
    (-15, 'Ghost Minion', 0, 20, 25, 'ghosts', ('G_MINION_01',)),
    (-16, 'Ghost Hell Warrior', 0, 20, 25, 'ghosts', ('G_HELLWARIOR',)),
    (-17, 'Ghost Sea Guy', 0, 8, 20, 'ghosts', ('G_SEAGUY_01', 'G_SEAGUY_02', 'G_SEAGUY_03', 'G_SEAGUY_04')),
    (-18, 'Ghost Insect Guy', 0, 10, 20, 'ghosts', ('G_INSECTGUY_01',)),
    (-19, 'Ghost Jackal', 0, 15, 20, 'ghosts', ('G_JACKAL_01',)),
    (-20, 'Ghost Necro', 0, 15, 40, 'ghosts', ('G_NECRO_01', 'G_NECRO_02')),
    (-21, 'Ghost Hellmaster', 0, 30, 40, 'ghosts', ('G_HELLMASTER_01', 'G_HELLMASTER_02')),
    (-22, 'Ghost Dead Knight', 0, 15, 40, 'ghosts', ('G_DEADKNIGHT_01', 'G_DEADKNIGHT_02', 'G_DEADKNIGHT_03', 'G_DEADKNIGHT_04', 'G_DEADKNIGHT_05')),
    (-23, 'Ghost Dwarf', 0, 6, 10, 'ghosts', ('G_DWARF_01',)),
    (-24, 'Ghost Ogr', 0, 15, 20, 'ghosts', ('G_MO_OGR',)),
    (-25, 'Ghost Cyclope', 0, 30, 35, 'ghosts', ('G_MO_CYCLOPE',)),
    (-26, 'Ghost Hideous', 0, 25, 35, 'ghosts', ('G_MO_HIDEOUS_01',)),
    (-27, 'Ghost Mummy', 0, 25, 35, 'ghosts', ('G_MO_MUMMY_01',)),
    (-28, 'Ghost Ghoul', 0, 6, 10, 'ghosts', ('G_MO_GHOUL_01',)),
    (-29, 'Ghost Vyvern', 0, 10, 25, 'ghosts', ('G_MO_VYVERN_01',)),
)


GROUPS = ('animals', 'greenskins', 'humans', 'undead', 'demons', 'dragons',
          'other', 'ghosts')


def all_entries():
    """Enemies and ghosts in one list."""
    return ENTRIES + GHOSTS


def game_name(num, translations):
    """The name the game shows for this row, taken from the language
    file of the installed game ('' when it has none). Units with
    different names are joined, e.g. "Wolf, Gray Wolf"."""
    e = entry(num)
    if e is None or not translations:
        return ''
    out = []
    for unit in e[6]:
        # only the unit itself: a sibling (MO_WOLF_03 -> MO_WOLF_01) would
        # put the wrong name on the row
        text = translations.get('translate' + unit)
        if text and text not in out:
            out.append(text)
    return ', '.join(out[:3])


def entry(type_num):
    for e in all_entries():
        if e[0] == type_num:
            return e
    return None


def retail_values():
    return {e[0]: (e[3], e[4]) for e in all_entries()}


# ---------------------------------------------------------------------------
# finding the table in a compiled script

def _immediates(body):
    out = []
    for m in re.finditer(rb'[\xb8\x68]', body):
        off = m.start()
        if off + 5 <= len(body):
            out.append((off, struct.unpack_from('<I', body, off + 1)[0]))
    return out


LEVEL_CEILING = 200      # sanity check while searching, not a game limit


def _match_at(imms, start):
    """Try to read the whole table beginning at immediate ``start``.
    The anchor is the run of type numbers and marker flags, never the levels
    themselves, so a script that was already changed is still found."""
    out, j = [], start
    for num, _name, mark, _lo, _hi, _grp, _units in ENTRIES:
        width = 4 if mark else 3
        if j + width > len(imms):
            return None
        vals = [v for _, v in imms[j:j + width]]
        if vals[-1] != num or (mark and vals[-2] != mark):
            return None
        hi, lo = vals[0], vals[1]
        if not (0 < lo <= hi <= LEVEL_CEILING):
            return None
        out.append((num, imms[j + 1][0], imms[j][0]))
        j += width
    return out


def locate(body):
    """[(type number, offset of min, offset of max)] in table order.
    Raises ValueError when the script does not carry the known table."""
    imms = _immediates(body)
    first = ENTRIES[0]
    width = 4 if first[2] else 3
    for start in range(len(imms)):
        vals = [v for _, v in imms[start:start + width]]
        if len(vals) < width or vals[-1] != first[0]:
            continue
        hit = _match_at(imms, start)
        if hit:
            return hit
    raise ValueError('enemy level table not found')


def _match_ghosts(imms, start):
    """Read the whole ghost run beginning at immediate ``start``. The
    anchor is what the tool never writes: the value added to the hero
    level (2 for the bear, 1 for the boar, 0 for the rest) and the order
    of the 29 entries."""
    out, j = [], start
    for num, _name, add, _lo, _hi, _grp, _units in GHOSTS:
        hit = None
        for k in range(j, min(j + 8, len(imms) - 2)):
            hi, lo, a = imms[k][1], imms[k + 1][1], imms[k + 2][1]
            if a == add and 0 < lo <= hi <= LEVEL_CEILING:
                hit = k
                break
        if hit is None:
            return None
        out.append((num, imms[hit + 1][0], imms[hit][0]))
        j = hit + 3
    return out


def locate_ghosts(body):
    """[(number, offset of min, offset of max)] of the ghost script
    (Ghosts.ech). Raises ValueError when the run is not in there."""
    imms = _immediates(body)
    for start in range(len(imms) - 2):
        hit = _match_ghosts(imms, start)
        if hit:
            return hit
    raise ValueError('ghost level table not found')


def read_levels(body):
    """{type number: (min, max)} of a compiled script, enemies and the
    ghosts (negative numbers)."""
    out = {}
    spots = list(locate(body))
    try:
        spots += locate_ghosts(body)
    except ValueError:
        pass                      # a script without the ghost part
    for num, off_lo, off_hi in spots:
        out[num] = (struct.unpack_from('<I', body, off_lo + 1)[0],
                    struct.unpack_from('<I', body, off_hi + 1)[0])
    return out


def patch_body(body, values):
    """Write {type: (min, max)} into a copy of the script, enemies and
    ghosts."""
    out = bytearray(body)
    n = 0
    spots = list(locate(body))
    try:
        spots += locate_ghosts(body)
    except ValueError:
        pass
    for num, off_lo, off_hi in spots:
        if num not in values:
            continue
        lo, hi = values[num]
        lo = max(MIN_LEVEL, min(MAX_LEVEL, int(lo)))
        hi = max(lo, min(MAX_LEVEL, int(hi)))
        struct.pack_into('<I', out, off_lo + 1, lo)
        struct.pack_into('<I', out, off_hi + 1, hi)
        n += 1
    return bytes(out), n


# ---------------------------------------------------------------------------
# archive with both scripts

def build_mod_archive(out_path, blobs):
    """blobs: [(inner path, body, resource name[, class id])] -> one WD
    archive with a fresh GUID per entry (class id 4 unless given: the enemy
    scripts; RPGCompute has 25)."""
    import random
    head = zlib.compress(questlimit.WD_MAGIC + random.randbytes(16))
    parts, dir_rows, offset = [head], [], len(head)
    guids = {}
    for inner, body, res, *rest in blobs:
        cid = rest[0] if rest else questlimit.ENTRY_ID
        data = zlib.compress(body)
        parts.append(data)
        guid = random.randbytes(16)
        guids[inner] = guid
        row = bytes([len(inner)]) + inner.encode('ascii')
        row += struct.pack('<BIII', questlimit.ENTRY_FLAGS, offset, len(data),
                           len(body))
        row += bytes([len(res)]) + res
        row += struct.pack('<I', cid)
        row += guid
        dir_rows.append(row)
        offset += len(data)
    filetime = int(time.time() * 10000000) + questlimit.FILETIME_EPOCH
    tab = struct.pack('<QH', filetime, len(dir_rows)) + b''.join(dir_rows)
    cdir = zlib.compress(tab)
    with open(out_path, 'wb') as f:
        for p in parts:
            f.write(p)
        f.write(cdir)
        f.write(struct.pack('<I', len(cdir) + 4))
    return guids


# ---------------------------------------------------------------------------
# state

_BASE_CACHE = {}         # the parsed par values, per archive and date


class State:
    """Where the enemy scripts come from and which levels they carry."""

    def __init__(self, game):
        self.game = game
        self.mods_dir = os.path.join(game, 'Mods') if game else None
        self.mod_path = os.path.join(self.mods_dir, MOD_NAME) if game else None
        self.source = None
        self.sources = {}        # inner path -> (archive, entry)
        self.mod_present = False
        self.mod_active = False
        self.values = {}         # what the game will use
        self.mod_values = {}
        self.others = []         # other mods shipping an enemy script
        self.exp_percent = 100   # hero experience curve the game will use
        self.mod_exp = None      # the percent in our mod (None: not in it)
        self.exp_others = []     # other mods shipping RPGCompute.eco
        self.stats = {}          # {unit: {field: value}} of the mod
        self.floor = True        # a kill is worth at least 0
        self.base = {}           # {unit: {stat: par value}} for the window
        self.base_label = None
        self.base_error = None
        self.error = None
        if game:
            self.read()

    def read(self):
        wdfiles = os.path.join(self.game, 'WDFiles')
        for name in (SOURCE_WD, FALLBACK_WD):
            p = os.path.join(wdfiles, name)
            if not os.path.exists(p):
                continue
            try:
                ents = {e['path']: e for e in wd_entries(p)}
            except Exception:
                continue
            for inner in INNER:
                if inner in ents and inner not in self.sources:
                    self.sources[inner] = (p, ents[inner])
            if self.sources:
                self.source = p
                break
        if INNER[0] not in self.sources:
            self.error = 'nosource'
            return
        try:
            self.values = read_levels(self.retail_body(INNER[0]))
        except Exception as e:
            self.error = str(e)
            return
        switches = reg_mods()
        self.mod_present = os.path.isfile(self.mod_path)
        self.mod_active = bool(switches.get(MOD_NAME, 0))
        if self.mod_present:
            try:
                ents = {e['path']: e for e in wd_entries(self.mod_path)}
                e = ents.get(INNER[0])
                if e:
                    self.mod_values = read_levels(
                        eco_body(wd_read_file(self.mod_path, e)))
            except Exception:
                self.mod_values = {}
        if self.mod_present:
            try:
                from . import rpgcompute
                ents = {e['path']: e for e in wd_entries(self.mod_path)}
                e = ents.get(rpgcompute.INNER)
                got = rpgcompute.read(eco_body(wd_read_file(
                    self.mod_path, e))) if e else None
                if got:
                    self.mod_exp, stats, floor = got
                    if self.mod_active:
                        self.stats, self.floor = stats, floor
            except Exception:
                self.mod_exp = None
        if self.mod_present and self.mod_active and self.mod_values:
            self.values = dict(self.mod_values)
        if self.mod_present and self.mod_active and self.mod_exp:
            self.exp_percent = self.mod_exp
        if not os.path.isdir(self.mods_dir):
            return
        for f in sorted(os.listdir(self.mods_dir)):
            if not f.lower().endswith('.wd') or f == MOD_NAME:
                continue
            try:
                paths = {e['path'] for e in wd_entries(
                    os.path.join(self.mods_dir, f))}
            except Exception:
                continue
            if paths & set(INNER):
                self.others.append((f, bool(switches.get(f, 0))))
            if 'Scripts\\RPGCompute\\RPGCompute.eco' in paths:
                self.exp_others.append((f, bool(switches.get(f, 0))))

    def read_base(self):
        """The par values of the units, for showing what edits come to."""
        from . import enemystats
        try:
            src = enemystats.base_par_source(self.game, own=MOD_NAME)
            if src is None:
                self.base_error = 'nopar'
                return
            key = (src[0], src[1]['offset'], os.path.getmtime(src[0]))
            if _BASE_CACHE.get('key') != key:
                par = enemystats.load_par(src[0], src[1])
                _BASE_CACHE.update(key=key, base=enemystats.read_base(
                    par, enemystats.units()))
            self.base = _BASE_CACHE['base']
            self.base_label = src[2]
        except Exception as e:           # shown in the window
            self.base_error = str(e)

    def retail_body(self, inner):
        arc, e = self.sources[inner]
        return eco_body(wd_read_file(arc, e))

    @property
    def changed(self):
        return self.values != retail_values()


def apply(game, values, log=print, exp_percent=100, stats=None,
          floor=True):
    """Write Mods\\EnemyLevels.wd with the given {type: (min, max)} and,
    when something differs from the game, RPGCompute.eco with the hero's
    experience curve and {unit: {field: value}} of the enemies."""
    st = State(game)
    if st.error:
        raise RuntimeError(st.error)
    blobs = []
    stats = {u: v for u, v in (stats or {}).items() if v}
    rpg = int(exp_percent) != 100 or bool(stats)
    if rpg:
        from . import expcurve, rpgcompute
        why = rpgcompute.usable(game)
        if why != 'ok':
            raise RuntimeError('rpgcompute: ' + why)
        blobs.append(rpgcompute.blob(expcurve.clamp(exp_percent), stats,
                                     floor))
        if int(exp_percent) != 100:
            log(('expcurve', expcurve.clamp(exp_percent)))
        if stats:
            log(('enemystats', len(stats), bool(floor)))
    for inner in INNER:
        if inner not in st.sources:
            continue
        body = st.retail_body(inner)
        patched, n = patch_body(body, values)
        arc, e = st.sources[inner]
        blobs.append((inner, patched, e['res'] or b'Enemies Script'))
        log(('patched', inner.rsplit(SEP, 1)[-1], n,
             os.path.basename(arc)))
    if not blobs:
        raise RuntimeError('nosource')
    bak = reg_backup()
    if bak:
        log(('regbackup', bak))
    if os.path.exists(st.mod_path):
        import shutil
        old = st.mod_path + time.strftime('.vor_%Y-%m-%d_%H-%M-%S')
        shutil.move(st.mod_path, old)
        log(('oldmod', os.path.basename(old)))
    os.makedirs(st.mods_dir, exist_ok=True)
    tmp = st.mod_path + '.neu'
    guids = build_mod_archive(tmp, blobs)
    back = {e['path']: e for e in wd_entries(tmp)}
    for inner, body, res, *rest in blobs:
        e = back.get(inner)
        cid = rest[0] if rest else questlimit.ENTRY_ID
        if (e is None or eco_body(wd_read_file(tmp, e)) != body
                or e['guid'] != guids[inner] or e['res'] != res
                or e['flags'] != questlimit.ENTRY_FLAGS
                or e['id'] != cid):
            os.remove(tmp)
            raise RuntimeError('archive differs after writing')
    os.replace(tmp, st.mod_path)
    reg_set(MOD_NAME, 1)
    log(('written', MOD_NAME, len(blobs),
         guids[INNER[0]].hex()))
    for name, active in st.others:
        if active:
            log(('otheractive', name))
    if rpg:
        for name, active in st.exp_others:
            if active:
                log(('expother', name))
    return len(blobs)


def remove(game, log=print):
    st = State(game)
    bak = reg_backup()
    if bak:
        log(('regbackup', bak))
    if st.mod_present:
        os.remove(st.mod_path)
        log(('removed', MOD_NAME))
    if MOD_NAME in reg_mods():
        reg_set(MOD_NAME, 0)
        log(('switchedoff', MOD_NAME))


# ---------------------------------------------------------------------------
# presets

def preset_follow_hero(values, types=None):
    """No cap: the creature keeps the hero's level (max 100)."""
    out = dict(values)
    for num, _n, _m, lo, hi, _g, _u in all_entries():
        if types is None or num in types:
            out[num] = (MIN_LEVEL, MAX_LEVEL)
    return out


def preset_add(values, plus, types=None):
    """Raise the maximum (and the minimum with it) by ``plus``."""
    out = dict(values)
    for num, _n, _m, lo, hi, _g, _u in all_entries():
        if types is None or num in types:
            cur_lo, cur_hi = out.get(num, (lo, hi))
            out[num] = (min(MAX_LEVEL, cur_lo + plus),
                        min(MAX_LEVEL, cur_hi + plus))
    return out


def preset_scale(values, factor, types=None):
    out = dict(values)
    for num, _n, _m, lo, hi, _g, _u in all_entries():
        if types is None or num in types:
            cur_lo, cur_hi = out.get(num, (lo, hi))
            out[num] = (max(MIN_LEVEL, min(MAX_LEVEL, round(cur_lo * factor))),
                        max(MIN_LEVEL, min(MAX_LEVEL, round(cur_hi * factor))))
    return out


def preset_retail(values, types=None):
    out = dict(values)
    for num, _n, _m, lo, hi, _g, _u in all_entries():
        if types is None or num in types:
            out[num] = (lo, hi)
    return out
