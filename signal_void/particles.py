"""
Particle System
================
Braille particle emitter and physics.
"""

import random
import math
from typing import List, Tuple

from .ecs import World
from .components import (
    Position, Velocity, Renderable, Lifetime,
    ParticleTag, Gravity
)
from .engine import (
    NEON_CYAN, NEON_MAGENTA, NEON_YELLOW, NEON_GREEN, NEON_RED, NEON_ORANGE,
    GRAY_LIGHT, GRAY_MED, GRAY_DARK, WHITE
)


def spawn_particle(
    world: World,
    x: float, y: float,
    vx: float, vy: float,
    char: str = '.',
    color: int = WHITE,
    lifetime: int = 20,
    gravity: float = 0.1
) -> int:
    """Spawn a single particle entity."""
    entity_id = world.create_entity()

    world.add_component(entity_id, Position(x, y))
    world.add_component(entity_id, Velocity(vx, vy))
    world.add_component(entity_id, Renderable(char=char, color=color, layer=5))
    world.add_component(entity_id, Lifetime(lifetime))
    world.add_component(entity_id, ParticleTag())

    if gravity > 0:
        world.add_component(entity_id, Gravity(gravity))

    return entity_id


def spawn_explosion(
    world: World,
    x: float, y: float,
    count: int = 15,
    colors: List[int] = None,
    chars: List[str] = None,
    speed_min: float = 0.3,
    speed_max: float = 1.2,
    lifetime_min: int = 15,
    lifetime_max: int = 30,
    gravity: float = 0.1
):
    """Spawn an explosion of particles."""
    if colors is None:
        colors = [WHITE, NEON_YELLOW, GRAY_LIGHT]
    if chars is None:
        chars = ['.', '*', '!', '+', 'x', "'", '`']

    for _ in range(count):
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(speed_min, speed_max)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed - 0.3  # Bias upward

        spawn_particle(
            world, x, y, vx, vy,
            char=random.choice(chars),
            color=random.choice(colors),
            lifetime=random.randint(lifetime_min, lifetime_max),
            gravity=gravity
        )


def spawn_directional_burst(
    world: World,
    x: float, y: float,
    direction_x: float, direction_y: float,
    count: int = 8,
    spread: float = 0.5,
    colors: List[int] = None,
    chars: List[str] = None
):
    """Spawn particles in a directional cone."""
    if colors is None:
        colors = [WHITE, NEON_CYAN]
    if chars is None:
        chars = ['*', '+', '.']

    base_angle = math.atan2(direction_y, direction_x)

    for _ in range(count):
        angle = base_angle + random.uniform(-spread, spread)
        speed = random.uniform(0.5, 1.5)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed

        spawn_particle(
            world, x, y, vx, vy,
            char=random.choice(chars),
            color=random.choice(colors),
            lifetime=random.randint(10, 20),
            gravity=0
        )


def spawn_death_particles_buffer_leak(world: World, x: float, y: float):
    """Green braille sparks for Buffer-Leak death."""
    spawn_explosion(
        world, x, y,
        count=12,
        colors=[NEON_GREEN, 48, 41, WHITE],  # Green shades
        chars=['.', '*', '&', '+'],
        speed_max=1.0,
        gravity=0.05
    )


def spawn_death_particles_firewall(world: World, x: float, y: float):
    """Heavy orange debris for Firewall death."""
    spawn_explosion(
        world, x, y,
        count=20,
        colors=[NEON_ORANGE, NEON_RED, NEON_YELLOW, WHITE],
        chars=['#', '=', '[', ']', 'H', '*'],
        speed_min=0.2,
        speed_max=0.8,
        lifetime_min=20,
        lifetime_max=40,
        gravity=0.15
    )


def spawn_death_particles_overclocker(world: World, x: float, y: float):
    """Electric blue spark explosion for Overclocker death."""
    spawn_explosion(
        world, x, y,
        count=25,
        colors=[NEON_CYAN, 39, 45, WHITE, NEON_MAGENTA],  # Blue/electric
        chars=['>', '<', '*', '+', '~', '^'],
        speed_min=0.5,
        speed_max=1.5,
        lifetime_min=10,
        lifetime_max=25,
        gravity=0.02
    )


def spawn_dash_trail_particle(world: World, x: float, y: float, color: int):
    """Spawn a single dash trail particle."""
    spawn_particle(
        world, x, y,
        vx=random.uniform(-0.1, 0.1),
        vy=random.uniform(-0.1, 0.1),
        char=random.choice(['·', '.', '*']),
        color=color,
        lifetime=8,
        gravity=0
    )


def spawn_logic_blast_wave(world: World, x: float, y: float):
    """
    Spawn an expanding circular wave of ASCII chars for Logic Blast.

    Multiple rings at increasing radii, each moving outward.
    Inner rings are bright magenta, outer rings fade to cyan/gray.
    """
    wave_chars = ['*', '+', 'x', '#', '!', '~', '.']
    ring_configs = [
        # (radius, count, speed, colors, lifetime)
        (1.0, 8, 0.8, [NEON_MAGENTA, WHITE], 18),
        (2.0, 12, 1.0, [NEON_MAGENTA, NEON_CYAN], 22),
        (3.5, 16, 1.2, [NEON_CYAN, NEON_MAGENTA], 26),
        (5.0, 20, 1.4, [NEON_CYAN, 39], 28),
        (7.0, 24, 1.5, [39, GRAY_MED], 30),
    ]

    for radius, count, speed, colors, lifetime in ring_configs:
        for i in range(count):
            angle = (2 * math.pi * i / count) + random.uniform(-0.15, 0.15)
            # Start at initial radius offset
            sx = x + math.cos(angle) * radius * 0.3
            sy = y + math.sin(angle) * radius * 0.3
            # Velocity pushes outward
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed

            spawn_particle(
                world, sx, sy, vx, vy,
                char=random.choice(wave_chars),
                color=random.choice(colors),
                lifetime=lifetime,
                gravity=0
            )
