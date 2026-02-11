"""
Enemy Archetypes
=================
Enemy entity creation and AI behaviors.

Each enemy follows a state-machine pattern:
    idle → detect → [unique behavior] → recover
"""

from typing import Optional
import math
import random

from .ecs import World
from .components import (
    Position, Velocity, Friction, MaxSpeed, Knockback,
    Renderable, CollisionBox, Health, Shield, Damage,
    AIBehavior, AIState, ChargeAttack,
    EnemyTag, SyntaxDrop, HitFlash,
    RangedAttack, SniperState
)
from .engine import NEON_GREEN, NEON_ORANGE, NEON_CYAN, NEON_RED, NEON_YELLOW, WHITE


# =============================================================================
# BUFFER-LEAK (&)
# =============================================================================
# Fast, low mass. Removes verbs on collision. Grants [RECURSIVE] on kill.

def create_buffer_leak(world: World, x: float, y: float) -> int:
    """
    Create a Buffer-Leak enemy.

    Visual: & (green)
    Behavior: Fast chase, lunge at close range
    Drop: [RECURSIVE] - next attack hits twice
    """
    entity_id = world.create_entity()

    world.add_component(entity_id, Position(x, y))
    world.add_component(entity_id, Velocity(0, 0))
    world.add_component(entity_id, Friction(0.9))
    world.add_component(entity_id, MaxSpeed(0.6))
    world.add_component(entity_id, CollisionBox(1.0, 1.0))

    world.add_component(entity_id, Renderable(
        char='&',
        color=NEON_GREEN,
        layer=5
    ))

    world.add_component(entity_id, Health(1, 1))
    world.add_component(entity_id, Damage(10, 0.3))

    world.add_component(entity_id, AIBehavior(
        state=AIState.CHASE,
        detection_range=999.0,
        attack_range=1.5,
        move_speed=0.5,
        behavior_type='chase'
    ))

    world.add_component(entity_id, EnemyTag('buffer_leak'))
    world.add_component(entity_id, SyntaxDrop('RECURSIVE', 'kill'))
    world.add_component(entity_id, HitFlash(0, WHITE))

    return entity_id


# =============================================================================
# FIREWALL ([H])
# =============================================================================
# Slow, high mass, frontal shield. Must be hit from behind. Grants [SUDO].

def create_firewall(world: World, x: float, y: float) -> int:
    """
    Create a Firewall enemy.

    Visual: [H] (orange) - rendered as single char 'H' with box
    Behavior: Intercept pathfinding, shield bash at close range
    Drop: [SUDO] - temporary invincibility
    """
    entity_id = world.create_entity()

    world.add_component(entity_id, Position(x, y))
    world.add_component(entity_id, Velocity(0, 0))
    world.add_component(entity_id, Friction(0.8))
    world.add_component(entity_id, MaxSpeed(0.3))
    world.add_component(entity_id, CollisionBox(1.0, 1.0))

    world.add_component(entity_id, Renderable(
        char='H',
        color=NEON_ORANGE,
        layer=5
    ))

    world.add_component(entity_id, Health(6, 6))
    world.add_component(entity_id, Damage(20, 1.0))
    world.add_component(entity_id, Shield(
        direction='front',
        active=True,
        blocks_damage=True,
        causes_knockback=True,
        knockback_force=1.5
    ))

    world.add_component(entity_id, AIBehavior(
        state=AIState.CHASE,
        detection_range=999.0,
        attack_range=3.0,
        move_speed=0.25,
        behavior_type='guard',
        turn_speed=0.05
    ))

    world.add_component(entity_id, EnemyTag('firewall'))
    world.add_component(entity_id, SyntaxDrop('SUDO', 'backstab'))
    world.add_component(entity_id, HitFlash(0, WHITE))

    return entity_id


# =============================================================================
# OVERCLOCKER (>>)
# =============================================================================
# Charges up, then dashes at player. Grants [DASH] when dodged.

