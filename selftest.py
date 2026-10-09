#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无头自检：在 SDL dummy 驱动下完整驱动 game.py 的逻辑与渲染，验证不崩溃且规则正确。"""

import os
import sys
import subprocess

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
pygame.init()

import game as G  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [ok]   " + name)
    else:
        FAIL += 1
        print("  [FAIL] " + name)


def test_construct():
    g = G.Game(seed=1)
    check("构造 + reset 状态为 ready", g.state == "ready")
    check("玩家初始站在地面", abs(g.py - (G.GROUND_Y - G.PLAYER_H)) < 1e-6 and g.on_ground)
    check("初始速度为 BASE_SPEED", abs(g.speed - G.BASE_SPEED) < 1e-6)


def test_idle_scroll():
    g = G.Game(seed=2)
    before = g.bg_off_near
    for _ in range(30):
        g.update(1 / 60)
    check("待机时背景滚动（画面不死板）", g.bg_off_near != before)
    check("待机不生成障碍", len(g.obstacles) == 0)
    check("待机仍是 ready", g.state == "ready")


def test_jump_and_land():
    g = G.Game(seed=3)
    g.request_jump()                 # ready -> play 并起跳
    check("起跳后进入 play", g.state == "play")
    g.update(1 / 60)                 # 推进一帧让位移生效
    check("起跳后离地", g.py < G.GROUND_Y - G.PLAYER_H)
    top = g.py
    for _ in range(120):
        g.update(1 / 60)
        top = min(top, g.py)
    check("跳跃有明显腾空高度(>30px)", (G.GROUND_Y - G.PLAYER_H) - top > 30)
    check("落地后回到地面且 on_ground", g.on_ground and abs(g.py - (G.GROUND_Y - G.PLAYER_H)) < 1.5)
    check("落地后二段跳次数复位", g.jumps_left == 2)


def test_double_jump():
    g = G.Game(seed=4)
    g.request_jump()                 # 进入 play + 第一跳
    for _ in range(6):
        g.update(1 / 60)
    y1 = g.py
    g.request_jump()                 # 二段跳
    check("二段跳后仍有上升速度", g.vy < 0)
    for _ in range(6):
        g.update(1 / 60)
    check("二段跳把角色抬得更高", g.py < y1)
    g.request_jump()                 # 第三跳应无效
    check("空中第三次跳跃无效(jumps 耗尽)", g.jumps_left == 0)


def test_duck():
    g = G.Game(seed=5)
    g.request_jump()
    g.px = -1000                     # 移出碰撞路径，专心测下蹲
    for _ in range(120):
        g.update(1 / 60)             # 确保落地
    g.set_duck(True)
    g.update(1 / 60)
    check("下蹲时碰撞高度变矮", g.ducking and abs(g.py - (G.GROUND_Y - G.PLAYER_DUCK_H)) < 1.5)
    hb = g._player_hitbox()
    check("下蹲 hitbox 高度≈下蹲高度", abs(hb.height - (G.PLAYER_DUCK_H - 4)) < 1e-6)
    g.set_duck(False)
    g.update(1 / 60)
    check("松开后站起", (not g.ducking) and abs(g.py - (G.GROUND_Y - G.PLAYER_H)) < 1.5)


def test_spawn_and_speed():
    g = G.Game(seed=6)
    g.request_jump()
    g.px = -1000                     # 无人操作，移出碰撞路径以免中途撞死
    seen_ground = seen_bird = False
    max_ent = 0
    for _ in range(60 * 60):         # 跑 60s
        g.update(1 / 60)
        for o in g.obstacles:
            if o.kind == "bird":
                seen_bird = True
            else:
                seen_ground = True
        max_ent = max(max_ent, len(g.obstacles) + len(g.coin_list))
    check("长跑中生成过地面障碍", seen_ground)
    check("长跑中生成过高空小鸟", seen_bird)
    check("速度随时机增长并封顶 MAX_SPEED", abs(g.speed - G.MAX_SPEED) < 1e-6)
    check("实体被回收(内存有界 <=40)", max_ent <= 40)


def test_fairness_gaps():
    """相邻障碍簇间距：要么紧邻(<=13px,一次跳过)，要么开阔(>=55px)，无难处理死区。"""
    g = G.Game(seed=7)
    g.request_jump()
    g.px = -1000                     # 移出碰撞路径，纯测生成间距
    bad = 0
    for _ in range(60 * 30):
        g.update(1 / 60)
        xs = sorted((o.x, o.x + o.w) for o in g.obstacles if o.fly == 0)
        for i in range(1, len(xs)):
            gap = xs[i][0] - xs[i - 1][1]
            if 13 < gap < 55:
                bad += 1
    check("无‘难处理死区间距’(簇要么紧邻要么开阔)", bad == 0)


