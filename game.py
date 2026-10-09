#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pixel Parkour (像素跑酷) — 横版无尽跑，像素卡通户外风格。

玩法
----
角色自动向前奔跑，你只需要控制跳跃和下蹲：
  * 跳过地面的岩石、原木、灌木；
  * 下蹲躲开高空飞来的小鸟；
  * 顺手吃掉金币加分；
  * 支持二段跳；跑得越远速度越快，撞到障碍就结束。

操作
----
  跳跃 / 二段跳 / 重开 : 空格 / ↑ / W / 鼠标左键
  下蹲（松开即站起）    : ↓ / S
  退出                  : Esc

本文件是单文件主体，逻辑与渲染分离：
  * Game.update(dt) 是纯逻辑步进，不依赖显示；
  * Game.draw()/present() 才创建并使用 Surface。
这样 selftest.py 可以在无头（SDL dummy）环境下完整驱动。
"""

import os
import sys
import math
import random

import pygame

# ---------------------------------------------------------------------------
# 分辨率：先在低分辨率画布上绘制像素画，再整数倍放大，得到清爽的像素风。
# ---------------------------------------------------------------------------
LW, LH = 320, 180          # 低分辨率逻辑画布
SCALE = 3                  # 放大倍数
DW, DH = LW * SCALE, LH * SCALE   # 实际窗口 960x540
FPS = 60

# 地面（草皮顶部）所在的 y 坐标（低分辨率坐标系）
GROUND_Y = LH - 30

# 物理常量
GRAVITY = 900.0            # px/s^2
JUMP_V = -298.0            # 起跳初速度
BASE_SPEED = 95.0          # 初始水平速度
MAX_SPEED = 250.0          # 最大水平速度
SPEED_K = 0.019            # 速度随距离增长系数

PLAYER_X = 56              # 角色固定横坐标
PLAYER_W = 12
PLAYER_H = 20              # 站立高度
PLAYER_DUCK_H = 12         # 下蹲高度

# 颜色（像素卡通户外调色板）
SKY_TOP = (126, 203, 240)
SKY_MID = (167, 222, 246)
SKY_LOW = (206, 240, 250)
SUN = (255, 236, 150)
CLOUD = (255, 255, 255)
CLOUD_SHADE = (226, 240, 248)
HILL_FAR = (126, 190, 140)
HILL_NEAR = (94, 168, 108)
TREE_TRUNK = (126, 88, 56)
TREE_LEAF = (72, 150, 84)
TREE_LEAF_DK = (56, 126, 70)
DIRT = (158, 110, 72)
DIRT_DK = (132, 90, 58)
GRASS = (98, 184, 96)
GRASS_DK = (74, 156, 78)

# 角色配色
SKIN = (247, 203, 165)
CAP = (226, 92, 76)
CAP_DK = (196, 72, 58)
SHIRT = (66, 132, 214)
SHIRT_DK = (48, 106, 180)
SHORTS = (52, 62, 84)
SHOE = (70, 48, 40)
EYE = (40, 40, 52)

# 障碍 / 道具配色
ROCK = (150, 152, 158)
ROCK_DK = (116, 118, 126)
LOG = (156, 110, 72)
LOG_DK = (120, 82, 52)
BUSH = (60, 140, 78)
BUSH_DK = (44, 112, 62)
BIRD = (240, 168, 66)
BIRD_DK = (214, 132, 40)
BEAK = (250, 200, 90)
COIN = (250, 204, 66)
COIN_DK = (214, 158, 34)
COIN_HI = (255, 240, 170)

WHITE = (255, 255, 255)
BLACK = (24, 26, 34)
GOLD = (255, 208, 70)


# ---------------------------------------------------------------------------
# 障碍定义
# ---------------------------------------------------------------------------
# kind: w, h, flying(相对地面的抬升) , 需要跳跃还是下蹲
OBSTACLES = {
    "rock":  {"w": 13, "h": 11, "fly": 0},
    "log":   {"w": 22, "h": 12, "fly": 0},
    "bush":  {"w": 15, "h": 14, "fly": 0},
    "spike": {"w": 16, "h": 9,  "fly": 0},
    "bird":  {"w": 17, "h": 12, "fly": 14},   # 低空掠过：站立会撞，下蹲可躲
}
GROUND_KINDS = ["rock", "log", "bush", "spike"]


class Entity:
    __slots__ = ("kind", "x", "y", "w", "h", "fly", "taken", "phase")

    def __init__(self, kind, x, y, w, h, fly=0):
        self.kind = kind
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.fly = fly
        self.taken = False
        self.phase = random.random() * math.tau

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))


class Game:
    """跑酷游戏的核心对象。逻辑（update）与渲染（draw/present）分离。"""

    def __init__(self, seed=None, cjk=True):
        self.rng = random.Random(seed)
        self.cjk_pref = cjk
        self._base = None          # 低分辨率画布，惰性创建
        self._font_big = None
        self._font_small = None
        self._cjk_ok = None
        self.best = 0              # 历史最好成绩（本次进程内）
        self.reset()

    # -- 生命周期 ----------------------------------------------------------
    def reset(self):
        self.state = "ready"       # ready / play / dead
        self.dist = 0.0
        self.speed = BASE_SPEED
        self.coins = 0
        self.time = 0.0

        # 玩家
        self.px = PLAYER_X
        self.py = GROUND_Y - PLAYER_H
        self.vy = 0.0
        self.on_ground = True
        self.jumps_left = 2
        self.ducking = False
        self.duck_held = False
        self.run_phase = 0.0
        self.dead_timer = 0.0

        # 实体
        self.obstacles = []
        self.coin_list = []

        # 生成节奏（按距离触发）
        self.next_obstacle_at = 260.0
        self.next_coin_at = 180.0

        # 背景装饰（在 tile 宽度内预生成，绘制时平铺）
        self.bg_off_far = 0.0
        self.bg_off_mid = 0.0
        self.bg_off_near = 0.0
        self.bg_off_ground = 0.0
        self._build_backdrop()

        # 飘字（吃金币 / 得分提示）
        self.popups = []

    # -- 输入接口 ----------------------------------------------------------
    def request_jump(self):
        """边缘触发的跳跃请求（按键按下 / 点击）。"""
        if self.state == "ready":
            self.state = "play"
            self._do_jump()
        elif self.state == "play":
            self._do_jump()
        elif self.state == "dead":
            if self.dead_timer > 0.35:
                self.reset()
                self.state = "play"

    def set_duck(self, on):
        self.duck_held = bool(on)

    def _do_jump(self):
        if self.state != "play":
            return
        if self.jumps_left > 0:
            self.vy = JUMP_V if self.jumps_left == 2 else JUMP_V * 0.86
            self.jumps_left -= 1
            self.on_ground = False
            self.ducking = False
            self._snd("jump")

    # -- 逻辑步进 ----------------------------------------------------------
    def update(self, dt):
        dt = min(dt, 1.0 / 20.0)   # 防止大步长穿模
        self.time += dt

        if self.state == "ready":
            # 待机时也让背景轻微滚动 + 角色原地跑动，画面不死板
            self.run_phase += dt * 10
            self._scroll_backdrop(dt, BASE_SPEED * 0.5)
            self._update_popups(dt)
            return

        if self.state == "dead":
            self.dead_timer += dt
            self._update_popups(dt)
            return

        # --- 正常运行 ---
        self.speed = min(MAX_SPEED, BASE_SPEED + self.dist * SPEED_K)
        move = self.speed * dt
        self.dist += move
        self.run_phase += dt * (6 + self.speed * 0.05)

        # 下蹲：仅在地面生效
        self.ducking = bool(getattr(self, "duck_held", False)) and self.on_ground
        h = PLAYER_DUCK_H if self.ducking else PLAYER_H
        floor = GROUND_Y - h
        # 竖直物理：站在地面时直接吸附到当前身高对应的地面（下蹲/站起脚底不悬空）
        if self.on_ground and self.vy >= 0:
            self.py = floor
            self.vy = 0.0
        else:
            self.vy += GRAVITY * dt
            self.py += self.vy * dt
            if self.py >= floor:
                self.py = floor
                self.vy = 0.0
                self.on_ground = True
                self.jumps_left = 2
            else:
                self.on_ground = False

        self._scroll_backdrop(dt, self.speed)
        self._spawn(move)
        self._move_entities(move, dt)
        self._collide()
        self._update_popups(dt)

    def _scroll_backdrop(self, dt, speed):
        self.bg_off_far = (self.bg_off_far + speed * 0.18 * dt) % self.TILE_FAR
        self.bg_off_mid = (self.bg_off_mid + speed * 0.38 * dt) % self.TILE_MID
        self.bg_off_near = (self.bg_off_near + speed * 0.72 * dt) % self.TILE_NEAR
        self.bg_off_ground = (self.bg_off_ground + speed * dt) % 16

    def _spawn(self, move):
        # 障碍：按时间间隔折算的距离，保证反应时间稳定、且一定可跳过
        if self.dist >= self.next_obstacle_at:
            kind = self._pick_obstacle()
            x0 = LW + 20
            self._add_obstacle(kind, x0)
            cluster_extra = 0.0
            # 低速时偶尔生成“紧邻的一簇”两个地面障碍：视觉上是一个更宽的障碍，
            # 一次跳跃即可整体越过（间距 <= 12px），不会制造无法落地的死局。
            if kind in GROUND_KINDS and self.speed < 150 and self.rng.random() < 0.3:
                d = OBSTACLES[kind]
                off = self.rng.randint(4, 12)
                k2 = self.rng.choice(GROUND_KINDS)
                self._add_obstacle(k2, x0 + d["w"] + off)
                cluster_extra = d["w"] + off + OBSTACLES[k2]["w"]
            t_gap = self.rng.uniform(0.95, 1.7)
            # 净间距 = gap - 障碍宽度；再为“一簇”额外让出簇身长度，
            # 保证任意相邻障碍要么紧邻(<=12px)、要么开阔(>=110px)，无死区。
            gap = max(110.0, self.speed * t_gap) + cluster_extra
            self.next_obstacle_at = self.dist + gap

        # 金币：独立节奏
        if self.dist >= self.next_coin_at:
            self._spawn_coin_pattern(LW + 16)
            self.next_coin_at = self.dist + self.rng.uniform(140, 320)

    def _pick_obstacle(self):
        # 高速时更容易出小鸟（下蹲），低速以地面障碍为主
        r = self.rng.random()
        bird_p = 0.18 + min(0.22, self.dist / 40000.0)
        if r < bird_p:
            return "bird"
        return self.rng.choice(GROUND_KINDS)

    def _add_obstacle(self, kind, x):
        d = OBSTACLES[kind]
        y = GROUND_Y - d["h"] - d["fly"]
        e = Entity(kind, x, y, d["w"], d["h"], d["fly"])
        e.phase = self.rng.random() * math.tau
        self.obstacles.append(e)

    def _spawn_coin_pattern(self, x):
        style = self.rng.random()
        if style < 0.45:
            # 一排水平金币
            n = self.rng.randint(3, 5)
            cy = GROUND_Y - self.rng.choice([16, 26, 38])
            for i in range(n):
                self.coin_list.append(Entity("coin", x + i * 15, cy, 9, 9))
        elif style < 0.8:
            # 拱形（跨越障碍时吃）
            n = 5
            for i in range(n):
                t = i / (n - 1)
                arc = math.sin(t * math.pi) * 34
                self.coin_list.append(Entity("coin", x + i * 14, GROUND_Y - 16 - arc, 9, 9))
        else:
            # 竖直一列（引导二段跳）
            n = self.rng.randint(3, 4)
            for i in range(n):
                self.coin_list.append(Entity("coin", x, GROUND_Y - 16 - i * 13, 9, 9))

    def _move_entities(self, move, dt):
        for o in self.obstacles:
            o.x -= move
            if o.kind == "bird":
                o.phase += dt * 12
        self.obstacles = [o for o in self.obstacles if o.x + o.w > -8]

        for c in self.coin_list:
            c.x -= move
            c.phase += dt * 6
        self.coin_list = [c for c in self.coin_list if c.x + c.w > -8 and not c.taken]

    def _player_hitbox(self, shrink=2):
        h = PLAYER_DUCK_H if self.ducking else PLAYER_H
        return pygame.Rect(int(self.px + shrink), int(self.py + shrink),
                           int(PLAYER_W - shrink * 2), int(h - shrink * 2))

    def _collide(self):
        ph = self._player_hitbox()
        # 金币
        for c in self.coin_list:
            if not c.taken and ph.colliderect(c.rect.inflate(2, 2)):
                c.taken = True
                self.coins += 1
                self._snd("coin")
                self.popups.append([c.x, c.y, "+1", 0.6])
        # 障碍
        for o in self.obstacles:
            or_ = o.rect
            if o.kind == "bird":
                or_ = or_.inflate(-2, -2)
            else:
                or_ = or_.inflate(-3, -2)
            if ph.colliderect(or_):
                self._die()
                break

    def _die(self):
        if self.state != "play":
            return
        self.state = "dead"
        self.dead_timer = 0.0
        score = self.score()
        if score > self.best:
            self.best = score
        self._snd("hit")

    def _update_popups(self, dt):
        for p in self.popups:
            p[1] -= 22 * dt
            p[3] -= dt
        self.popups = [p for p in self.popups if p[3] > 0]

    # -- 计分 --------------------------------------------------------------
    def score(self):
        return int(self.dist // 10) + self.coins * 10

    def meters(self):
        return int(self.dist // 10)

    # -- 音效（可选，纯代码合成，缺 numpy 或音频不可用时静默跳过）----------
    def _snd(self, name):
        snd = self._get_sounds().get(name)
        if snd is not None:
            try:
                snd.play()
            except Exception:
                pass

    def _get_sounds(self):
        if getattr(self, "_sounds", None) is not None:
            return self._sounds
        self._sounds = {}
        try:
            import numpy as np
            if pygame.mixer.get_init() is None:
                return self._sounds
            sr = 22050

            def tone(freq, dur, vol=0.28, kind="square", slide=0.0):
                n = int(sr * dur)
                t = np.linspace(0, dur, n, False)
                f = freq + slide * t
                if kind == "square":
                    wave = np.sign(np.sin(2 * np.pi * f * t))
                else:
                    wave = np.sin(2 * np.pi * f * t)
                env = np.linspace(vol, 0, n) ** 1.5
                data = (wave * env * 32767).astype(np.int16)
                stereo = np.vstack((data, data)).T.flatten()
                return pygame.sndarray.make_sound(stereo)

            self._sounds["jump"] = tone(420, 0.12, slide=520)
            self._sounds["coin"] = tone(880, 0.09, vol=0.22, slide=420)
            self._sounds["hit"] = tone(160, 0.28, vol=0.3, kind="sine", slide=-90)
        except Exception:
            self._sounds = {}
        return self._sounds

    # -- 背景预生成 --------------------------------------------------------
    TILE_FAR = 640
    TILE_MID = 480
    TILE_NEAR = 360

    def _build_backdrop(self):
        rng = random.Random(20240607)
        # 远山
        self.far_hills = []
        x = 0
        while x < self.TILE_FAR:
            w = rng.randint(70, 120)
            h = rng.randint(26, 46)
            self.far_hills.append((x, w, h))
            x += rng.randint(50, 90)
        # 云
        self.clouds = []
        for _ in range(7):
            self.clouds.append((rng.randint(0, self.TILE_FAR),
                                rng.randint(14, 60),
                                rng.randint(18, 34)))
        # 近景丘陵 + 树
        self.near_hills = []
        x = 0
        while x < self.TILE_MID:
            w = rng.randint(60, 100)
            h = rng.randint(18, 34)
            self.near_hills.append((x, w, h))
            x += rng.randint(46, 80)
        self.trees = []
        for _ in range(6):
            self.trees.append((rng.randint(0, self.TILE_NEAR),
                               rng.choice([14, 18, 22])))

    # =====================================================================
    # 渲染
    # =====================================================================
    def _get_base(self):
        if self._base is None:
            self._base = pygame.Surface((LW, LH))
        return self._base

    def draw(self):
        """把当前帧绘制到低分辨率画布并返回它。"""
        s = self._get_base()
        self._draw_sky(s)
        self._draw_far(s)
        self._draw_mid(s)
        self._draw_near(s)
        self._draw_ground(s)
        for c in self.coin_list:
            self._draw_coin(s, c)
        for o in self.obstacles:
            self._draw_obstacle(s, o)
        self._draw_player(s)
        self._draw_popups(s)
        return s

    def present(self, target):
        """把像素画布放大到 target，并在其上绘制 HUD / 覆盖层。"""
        base = self.draw()
        scaled = pygame.transform.scale(base, (DW, DH))
        target.blit(scaled, (0, 0))
        self._draw_hud(target)
        return target

    # -- 各图层 ------------------------------------------------------------
    def _draw_sky(self, s):
        s.fill(SKY_TOP)
        pygame.draw.rect(s, SKY_MID, (0, 46, LW, LH - 46))
        pygame.draw.rect(s, SKY_LOW, (0, 96, LW, LH - 96))
        # 太阳
        pygame.draw.circle(s, SUN, (268, 34), 15)
        pygame.draw.circle(s, (255, 246, 200), (268, 34), 11)

    def _tile_x(self, off, tile_w, x):
        return x - off

    def _draw_far(self, s):
        # 云
        for (cx, cy, cw) in self.clouds:
            for rep in (-1, 0, 1):
                x = self._tile_x(self.bg_off_far, self.TILE_FAR, cx) + rep * self.TILE_FAR
                if -60 < x < LW + 40:
                    self._cloud(s, int(x), cy, cw)
        # 远山
        base_y = GROUND_Y + 4
        for (hx, hw, hh) in self.far_hills:
            for rep in (-1, 0, 1):
                x = self._tile_x(self.bg_off_mid, self.TILE_FAR, hx) + rep * self.TILE_FAR
                if -140 < x < LW + 40:
                    self._hill(s, int(x), base_y, hw, hh, HILL_FAR)

    def _draw_mid(self, s):
        base_y = GROUND_Y + 8
        for (hx, hw, hh) in self.near_hills:
            for rep in (-1, 0, 1):
                x = self._tile_x(self.bg_off_mid, self.TILE_MID, hx) + rep * self.TILE_MID
                if -120 < x < LW + 40:
                    self._hill(s, int(x), base_y, hw, hh, HILL_NEAR)

    def _draw_near(self, s):
        for (tx, th) in self.trees:
            for rep in (-1, 0, 1):
                x = self._tile_x(self.bg_off_near, self.TILE_NEAR, tx) + rep * self.TILE_NEAR
                if -30 < x < LW + 20:
                    self._tree(s, int(x), GROUND_Y + 2, th)

    def _cloud(self, s, x, y, w):
        h = max(6, w // 3)
        pygame.draw.rect(s, CLOUD, (x, y, w, h))
        pygame.draw.rect(s, CLOUD, (x + w // 4, y - h // 2, w // 2, h))
        pygame.draw.rect(s, CLOUD_SHADE, (x, y + h - 2, w, 2))

    def _hill(self, s, x, base_y, w, h, color):
        # 用逐层收窄的矩形堆出像素山丘
        steps = 6
        for i in range(steps):
            t = i / steps
            ww = int(w * (1 - t))
            hh = int(h * (t + 1 / steps))
            xx = x + (w - ww) // 2
            yy = base_y - int(h * (i + 1) / steps)
            pygame.draw.rect(s, color, (xx, yy, ww, int(h / steps) + 2))

    def _tree(self, s, x, base_y, th):
        tw = 4
        pygame.draw.rect(s, TREE_TRUNK, (x, base_y - th, tw, th))
        cw = th + 6
        cy = base_y - th - cw // 2
        pygame.draw.circle(s, TREE_LEAF_DK, (x + tw // 2, cy + 2), cw // 2)
        pygame.draw.circle(s, TREE_LEAF, (x + tw // 2 - 1, cy), cw // 2 - 2)

    def _draw_ground(self, s):
        # 草皮
        pygame.draw.rect(s, GRASS, (0, GROUND_Y, LW, 6))
        pygame.draw.rect(s, GRASS_DK, (0, GROUND_Y + 5, LW, 2))
        # 泥土
        pygame.draw.rect(s, DIRT, (0, GROUND_Y + 7, LW, LH - GROUND_Y - 7))
        # 移动的草丛 / 石子纹理
        off = int(self.bg_off_ground)
        for gx in range(-16, LW + 16, 16):
            x = gx - off
            pygame.draw.rect(s, GRASS, (x, GROUND_Y - 2, 2, 2))
            pygame.draw.rect(s, GRASS_DK, (x + 6, GROUND_Y - 1, 1, 1))
            pygame.draw.rect(s, DIRT_DK, (x + 3, GROUND_Y + 12, 3, 2))
            pygame.draw.rect(s, DIRT_DK, (x + 10, GROUND_Y + 18, 2, 2))

    def _draw_obstacle(self, s, o):
        x, y, w, h = int(o.x), int(o.y), int(o.w), int(o.h)
        if o.kind == "rock":
            pygame.draw.rect(s, ROCK, (x + 1, y + 2, w - 2, h - 2))
            pygame.draw.rect(s, ROCK, (x + 3, y, w - 6, 3))
            pygame.draw.rect(s, ROCK_DK, (x + 1, y + h - 3, w - 2, 3))
            pygame.draw.rect(s, WHITE, (x + 3, y + 3, 2, 2))
        elif o.kind == "log":
            pygame.draw.rect(s, LOG, (x, y + 1, w, h - 1))
            pygame.draw.rect(s, LOG_DK, (x, y + h - 3, w, 3))
            pygame.draw.circle(s, LOG_DK, (x + 3, y + h // 2), 3)
            pygame.draw.circle(s, LOG, (x + 3, y + h // 2), 2)
        elif o.kind == "bush":
            pygame.draw.circle(s, BUSH_DK, (x + w // 2, y + h - 4), w // 2)
            pygame.draw.circle(s, BUSH, (x + w // 2 - 2, y + h // 2), w // 2 - 1)
            pygame.draw.circle(s, BUSH, (x + w // 2 + 3, y + h // 2 + 1), w // 3)
            pygame.draw.rect(s, (240, 120, 140), (x + 4, y + 4, 2, 2))
            pygame.draw.rect(s, (240, 120, 140), (x + w - 6, y + 6, 2, 2))
        elif o.kind == "spike":
            for i in range(3):
                sx = x + i * 5
                pygame.draw.polygon(s, ROCK, [(sx, y + h), (sx + 5, y + h), (sx + 2, y)])
                pygame.draw.polygon(s, ROCK_DK, [(sx + 2, y + h), (sx + 5, y + h), (sx + 2, y)])
        elif o.kind == "bird":
            flap = int(math.sin(o.phase) * 3)
            # 身体
            pygame.draw.rect(s, BIRD, (x + 3, y + 4, w - 6, h - 6))
            pygame.draw.rect(s, BIRD_DK, (x + 3, y + h - 4, w - 6, 2))
            # 头 + 喙
            pygame.draw.rect(s, BIRD, (x + w - 6, y + 2, 6, 6))
            pygame.draw.rect(s, BEAK, (x + w, y + 4, 3, 2))
            pygame.draw.rect(s, EYE, (x + w - 3, y + 3, 1, 1))
            # 翅膀（上下拍动）
            pygame.draw.rect(s, BIRD_DK, (x + 4, y + 2 - flap, 8, 3))

    def _draw_coin(self, s, c):
        x, y = int(c.x), int(c.y)
        wob = abs(math.sin(c.phase))
        w = max(3, int(9 * (0.35 + 0.65 * wob)))
        ox = x + (9 - w) // 2
        pygame.draw.rect(s, COIN_DK, (ox, y, w, 9))
        pygame.draw.rect(s, COIN, (ox, y + 1, w, 7))
        if w >= 6:
            pygame.draw.rect(s, COIN_HI, (ox + 2, y + 2, 2, 3))

    def _draw_player(self, s):
        x = int(self.px)
        y = int(self.py)
        duck = self.ducking
        h = PLAYER_DUCK_H if duck else PLAYER_H

        if self.state == "dead":
            self._draw_player_dead(s, x, y, h)
            return

        # 阴影
        sh_y = GROUND_Y - 1
        sh_w = int(10 - min(6, (GROUND_Y - (y + h)) * 0.12))
        pygame.draw.rect(s, (60, 120, 70), (x + 1, sh_y, max(4, sh_w), 2))

        body_top = y
        leg_phase = math.sin(self.run_phase)
        leg_phase2 = math.sin(self.run_phase + math.pi)

        if duck:
            # 下蹲：整体压扁
            pygame.draw.rect(s, SHIRT, (x, y + 4, 12, 5))          # 身体
            pygame.draw.rect(s, SHIRT_DK, (x, y + 8, 12, 1))
            pygame.draw.rect(s, SKIN, (x + 1, y, 9, 6))            # 头
            pygame.draw.rect(s, CAP, (x, y - 1, 11, 3))            # 帽
            pygame.draw.rect(s, CAP_DK, (x + 8, y, 5, 2))          # 帽檐
            pygame.draw.rect(s, EYE, (x + 7, y + 2, 1, 2))
            pygame.draw.rect(s, SHORTS, (x + 1, y + 9, 10, 2))
            pygame.draw.rect(s, SHOE, (x + 1, y + 11, 4, 1))
            pygame.draw.rect(s, SHOE, (x + 7, y + 11, 4, 1))
            return

        # 腿
        swing = int(leg_phase * 3) if self.on_ground else 2
        swing2 = int(leg_phase2 * 3) if self.on_ground else -2
        pygame.draw.rect(s, SHORTS, (x + 1, y + 12, 10, 4))
        pygame.draw.rect(s, SKIN, (x + 2, y + 16, 3, 3 + swing // 2))
        pygame.draw.rect(s, SKIN, (x + 7, y + 16, 3, 3 + swing2 // 2))
        pygame.draw.rect(s, SHOE, (x + 1, y + 18 + max(0, swing // 2), 4, 2))
        pygame.draw.rect(s, SHOE, (x + 7, y + 18 + max(0, swing2 // 2), 4, 2))
        # 身体
        pygame.draw.rect(s, SHIRT, (x + 1, y + 6, 10, 7))
        pygame.draw.rect(s, SHIRT_DK, (x + 1, y + 11, 10, 2))
        # 手臂（跑步摆动）
        arm = int(leg_phase2 * 3) if self.on_ground else -3
        pygame.draw.rect(s, SKIN, (x + 9, y + 7 + arm // 2, 3, 5))
        # 头
        pygame.draw.rect(s, SKIN, (x + 1, y, 9, 7))
        pygame.draw.rect(s, EYE, (x + 7, y + 3, 1, 2))
        pygame.draw.rect(s, (220, 150, 130), (x + 6, y + 5, 2, 1))   # 腮红/嘴
        # 帽子
        pygame.draw.rect(s, CAP, (x, y - 1, 10, 3))
        pygame.draw.rect(s, CAP_DK, (x + 8, y, 6, 2))                # 帽檐
        pygame.draw.rect(s, CAP_DK, (x + 3, y - 2, 4, 1))

    def _draw_player_dead(self, s, x, y, h):
        # 简单“晕倒”姿态：躺平 + 转圈星星
        pygame.draw.rect(s, SHIRT, (x - 2, GROUND_Y - 8, 12, 6))
        pygame.draw.rect(s, SKIN, (x + 9, GROUND_Y - 10, 7, 6))
        pygame.draw.rect(s, CAP, (x + 8, GROUND_Y - 12, 8, 3))
        pygame.draw.rect(s, SHORTS, (x - 5, GROUND_Y - 7, 5, 5))
        pygame.draw.rect(s, SHOE, (x - 7, GROUND_Y - 6, 3, 3))
        pygame.draw.rect(s, EYE, (x + 12, GROUND_Y - 8, 1, 1))
        pygame.draw.rect(s, EYE, (x + 14, GROUND_Y - 8, 1, 1))
        for i in range(3):
            a = self.time * 6 + i * math.tau / 3
            sx = int(x + 12 + math.cos(a) * 7)
            sy = int(GROUND_Y - 18 + math.sin(a) * 3)
            pygame.draw.rect(s, GOLD, (sx, sy, 2, 2))

    def _draw_popups(self, s):
        for p in self.popups:
            self._tiny_text(s, p[2], int(p[0]), int(p[1]), GOLD)

    # -- 低分辨率小字（手绘点阵，仅用于飘字，够简单）-----------------------
    GLYPHS = {
        "+": ["010", "111", "010"],
        "1": ["010", "010", "111"],
        "2": ["110", "011", "110"],
        "0": ["111", "101", "111"],
    }

    def _tiny_text(self, s, text, x, y, color):
        cx = x
        for ch in text:
            g = self.GLYPHS.get(ch)
            if not g:
                cx += 4
                continue
            for ry, row in enumerate(g):
                for rx, bit in enumerate(row):
                    if bit == "1":
                        s.set_at((cx + rx, y + ry), color)
            cx += 4

    # -- HUD / 覆盖层（绘制在放大后的 target 上，字体清晰）----------------
    def _load_fonts(self):
        if self._font_big is not None:
            return
        big_size, small_size = 56, 26
        font_path = self._find_cjk_font()
        self._cjk_ok = font_path is not None and self.cjk_pref
        try:
            if font_path:
                self._font_big = pygame.font.Font(font_path, big_size)
                self._font_small = pygame.font.Font(font_path, small_size)
            else:
                self._font_big = pygame.font.Font(None, big_size)
                self._font_small = pygame.font.Font(None, small_size)
        except Exception:
            self._font_big = pygame.font.Font(None, big_size)
            self._font_small = pygame.font.Font(None, small_size)
            self._cjk_ok = False

    @staticmethod
    def _find_cjk_font():
        candidates = [
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        try:
            m = pygame.font.match_font("microsoftyahei,simhei,pingfang,wenquanyimicrohei")
            if m:
                return m
        except Exception:
            pass
        return None

    def T(self, zh, en):
        return zh if self._cjk_ok else en

    def _draw_hud(self, t):
        self._load_fonts()
        # 计分板
        panel = pygame.Surface((266, 92), pygame.SRCALPHA)
        panel.fill((20, 26, 40, 130))
        t.blit(panel, (16, 14))

        score = self.score()
        coin_txt = self.T("金币 ", "COINS ") + str(self.coins)
        dist_txt = self.T("距离 ", "DIST ") + str(self.meters()) + "m"
        best_txt = self.T("最佳 ", "BEST ") + str(max(self.best, score))

        t.blit(self._font_small.render(coin_txt, True, GOLD), (28, 20))
        t.blit(self._font_small.render(dist_txt, True, WHITE), (150, 20))
        t.blit(self._font_big.render(str(score), True, WHITE), (26, 40))
        # 右上角最佳
        bs = self._font_small.render(best_txt, True, (200, 220, 255))
        t.blit(bs, (DW - bs.get_width() - 20, 20))

        if self.state == "ready":
            self._center_msg(t,
                             self.T("像素跑酷", "PIXEL PARKOUR"),
                             self.T("空格 / ↑ / 点击  起跳（可二段跳）    ↓ / S  下蹲",
                                    "SPACE / UP / Click = Jump (double)   DOWN / S = Duck"),
                             self.T("按空格开始", "Press SPACE to start"))
        elif self.state == "dead":
            self._center_msg(t,
                             self.T("游戏结束", "GAME OVER"),
                             self.T("本局得分 {}    最佳 {}".format(score, self.best),
                                    "Score {}    Best {}".format(score, self.best)),
                             self.T("按空格重新开始", "Press SPACE to restart"))

    def _center_msg(self, t, title, sub, hint):
        veil = pygame.Surface((DW, DH), pygame.SRCALPHA)
        veil.fill((16, 20, 34, 150))
        t.blit(veil, (0, 0))
        ts = self._font_big.render(title, True, WHITE)
        t.blit(ts, (DW // 2 - ts.get_width() // 2, DH // 2 - 90))
        ss = self._font_small.render(sub, True, (210, 224, 240))
        t.blit(ss, (DW // 2 - ss.get_width() // 2, DH // 2 - 24))
        blink = (self.time * 2) % 2 < 1.3 or self.state == "dead"
        if blink:
            hs = self._font_small.render(hint, True, GOLD)
            t.blit(hs, (DW // 2 - hs.get_width() // 2, DH // 2 + 26))


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
def _jump_key(k):
    return k in (pygame.K_SPACE, pygame.K_UP, pygame.K_w)


def _duck_key(k):
    return k in (pygame.K_DOWN, pygame.K_s)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    autostart = "--autostart" in argv
    autoquit = 0
    if "--autoquit-frames" in argv:
        i = argv.index("--autoquit-frames")
        if i + 1 < len(argv):
            autoquit = int(argv[i + 1])

    pygame.init()
    try:
        pygame.mixer.init()
    except Exception:
        pass
    pygame.display.set_mode((DW, DH))
    pygame.display.set_caption("Pixel Parkour 像素跑酷")
    display = pygame.display.get_surface()
    clock = pygame.time.Clock()
    game = Game()
    if autostart:
        game.request_jump()

    running = True
    frames = 0
    while running:
        dt = clock.tick(FPS) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif _jump_key(e.key):
                    game.request_jump()
                if _duck_key(e.key):
                    game.set_duck(True)
            elif e.type == pygame.KEYUP:
                if _duck_key(e.key):
                    game.set_duck(False)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                game.request_jump()

        # 无头回归时 dt 恒为 0，用固定步长保证逻辑真的推进
        game.update(dt if dt > 0 else 1.0 / FPS)
        game.present(display)
        pygame.display.flip()

        frames += 1
        if autoquit and frames >= autoquit:
            running = False

    pygame.quit()


if __name__ == "__main__":
    # --autostart        : 一进来就起跳（进入 play），供无头回归走真实输入/主循环路径
    # --autoquit-frames N: 跑 N 帧后自动退出
    main()