def create_overclocker(world: World, x: float, y: float) -> int:
    """
    Create an Overclocker enemy.

    Visual: >> (cyan/red when charging)
    Behavior: Orbit player, charge attack with shorter telegraph
    Drop: [DASH] - increased move speed
    """
    entity_id = world.create_entity()

    world.add_component(entity_id, Position(x, y))
    world.add_component(entity_id, Velocity(0, 0))
    world.add_component(entity_id, Friction(0.85))
    world.add_component(entity_id, MaxSpeed(0.4))
    world.add_component(entity_id, CollisionBox(1.0, 1.0))

    world.add_component(entity_id, Renderable(
        char='>',
        color=NEON_CYAN,
        layer=5
    ))

    world.add_component(entity_id, Health(2, 2))
    world.add_component(entity_id, Damage(15, 0.8))

    world.add_component(entity_id, AIBehavior(
        state=AIState.CHASE,
        detection_range=999.0,
        attack_range=10.0,
        move_speed=0.3,
        behavior_type='charge'
    ))

    world.add_component(entity_id, ChargeAttack(
        charge_time=48,  # 0.8s (was 1.0s)
        charge_speed=2.0,
        trail_damage=5
    ))

    world.add_component(entity_id, EnemyTag('overclocker'))
    world.add_component(entity_id, SyntaxDrop('DASH', 'dodge'))
    world.add_component(entity_id, HitFlash(0, WHITE))

    return entity_id


# =============================================================================
# SPAMMER (!)
# =============================================================================
# Ranged fodder. Fires slow projectiles, strafes, flees when close.

def create_spammer(world: World, x: float, y: float) -> int:
    """
    Create a Spammer enemy.

    Visual: ! (yellow)
    Behavior: Ranged — maintains distance, fires projectiles, flees if rushed
    Drop: [RECURSIVE] on kill
    """
    entity_id = world.create_entity()

    world.add_component(entity_id, Position(x, y))
    world.add_component(entity_id, Velocity(0, 0))
    world.add_component(entity_id, Friction(0.88))
    world.add_component(entity_id, MaxSpeed(0.5))
    world.add_component(entity_id, CollisionBox(1.0, 1.0))

    world.add_component(entity_id, Renderable(
        char='!',
        color=NEON_YELLOW,
        layer=5
    ))

    world.add_component(entity_id, Health(2, 2))
    world.add_component(entity_id, Damage(5, 0.2))

    world.add_component(entity_id, AIBehavior(
        state=AIState.CHASE,
        detection_range=999.0,
        attack_range=15.0,
        move_speed=0.3,
        behavior_type='spammer'
    ))

    world.add_component(entity_id, RangedAttack(
        cooldown=2.0,
        cooldown_timer=random.uniform(0.5, 1.5),  # Stagger initial fire
        projectile_speed=0.5,
        projectile_damage=1,
        projectile_visual='\u00b7',
        projectile_color=(255, 255, 0),
        telegraph_time=0.3,
    ))

    world.add_component(entity_id, EnemyTag('spammer'))
    world.add_component(entity_id, SyntaxDrop('RECURSIVE', 'kill'))
    world.add_component(entity_id, HitFlash(0, WHITE))

    return entity_id


# =============================================================================
# SNIPER (¦)
# =============================================================================
# Ranged elite. Charges aim line, tracks player, locks, fires hitscan beam.

