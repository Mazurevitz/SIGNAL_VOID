"""
Weapon Evolution System
========================
Evolution definitions, threshold checking, weapon transformation, and UI.
"""

import math
import random

from .ecs import World
from .components import (
    Position, Velocity, Health, EnemyTag, Knockback,
    HitFlash, Lifetime, Renderable, PlayerTag, PlayerStats,
    WeaponInventory, WeaponComponent
)
from .engine import (
    NEON_CYAN, NEON_MAGENTA, NEON_YELLOW, NEON_GREEN, NEON_RED,
    WHITE, GRAY_DARK, GRAY_MED
)


# =============================================================================
# EVOLUTION DEFINITIONS
# =============================================================================
# Maps base weapon type -> evolution requirements and target type.

WEAPON_EVOLUTIONS = {
    'slash': {
        'evolved_type': 'quicksort',
        'required_upgrade': 'atk_speed',
        'required_stacks': 4,
        'flavor': 'Attack speed threshold reached.',
    },
    'ping': {
        'evolved_type': 'segfault',
        'required_upgrade': 'dmg_up',
        'required_stacks': 4,
        'flavor': 'Damage threshold reached.',
    },
    'fork': {
        'evolved_type': 'ddos',
        'required_upgrade': 'projectile',
        'required_stacks': 2,
        'flavor': 'Projectile saturation reached.',
    },
    'kill9': {
        'evolved_type': 'kernel_panic',
        'required_upgrade': 'crit_chance',
        'required_stacks': 3,
        'flavor': 'Critical mass reached.',
    },
    'rmrf': {
        'evolved_type': 'format_c',
        'required_upgrade': 'atk_size',
        'required_stacks': 3,
        'flavor': 'Attack size threshold reached.',
    },
    'overflow': {
        'evolved_type': 'stack_overflow',
        'required_upgrade': 'max_hp',
        'required_stacks': 4,
        'flavor': 'Stability threshold reached.',
    },
}


# =============================================================================
# EVOLUTION CHECK
# =============================================================================

def check_evolution(weapon: WeaponComponent, stats: PlayerStats):
    """Check if a weapon can evolve. Returns evolution dict or None."""
    if weapon.is_evolved:
        return None

    base = weapon.base_type
    if base not in WEAPON_EVOLUTIONS:
        return None

    evo = WEAPON_EVOLUTIONS[base]
    stacks = stats.upgrade_counts.get(evo['required_upgrade'], 0)

    if stacks >= evo['required_stacks']:
        return evo
    return None


def check_all_evolutions(world: World, player_id: int):
    """Check all player weapons for evolution. Returns list of (weapon_index, evo_data)."""
    stats = world.get_component(player_id, PlayerStats)
    inv = world.get_component(player_id, WeaponInventory)
    if stats is None or inv is None:
        return []

    results = []
    for i, weapon in enumerate(inv.weapons):
        evo = check_evolution(weapon, stats)
        if evo is not None:
            results.append((i, evo))
    return results


def evolve_weapon(weapon: WeaponComponent, evo_data: dict):
    """Transform a weapon into its evolved form."""
    weapon.weapon_type = evo_data['evolved_type']
    weapon.is_evolved = True
    weapon.mod_slots = 3  # All evolved weapons get 3 mod slots


# =============================================================================
# EVOLUTION SCREEN
# =============================================================================

