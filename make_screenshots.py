#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出图脚本：无头渲染若干关键画面到 screenshots/，用于人工核对像素卡通户外效果。"""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
pygame.init()

import game as G  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(OUT, exist_ok=True)


def canvas():
    return pygame.Surface((G.DW, G.DH))


def save(g, name):
    t = canvas()
    g.present(t)
    path = os.path.join(OUT, name)
    pygame.image.save(t, path)
    print("saved", path)


def run_frames(g, n, dt=1 / 60):
    for _ in range(n):
        g.update(dt)


def main():
    # 01 待机界面
    g = G.Game(seed=101)
    run_frames(g, 40)                 # 让背景铺开、角色原地跑
    save(g, "01_ready.png")

    # 02 正常奔跑（地面障碍 + 金币）
    g = G.Game(seed=202)
    g.request_jump()
    run_frames(g, 120)                # 落地并跑一段
    g.obstacles.clear()
    g.coin_list.clear()
    g.obstacles.append(G.Entity("bush", 210, G.GROUND_Y - 14, 15, 14))
    g.obstacles.append(G.Entity("rock", 150, G.GROUND_Y - 11, 13, 11))
    for i in range(4):
        g.coin_list.append(G.Entity("coin", 90 + i * 15, G.GROUND_Y - 40, 9, 9))
    g.update(1 / 60)
    save(g, "02_run.png")

    # 03 跳过原木（腾空瞬间）
    g = G.Game(seed=303)
    g.request_jump()
    run_frames(g, 120)
    g.obstacles.clear()
    g.coin_list.clear()
    g.obstacles.append(G.Entity("log", g.px - 6, G.GROUND_Y - 12, 22, 12))
    # 手动置于跳跃 apex 附近，构图更好看
    g.py = G.GROUND_Y - G.PLAYER_H - 34
    g.vy = -40
    g.on_ground = False
    for i in range(3):
        g.coin_list.append(G.Entity("coin", g.px - 30 + i * 30, G.GROUND_Y - 62, 9, 9))
    g.update(0)                       # 只重算碰撞盒/动画，不推进
    save(g, "03_jump.png")

    # 04 下蹲躲小鸟
    g = G.Game(seed=404)
    g.request_jump()
    run_frames(g, 120)
    g.set_duck(True)
    g.obstacles.clear()
    g.coin_list.clear()
    b = G.OBSTACLES["bird"]
    bird = G.Entity("bird", g.px + 4, G.GROUND_Y - b["h"] - b["fly"], b["w"], b["h"], b["fly"])
    bird.phase = 1.2
    g.obstacles.append(bird)
    g.obstacles.append(G.Entity("spike", 200, G.GROUND_Y - 9, 16, 9))
    g.update(0)
    save(g, "04_duck.png")

    # 05 冲过金币拱形
    g = G.Game(seed=505)
    g.request_jump()
    run_frames(g, 120)
    g.obstacles.clear()
    g.coin_list.clear()
    import math
    for i in range(6):
        t = i / 5
        arc = math.sin(t * math.pi) * 34
        g.coin_list.append(G.Entity("coin", 70 + i * 16, G.GROUND_Y - 16 - arc, 9, 9))
    g.coins = 7
    g.update(1 / 60)
    save(g, "05_coins.png")

    # 06 游戏结束
    g = G.Game(seed=606)
    g.request_jump()
    run_frames(g, 200)
    g.dist = 12345
    g.coins = 18
    g._die()
    run_frames(g, 30)                 # dead 动画
    save(g, "06_gameover.png")

    pygame.quit()
    print("\nAll screenshots written to", OUT)


if __name__ == "__main__":
    main()
