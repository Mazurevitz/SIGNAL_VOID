"""
Projectile System
==================
Projectile lifecycle: spawn, move (via movement_system), collide, destroy.
"""

import math
import random

from .ecs import World
from .components import (
    Position, Velocity, Renderable, Lifetime, CollisionBox,
    Projectile, ProjectileTag, Health, EnemyTag, Knockback,
    HitFlash, PlayerStats, PlayerTag
)
from .engine import (
    NEON_CYAN, NEON_GREEN, NEON_YELLOW, NEON_RED,
    GRAY_MED, GRAY_DARK, WHITE
)


def spawn_projectile(
    world: World,
    x: float, y: float,
    vx: float, vy: float,
    damage: int = 35,
    knockback: float = 0.6,
    max_range: float = 30.0,
    char: str = '\u2022',
    color: int = NEON_CYAN,
    owner_id: int = -1,
) -> int:
    """Spawn a single projectile entity."""
    eid = world.create_entity()

    world.add_component(eid, Position(x, y))
    world.add_component(eid, Velocity(vx, vy))
    world.add_component(eid, Renderable(char=char, color=color, layer=8))
    world.add_component(eid, CollisionBox(0.5, 0.5))
    # Lifetime as safety net (10 seconds at 60fps)
    world.add_component(eid, Lifetime(frames_remaining=600))
    world.add_component(eid, Projectile(
        damage=damage,
        knockback=knockback,
        owner_id=owner_id,
        max_range=max_range,
        weapon_color=color,
    ))
    world.add_component(eid, ProjectileTag())

    return eid


def projectile_system(world: World, renderer, width: int, height: int):
    """
    Update projectiles: track distance, check enemy collision, destroy on wall/range.

    Returns a list of event dicts (for consistency with combat_system).
    """
    from .particles import spawn_directional_burst, spawn_particle

    events = []
    to_destroy = []

    # Get player stats once for damage multiplier / crit
    p_stats = None
    for eid, ps in world.query(PlayerStats):
        if world.has_component(eid, PlayerTag):
            p_stats = ps
            break

    for proj_id, pos, vel, proj in world.query(
        Position, Velocity, Projectile
    ):
        # Track distance traveled this frame
        speed = math.sqrt(vel.x * vel.x + vel.y * vel.y)
        proj.distance_traveled += speed

        # Destroy if past max range
        if proj.distance_traveled >= proj.max_range:
            _spawn_projectile_fizzle(world, pos.x, pos.y, proj.weapon_color)
            to_destroy.append(proj_id)
            continue

        # Destroy if out of bounds
        if pos.x < 1 or pos.x > width - 2 or pos.y < 1 or pos.y > height - 2:
            _spawn_wall_impact(world, pos.x, pos.y, proj.weapon_color)
            to_destroy.append(proj_id)
            continue

        # Check collision with enemies
        hit_enemy = False
        for enemy_id, e_pos, e_health, e_tag in world.query(
            Position, Health, EnemyTag
        ):
            # Skip already-hit enemies (for piercing projectiles)
            if enemy_id in proj.hit_entities:
                continue

            dx = e_pos.x - pos.x
            dy = e_pos.y - pos.y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist < 1.2:  # Hit radius
                # Calculate damage
                base_damage = proj.damage
                is_crit = False

                if p_stats:
                    base_damage = int(base_damage * p_stats.damage_multiplier)
                    if random.random() < p_stats.crit_chance:
                        base_damage = int(base_damage * p_stats.crit_damage_multiplier)
                        is_crit = True

                e_health.current -= base_damage

                # Hit flash
                flash = world.get_component(enemy_id, HitFlash)
                if flash:
                    flash.frames_remaining = 4

                # Apply stun if projectile has stun_frames
                if proj.stun_frames > 0:
                    from .components import Stunned
                    stun = world.get_component(enemy_id, Stunned)
                    if stun is None:
                        world.add_component(enemy_id, Stunned(
                            frames_remaining=proj.stun_frames))
                    else:
                        stun.frames_remaining = max(
                            stun.frames_remaining, proj.stun_frames)

                # Knockback in projectile direction
                if speed > 0:
                    kb_x = vel.x / speed * proj.knockback
                    kb_y = vel.y / speed * proj.knockback
                else:
                    kb_x, kb_y = 0.0, 0.0
                world.add_component(enemy_id, Knockback(kb_x, kb_y, decay=0.7))

                # Hit-stop and shake
                renderer.trigger_hitstop(2)
                renderer.trigger_shake(intensity=1, frames=3)

                # Spawn hit sparks
                if is_crit:
                    spark_colors = [NEON_YELLOW, WHITE, NEON_RED]
                    spark_count = 8
                else:
                    spark_colors = [proj.weapon_color, WHITE, NEON_YELLOW]
                    spark_count = 5

                if speed > 0:
                    spawn_directional_burst(
                        world, e_pos.x, e_pos.y,
                        vel.x / speed, vel.y / speed,
                        count=spark_count,
                        colors=spark_colors,
                        chars=['*', '+', 'x', '.']
                    )

                if proj.piercing:
                    # Piercing: track hit, keep going
                    proj.hit_entities.append(enemy_id)
                    hit_enemy = True
                else:
                    hit_enemy = True
                    to_destroy.append(proj_id)
                    break  # One hit per projectile (non-piercing)

    # Destroy hit/expired projectiles
    for eid in to_destroy:
        if world.is_alive(eid):
            world.destroy_entity(eid)

    return events


def _spawn_projectile_fizzle(world: World, x: float, y: float, color: int):
    """Small fizzle when projectile expires at max range."""
    from .particles import spawn_particle
    for _ in range(3):
        spawn_particle(
            world, x, y,
            vx=random.uniform(-0.3, 0.3),
            vy=random.uniform(-0.3, 0.3),
            char=random.choice(['.', '*', '+']),
            color=color,
            lifetime=random.randint(5, 10),
            gravity=0
        )


def _spawn_wall_impact(world: World, x: float, y: float, color: int):
    """Small spark burst when projectile hits a wall."""
    from .particles import spawn_particle
    for _ in range(4):
        spawn_particle(
            world, x, y,
            vx=random.uniform(-0.5, 0.5),
            vy=random.uniform(-0.5, 0.5),
            char=random.choice(['*', '+', 'x']),
            color=color,
            lifetime=random.randint(6, 12),
            gravity=0.05
        )