def test_collision_death():
    g = G.Game(seed=8)
    g.request_jump()
    g.px = -1000
    for _ in range(120):
        g.update(1 / 60)             # 落地
    g.px = G.PLAYER_X                # 归位，摆放受控障碍
    g.obstacles.clear()
    o = G.Entity("rock", g.px - 2, G.GROUND_Y - 11, 13, 11)
    g.obstacles.append(o)
    g.update(1 / 60)
    check("撞上地面障碍 -> dead", g.state == "dead")
    check("dead 后记录 best>0", g.best > 0)
    # 重开
    g.dead_timer = 1.0
    g.request_jump()
    check("结束后可重开 -> play 且状态清空",
          g.state == "play" and len(g.obstacles) == 0 and g.coins == 0)


def test_bird_needs_duck():
    fly = G.OBSTACLES["bird"]["fly"]
    bh = G.OBSTACLES["bird"]["h"]
    bw = G.OBSTACLES["bird"]["w"]
    by = G.GROUND_Y - bh - fly
    # 站立应被撞到
    g = G.Game(seed=9)
    g.request_jump()
    g.px = -1000
    for _ in range(120):
        g.update(1 / 60)
    g.px = G.PLAYER_X
    g.obstacles.clear()
    g.obstacles.append(G.Entity("bird", g.px - 2, by, bw, bh, fly))
    g.update(1 / 60)
    check("站立会被低空小鸟撞到", g.state == "dead")
    # 下蹲应能躲过
    g2 = G.Game(seed=9)
    g2.request_jump()
    g2.px = -1000
    for _ in range(120):
        g2.update(1 / 60)
    g2.px = G.PLAYER_X
    g2.set_duck(True)
    g2.obstacles.clear()
    g2.obstacles.append(G.Entity("bird", g2.px - 2, by, bw, bh, fly))
    g2.update(1 / 60)
    check("下蹲可躲过低空小鸟", g2.state == "play")


def test_coin_collect():
    g = G.Game(seed=10)
    g.request_jump()
    g.px = -1000
    for _ in range(120):
        g.update(1 / 60)
    g.px = G.PLAYER_X
    g.coin_list.clear()
    hb = g._player_hitbox()
    g.coin_list.append(G.Entity("coin", hb.x, hb.y + 2, 9, 9))
    before = g.coins
    g.update(1 / 60)
    check("吃到金币 coins+1 并生成飘字", g.coins == before + 1)
    check("金币计分 = 距离 + coins*10",
          g.score() == int(g.dist // 10) + g.coins * 10)


def test_render():
    g = G.Game(seed=11)
    g.request_jump()
    for _ in range(200):
        g.update(1 / 60)
    base = g.draw()
    check("draw() 返回低分辨率画布", base.get_size() == (G.LW, G.LH))
    target = pygame.Surface((G.DW, G.DH))
    g.present(target)
    check("present() 输出窗口分辨率", target.get_size() == (G.DW, G.DH))
    # 画面不能是纯色（说明背景/角色都画出来了）
    colors = set()
    for yy in range(0, G.DH, 7):
        for xx in range(0, G.DW, 7):
            colors.add(tuple(target.get_at((xx, yy))[:3]))
    check("画面色彩丰富(>15 种采样色)", len(colors) > 15)
    # dead 帧也能渲染
    g.state = "dead"
    g.present(pygame.Surface((G.DW, G.DH)))
    check("dead 覆盖层渲染不崩溃", True)


def test_real_mainloop():
    """用 --autostart --autoquit-frames 跑真实 main()（真事件循环+present），回归输入路径。"""
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run(
        [sys.executable, os.path.join(here, "game.py"),
         "--autostart", "--autoquit-frames", "90"],
        env=env, cwd=here, capture_output=True, timeout=60,
    )
    ok = (r.returncode == 0)
    check("真实 main() 主循环跑 90 帧无异常退出 (rc=0)", ok)
    if not ok:
        print("    stderr:", r.stderr.decode("utf-8", "replace")[-500:])


def main():
    tests = [
        test_construct, test_idle_scroll, test_jump_and_land, test_double_jump,
        test_duck, test_spawn_and_speed, test_fairness_gaps, test_collision_death,
        test_bird_needs_duck, test_coin_collect, test_render, test_real_mainloop,
    ]
    for t in tests:
        print("\n== " + t.__name__ + " ==")
        t()
    print("\n" + "=" * 40)
    print("PASS {} / FAIL {}".format(PASS, FAIL))
    pygame.quit()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
