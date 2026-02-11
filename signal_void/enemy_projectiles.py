"""
Enemy Projectile System
========================
Spawning, movement, collision, and rendering of enemy projectiles.
"""

import math
import random

from .ecs import World
from .components import (
    Position, Velocity, Renderable, Lifetime, CollisionBox,
    EnemyProjectileTag, PlayerTag, Health, Invulnerable,
    DashState, Knockback, AttackState, PlayerStats,
    ParticleTag, EnemyTag, SniperState
)
from .engine import NEON_RED, NEON_YELLOW, WHITE, GRAY_DARK
from .particles import spawn_explosion, spawn_particle


def spawn_enemy_projectile(
    world: World,
    x: float, y: float,
    dir_x: float, dir_y: float,
    speed: float = 0.5,
    damage: float = 1,
    visual: str = '\u00b7',
    color: int = NEON_YELLOW,
    lifetime: int = 150,  # 2.5 seconds
    owner_id: int = -1
) -> int:
    """Spawn an enemy projectile entity."""
    eid = world.create_entity()
    world.add_component(eid, Position(x, y))
    world.add_component(eid, Velocity(dir_x * speed, dir_y * speed))
    world.add_component(eid, Renderable(char=visual, color=color, layer=6))
    world.add_component(eid, Lifetime(lifetime))
    world.add_component(eid, CollisionBox(0.8, 0.8))
    world.add_component(eid, EnemyProjectileTag(
        damage=damage, owner_id=owner_id,
        speed=speed, visual=visual
    ))
    return eid


def enemy_projectile_system(world: World, renderer, room_w: int, room_h: int):
    """
    Handle enemy projectile collisions:
    1. Hit player (damage, destroy projectile)
    2. Hit walls (destroy projectile)
    3. Destroyable by player melee attacks
    """
    to_destroy = []

    # Find player
    player_id = None
    p_pos = None
    p_health = None
    for pid, pp, ph, _ in world.query(Position, Health, PlayerTag):
        player_id = pid
        p_pos = pp
        p_health = ph
        break

    if player_id is None or p_pos is None:
        return

    # Check i-frames and dash
    invuln = world.get_component(player_id, Invulnerable)
    dash = world.get_component(player_id, DashState)
    player_invuln = (
        (invuln and invuln.frames_remaining > 0) or
        (dash and dash.frames_remaining > 0)
    )

    # Check if player is attacking (for destroying projectiles)
    attack = world.get_component(player_id, AttackState)
    p_stats = world.get_component(player_id, PlayerStats)

    for eid, proj_pos, proj_tag in world.query(Position, EnemyProjectileTag):
        # Wall collision
        if proj_pos.x < 1 or proj_pos.x > room_w - 1 or proj_pos.y < 1 or proj_pos.y > room_h - 1:
            to_destroy.append(eid)
            continue

        # Player collision
        dx = proj_pos.x - p_pos.x
        dy = proj_pos.y - p_pos.y
        dist = math.sqrt(dx * dx + dy * dy)

        # Player attack can destroy enemy projectiles
        if attack and attack.active and dist < 3.0:
            if not attack.is_beam:
                # Check if projectile is in attack cone
                if dist > 0:
                    ndx, ndy = dx / dist, dy / dist
                    dot = ndx * attack.direction_x + ndy * attack.direction_y
                    if dot > 0.3:
                        to_destroy.append(eid)
                        # Small spark on destroy
                        spawn_particle(
                            world, proj_pos.x, proj_pos.y,
                            vx=random.uniform(-0.3, 0.3),
                            vy=random.uniform(-0.3, 0.3),
                            char='*', color=NEON_YELLOW,
                            lifetime=6, gravity=0
                        )
                        continue

        # Hit player
        if dist < 1.2 and not player_invuln:
            effective_dmg = int(proj_tag.damage)
            if p_stats and p_stats.damage_reduction > 0:
                effective_dmg = max(1, int(effective_dmg * (1 - p_stats.damage_reduction)))
            p_health.current -= effective_dmg
            p_health.current = max(0, p_health.current)

            # I-frames
            iframes = p_stats.invincibility_frames if p_stats else 45
            world.add_component(player_id, Invulnerable(frames_remaining=iframes))

            # Knockback
            if dist > 0:
                kb_x = dx / dist * 0.3
                kb_y = dy / dist * 0.3
            else:
                kb_x, kb_y = 0, -0.3
            world.add_component(player_id, Knockback(kb_x, kb_y, decay=0.7))

            # Impact effect
            renderer.trigger_shake(intensity=1, frames=3)
            spawn_explosion(
                world, p_pos.x, p_pos.y,
                count=4, colors=[NEON_RED, NEON_YELLOW],
                chars=['!', '*'], speed_min=0.2, speed_max=0.5,
                lifetime_min=6, lifetime_max=12, gravity=0
            )

            to_destroy.append(eid)
            continue

    for eid in to_destroy:
        world.destroy_entity(eid)


def render_sniper_beams(world: World, renderer, room_w: int, room_h: int):
    """Render sniper aim lines (tracking/locked) and fire beams."""
    for eid, pos, sniper, enemy_tag in world.query(
        Position, SniperState, EnemyTag
    ):
        if sniper.phase == 'tracking':
            # Dim red dotted aim line tracking player
            _draw_aim_line(
                renderer, pos, sniper,
                room_w, room_h,
                color=52,  # dim red
                dotted=True,
                brightness=min(1.0, sniper.charge_timer / sniper.charge_duration)
            )

        elif sniper.phase == 'locked':
            # Brighter locked aim line — dodge window
            progress = (sniper.charge_timer - (sniper.charge_duration - sniper.lock_time)) / sniper.lock_time
            if int(progress * 10) % 2 == 0:
                color = NEON_RED
            else:
                color = WHITE
            _draw_aim_line(
                renderer, pos, sniper,
                room_w, room_h,
                color=color,
                dotted=True,
                brightness=1.0
            )

        elif sniper.phase == 'firing':
            # Solid bright beam
            _draw_aim_line(
                renderer, pos, sniper,
                room_w, room_h,
                color=WHITE if sniper.fire_frames % 2 == 0 else NEON_RED,
                dotted=False,
                brightness=1.0
            )


def _draw_aim_line(renderer, pos, sniper, room_w, room_h,
                   color=NEON_RED, dotted=True, brightness=1.0):
    """Draw aim line from sniper position along aim direction."""
    dx = sniper.aim_x
    dy = sniper.aim_y
    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return

    # Choose character based on angle
    angle = math.atan2(dy, dx)
    abs_angle = abs(angle)
    if abs_angle < 0.4 or abs_angle > 2.74:
        beam_char = '\u2500'  # ─
    elif abs_angle > 1.17 and abs_angle < 1.97:
        beam_char = '\u2502'  # │
    elif (angle > 0.4 and angle < 1.17) or (angle < -1.97 and angle > -2.74):
        beam_char = '\\'
    else:
        beam_char = '/'

    dot_char = '\u00b7'  # ·

    max_range = max(room_w, room_h)
    for i in range(1, max_range):
        bx = int(pos.x + dx * i)
        by = int(pos.y + dy * i)

        if bx < 1 or bx >= room_w - 1 or by < 1 or by >= room_h - 1:
            break

        if dotted:
            if i % 3 == 0:
                renderer.buffer.put(bx, by, dot_char, color)
        else:
            renderer.buffer.put(bx, by, beam_char, color)