def render_evolution_screen(renderer, weapon: WeaponComponent, evo_data: dict,
                            frame: int):
    """Render the evolution screen overlay."""
    from .weapons import WEAPONS

    width = renderer.width
    height = renderer.game_height

    old_type = weapon.base_type
    new_type = evo_data['evolved_type']
    old_data = WEAPONS.get(old_type, WEAPONS['slash'])
    new_data = WEAPONS.get(new_type, WEAPONS['slash'])

    box_w = 50
    box_h = 13
    bx = width // 2 - box_w // 2
    by = height // 2 - box_h // 2

    # Background
    for y in range(by, by + box_h):
        renderer.buffer.put_string(bx, y, ' ' * box_w, 0)

    # Border
    title_color = NEON_YELLOW
    renderer.buffer.put_string(bx, by,
        '\u250c\u2500\u2500\u2500 COMPILATION COMPLETE '
        + '\u2500' * (box_w - 28) + '\u2510',
        title_color)
    for y in range(by + 1, by + box_h - 1):
        renderer.buffer.put_string(bx, y, '\u2502', title_color)
        renderer.buffer.put_string(bx + box_w - 1, y, '\u2502', title_color)
    renderer.buffer.put_string(bx, by + box_h - 1,
        '\u2514' + '\u2500' * (box_w - 2) + '\u2518', title_color)

    # Evolution arrow
    cy = by + 2
    old_sym = old_data['symbol']
    new_sym = new_data['symbol']
    pulse = (frame // 8) % 2 == 0

    arrow_text = f'    {old_sym}  \u2500\u2500\u2500\u2500\u2500\u2500\u25ba  {new_sym}'
    renderer.buffer.put_string(bx + 3, cy, arrow_text,
                                new_data['color'] if pulse else WHITE)

    # Names
    cy += 1
    name_text = f'    {old_data["name"]:12s}  {new_data["name"]}'
    renderer.buffer.put_string(bx + 3, cy, name_text, GRAY_MED)

    # Flavor text
    cy += 2
    renderer.buffer.put_string(bx + 3, cy,
        f'"{evo_data["flavor"]}"', NEON_YELLOW)
    renderer.buffer.put_string(bx + 3, cy + 1,
        f'{old_data["name"]} evolves into {new_data["name"]}.', GRAY_MED)

    # Description
    cy += 3
    desc = f'{new_sym} {new_data["name"]}: {new_data["description"]}'
    renderer.buffer.put_string(bx + 3, cy, desc[:box_w - 6], new_data['color'])

    # Mod slots upgrade
    cy += 1
    renderer.buffer.put_string(bx + 3, cy, 'Mod slots: 2 \u2192 3', NEON_GREEN)

    # Controls
    cy = by + box_h - 2
    if (frame // 20) % 2 == 0:
        renderer.buffer.put_string(bx + 3, cy,
            '[ENTER] Accept    [ESC] Decline', NEON_CYAN)


# =============================================================================
# SHOCKWAVE SYSTEM (Kernel Panic)
# =============================================================================

class _ShockwaveRing:
    """Expanding shockwave ring from Kernel Panic evolved weapon."""
    def __init__(self, origin_x, origin_y, max_radius=5, damage=30,
                 expand_speed=1.0, color=NEON_RED):
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.current_radius = 0.0
        self.max_radius = max_radius
        self.damage = damage
        self.expand_speed = expand_speed
        self.color = color
        self.hit_entities = set()


def spawn_shockwave(world: World, x: float, y: float,
                    max_radius: int = 5, damage: int = 30):
    """Spawn a shockwave ring entity at the given position."""
    eid = world.create_entity()
    world.add_component(eid, Position(x, y))
    world.add_component(eid, Velocity(0, 0))
    world.add_component(eid, Lifetime(frames_remaining=max_radius + 2))
    world.add_component(eid, _ShockwaveRing(
        origin_x=x, origin_y=y,
        max_radius=max_radius, damage=damage
    ))
    return eid


def shockwave_system(world: World, renderer):
    """Expand shockwave rings, damage enemies at edge, spawn ring particles."""
    from .particles import spawn_particle

    for sw_id, pos, sw in world.query(Position, _ShockwaveRing):
        sw.current_radius += sw.expand_speed

        if sw.current_radius > sw.max_radius:
            continue

        # Spawn ring particles at current radius
        num_points = max(8, int(sw.current_radius * 6))
        for i in range(num_points):
            angle = (2 * math.pi * i) / num_points
            rx = sw.origin_x + math.cos(angle) * sw.current_radius
            ry = sw.origin_y + math.sin(angle) * sw.current_radius
            spawn_particle(
                world, rx, ry,
                vx=math.cos(angle) * 0.1,
                vy=math.sin(angle) * 0.1,
                char=random.choice(['\u2591', '\u2592', '*']),
                color=sw.color,
                lifetime=random.randint(4, 8),
                gravity=0
            )

        # Damage enemies near the ring edge
        for enemy_id, e_pos, e_health, _ in world.query(
            Position, Health, EnemyTag
        ):
            if enemy_id in sw.hit_entities:
                continue
            dx = e_pos.x - sw.origin_x
            dy = e_pos.y - sw.origin_y
            dist = math.sqrt(dx * dx + dy * dy)
            # Hit if near the ring edge (within 1.5 cells)
            if abs(dist - sw.current_radius) < 1.5:
                e_health.current -= sw.damage
                sw.hit_entities.add(enemy_id)

                flash = world.get_component(enemy_id, HitFlash)
                if flash:
                    flash.frames_remaining = 4

                # Knockback outward
                if dist > 0:
                    kb_x = dx / dist * 1.5
                    kb_y = dy / dist * 1.5
                    world.add_component(enemy_id, Knockback(kb_x, kb_y, decay=0.7))