def create_sniper(world: World, x: float, y: float) -> int:
    """
    Create a Sniper enemy.

    Visual: ¦ (red)
    Behavior: Repositions far, charges aim line tracking player,
              locks direction for 0.5s, fires instant hitscan beam.
    Drop: [DASH] on kill
    """
    entity_id = world.create_entity()

    world.add_component(entity_id, Position(x, y))
    world.add_component(entity_id, Velocity(0, 0))
    world.add_component(entity_id, Friction(0.88))
    world.add_component(entity_id, MaxSpeed(0.35))
    world.add_component(entity_id, CollisionBox(1.0, 1.0))

    world.add_component(entity_id, Renderable(
        char='\u00a6',  # ¦
        color=NEON_RED,
        layer=5
    ))

    world.add_component(entity_id, Health(3, 3))
    world.add_component(entity_id, Damage(15, 0.5))

    world.add_component(entity_id, AIBehavior(
        state=AIState.CHASE,
        detection_range=999.0,
        attack_range=20.0,
        move_speed=0.25,
        behavior_type='sniper'
    ))

    world.add_component(entity_id, SniperState(
        charge_duration=1.5,
        lock_time=0.5,
        fire_cooldown=4.0,
        fire_cooldown_timer=random.uniform(1.0, 2.5),
        beam_damage=3,
    ))

    world.add_component(entity_id, EnemyTag('sniper'))
    world.add_component(entity_id, SyntaxDrop('DASH', 'kill'))
    world.add_component(entity_id, HitFlash(0, WHITE))

    return entity_id


# =============================================================================
# ENEMY SPAWNING
# =============================================================================

def spawn_random_enemy(world: World, x: float, y: float, depth: int = 1) -> int:
    """Spawn a weighted-random enemy type based on room depth."""
    # Deeper rooms shift toward harder enemies
    if depth <= 2:
        weights = [60, 25, 15]  # Mostly buffer-leaks
    elif depth <= 4:
        weights = [40, 35, 25]  # More firewalls
    else:
        weights = [30, 35, 35]  # Even split with more overclockers

    types = ['buffer_leak', 'firewall', 'overclocker']
    enemy_type = random.choices(types, weights=weights, k=1)[0]

    if enemy_type == 'buffer_leak':
        return create_buffer_leak(world, x, y)
    elif enemy_type == 'firewall':
        return create_firewall(world, x, y)
    else:
        return create_overclocker(world, x, y)


def _apply_depth_scaling(world: World, entity_id: int, depth: int):
    """Scale enemy stats based on room depth.

    HP scales by 1.08x per depth past 10 (compounding).
    Damage and speed scale gently so fodder stays satisfying to kill.
    """
    if depth <= 1:
        return

    # HP: only scale after depth 10 (keep fodder as fodder)
    if depth > 10:
        health = world.get_component(entity_id, Health)
        if health:
            hp_mult = 1.08 ** (depth - 10)
            health.maximum = max(health.maximum, int(health.maximum * hp_mult))
            health.current = health.maximum

    # Damage: gentle scaling
    damage_mult = 1.0 + (depth - 1) * 0.08
    damage = world.get_component(entity_id, Damage)
    if damage:
        damage.amount = max(damage.amount, int(damage.amount * damage_mult))

    # Speed: gentle scaling
    speed_mult = 1.0 + (depth - 1) * 0.03
    ai = world.get_component(entity_id, AIBehavior)
    if ai:
        ai.move_speed *= speed_mult

    max_speed = world.get_component(entity_id, MaxSpeed)
    if max_speed:
        max_speed.value *= speed_mult


def spawn_enemies_for_room(
    world: World,
    room_width: int,
    room_height: int,
    count: int = 4,
    player_x: float = 0,
    player_y: float = 0,
    min_distance: float = 10.0,
    depth: int = 1
) -> list:
    """Spawn enemies for a room, avoiding player position."""
    entities = []
    margin = 3

    for _ in range(count):
        # Find valid spawn position
        attempts = 0
        while attempts < 20:
            x = random.uniform(margin, room_width - margin)
            y = random.uniform(margin, room_height - margin)

            # Check distance from player
            dx = x - player_x
            dy = y - player_y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist >= min_distance:
                eid = spawn_random_enemy(world, x, y, depth)
                _apply_depth_scaling(world, eid, depth)
                entities.append(eid)
                break

            attempts += 1

    return entities
