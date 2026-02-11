"""
Weapon Mod System
==================
Mod definitions, hook dispatch, and mod utilities.

Mods attach to weapons (max 2 per weapon) and modify behavior via hooks:
- modify_attack_params: tweak damage/knockback/count before attack
- on_hit: fire after weapon deals damage
- on_kill: fire after weapon kills an enemy
- passive_tick: fire every frame
- modify_projectile_velocity: adjust projectile flight each frame
"""

import math
import random

from .ecs import World
from .components import (
    Position, Velocity, Health, EnemyTag, Knockback,
    HitFlash, Lifetime, Renderable, PlayerTag, PlayerStats,
    WeaponInventory
)
from .engine import (
    NEON_CYAN, NEON_MAGENTA, NEON_YELLOW, NEON_GREEN, NEON_RED,
    NEON_ORANGE, WHITE, GRAY_DARK, GRAY_MED
)


# =============================================================================
# MOD DEFINITIONS
# =============================================================================

WEAPON_MODS = {
    'recursive': {
        'name': '--recursive',
        'description': 'Hits echo once at 50% damage',
        'rarity': 'common',
        'color': NEON_CYAN,
        'hooks': ['on_hit'],
    },
    'force': {
        'name': '--force',
        'description': '3\u00d7 knockback on attacks',
        'rarity': 'common',
        'color': NEON_RED,
        'hooks': ['modify_attack_params'],
    },
    'verbose': {
        'name': '--verbose',
        'description': 'Attacks leave damaging trail (2s)',
        'rarity': 'common',
        'color': NEON_ORANGE,
        'hooks': ['on_attack'],
    },
    'async_mod': {
        'name': '--async',
        'description': 'Auto-fires every 1.5s while moving',
        'rarity': 'rare',
        'color': NEON_GREEN,
        'hooks': ['passive_tick'],
    },
    'grep_mod': {
        'name': '--grep',
        'description': 'Projectiles home toward enemies',
        'rarity': 'common',
        'color': NEON_YELLOW,
        'hooks': ['modify_projectile_velocity'],
    },
    'tee': {
        'name': '| tee',
        'description': 'On kill, fires attack in random dir',
        'rarity': 'rare',
        'color': WHITE,
        'hooks': ['on_kill'],
    },
    'parallel': {
        'name': '--parallel',
        'description': '+1 projectile or +30\u00b0 arc',
        'rarity': 'common',
        'color': NEON_MAGENTA,
        'hooks': ['modify_attack_params'],
    },
    'cron_mod': {
        'name': '--cron',
        'description': 'Every 5th hit deals 3\u00d7 damage',
        'rarity': 'rare',
        'color': NEON_YELLOW,
        'hooks': ['on_hit'],
    },
    'sudo_mod': {
        'name': '--sudo',
        'description': 'Attacks bypass shields and armor',
        'rarity': 'rare',
        'color': NEON_RED,
        'hooks': ['modify_attack_params'],
    },
}


# =============================================================================
# MOD UTILITIES
# =============================================================================

def get_mod_data(mod_id: str) -> dict:
    """Get mod definition by ID."""
    return WEAPON_MODS.get(mod_id, WEAPON_MODS['recursive'])


def weapon_has_mod(weapon, mod_id: str) -> bool:
    """Check if a weapon has a specific mod attached."""
    return mod_id in weapon.mods


def select_mod_offer() -> str:
    """Pick a random mod to offer. Common mods weighted higher."""
    common = [m for m, d in WEAPON_MODS.items() if d['rarity'] == 'common']
    rare = [m for m, d in WEAPON_MODS.items() if d['rarity'] == 'rare']
    # 70% common, 30% rare
    pool = common * 3 + rare
    return random.choice(pool)


def attach_mod(weapon, mod_id: str, slot: int = -1):
    """Attach a mod to a weapon. If slot=-1, append. If slot specified, replace."""
    if slot >= 0 and slot < len(weapon.mods):
        weapon.mods[slot] = mod_id
    else:
        weapon.mods.append(mod_id)


def render_mod_select(renderer, offered_mod_id: str, current_weapons: list,
                      frame: int):
    """Render the mod selection overlay."""
    from .weapons import WEAPONS

    width = renderer.width
    height = renderer.game_height

    mod_data = get_mod_data(offered_mod_id)

    box_w = 47
    box_h = 13
    bx = width // 2 - box_w // 2
    by = height // 2 - box_h // 2

    # Draw box background
    for y in range(by, by + box_h):
        renderer.buffer.put_string(bx, y, ' ' * box_w, 0)

    # Borders
    renderer.buffer.put_string(bx, by,
        '\u250c\u2500\u2500\u2500 PATCH AVAILABLE ' + '\u2500' * (box_w - 20) + '\u2510',
        NEON_MAGENTA)
    for y in range(by + 1, by + box_h - 1):
        renderer.buffer.put_string(bx, y, '\u2502', NEON_MAGENTA)
        renderer.buffer.put_string(bx + box_w - 1, y, '\u2502', NEON_MAGENTA)
    renderer.buffer.put_string(bx, by + box_h - 1,
        '\u2514' + '\u2500' * (box_w - 2) + '\u2518', NEON_MAGENTA)

    # Found mod
    cy = by + 2
    pulse = (frame // 8) % 2 == 0
    m_color = mod_data['color'] if pulse else WHITE
    renderer.buffer.put_string(bx + 3, cy, f'Found:  {mod_data["name"]}', m_color)
    renderer.buffer.put_string(bx + 3, cy + 1,
        f'"{mod_data["description"]}"', GRAY_MED)

    # Attach to options
    cy = by + 5
    renderer.buffer.put_string(bx + 3, cy, 'Attach to:', GRAY_MED)
    cy += 1

    for i, w in enumerate(current_weapons):
        wdata = WEAPONS.get(w.weapon_type, WEAPONS['slash'])
        mod_count = len(w.mods)
        mod_max = w.mod_slots

        mod_names = ', '.join(get_mod_data(m)['name'] for m in w.mods) if w.mods else ''
        mod_info = f'({mod_count}/{mod_max} mods'
        if mod_names:
            mod_info += f': {mod_names}'
        mod_info += ')'

        text = f'[{i+1}] {wdata["name"]} {wdata["symbol"]}  {mod_info}'
        renderer.buffer.put_string(bx + 3, cy + i, text, wdata['color'])

    renderer.buffer.put_string(bx + 3, cy + len(current_weapons) + 1,
        '[ESC] Discard', GRAY_DARK)

    # Hint
    renderer.buffer.put_string(bx + 3, by + box_h - 2,
        'Press 1, 2, or ESC', GRAY_MED)


# =============================================================================
# HOOK: modify_attack_params
# =============================================================================

def apply_mod_params(weapon, params: dict) -> dict:
    """
    Apply modify_attack_params hooks from weapon mods.

    `params` dict has: damage, knockback, projectile_count, arc_angle, etc.
    Returns modified params dict.
    """
    for mod_id in weapon.mods:
        if mod_id == 'force':
            params['knockback'] = params.get('knockback', 1.0) * 3.0
        elif mod_id == 'parallel':
            if params.get('projectile_count', 0) > 0:
                params['projectile_count'] = params.get('projectile_count', 0) + 1
            else:
                params['arc_angle'] = params.get('arc_angle', 90) + 30
        elif mod_id == 'sudo_mod':
            params['ignore_shield'] = True
    return params


# =============================================================================
# HOOK: on_hit
# =============================================================================

def fire_on_hit(world: World, weapon, enemy_id: int, hit_pos: tuple,
                damage: int, direction: tuple, renderer, is_echo: bool = False):
    """
    Fire on_hit hooks for weapon mods.

    Called after damage is dealt to an enemy.
    `is_echo` prevents recursive echoes from triggering further echoes.
    """
    for mod_id in weapon.mods:
        if mod_id == 'recursive' and not is_echo:
            _schedule_echo_attack(
                world, hit_pos, damage, direction, weapon, renderer
            )
        elif mod_id == 'cron_mod':
            weapon.hit_counter += 1
            if weapon.hit_counter >= 5:
                weapon.hit_counter = 0
                _cron_burst(world, enemy_id, damage, renderer)


def _schedule_echo_attack(world, hit_pos, damage, direction, weapon, renderer):
    """Schedule an echo attack at 50% damage after 18 frames (0.3s)."""
    from .components import Lifetime, Position, Renderable
    from .particles import spawn_particle

    echo_damage = max(1, damage // 2)
    ex, ey = hit_pos

    # Create a delayed-damage entity
    eid = world.create_entity()
    world.add_component(eid, Position(ex, ey))
    world.add_component(eid, Velocity(0, 0))
    world.add_component(eid, Lifetime(frames_remaining=18))
    world.add_component(eid, _EchoMarker(
        damage=echo_damage,
        direction_x=direction[0],
        direction_y=direction[1],
        radius=2.5,
    ))

    # Preview visual: dim sparkle at echo location
    spawn_particle(
        world, ex, ey,
        vx=0, vy=0,
        char='*',
        color=GRAY_MED,
        lifetime=18,
        gravity=0
    )


def _cron_burst(world, enemy_id, damage, renderer):
    """Cron mod: 5th hit bonus — extra screen shake + visual."""
    from .particles import spawn_explosion
    pos = world.get_component(enemy_id, Position)
    if pos:
        # Extra damage already applied by caller (3x in combat_system)
        renderer.trigger_shake(intensity=3, frames=5)
        spawn_explosion(
            world, pos.x, pos.y,
            count=10,
            colors=[WHITE, NEON_YELLOW, NEON_RED],
            chars=['!', '*', '#', '+'],
            speed_min=0.5, speed_max=1.2,
            lifetime_min=10, lifetime_max=20,
            gravity=0
        )


# =============================================================================
# HOOK: on_kill
# =============================================================================

def fire_on_kill(world: World, weapon, enemy_id: int, kill_pos: tuple,
                 renderer, chain_depth: int = 0):
    """Fire on_kill hooks for weapon mods."""
    for mod_id in weapon.mods:
        if mod_id == 'tee' and chain_depth < 3:
            _tee_copy_attack(world, kill_pos, weapon, renderer, chain_depth)


def _tee_copy_attack(world, kill_pos, weapon, renderer, chain_depth):
    """| tee: fire a copy attack in a random direction from kill position."""
    from .weapons import get_weapon_data
    from .particles import spawn_directional_burst

    data = get_weapon_data(weapon)
    angle = random.uniform(0, math.pi * 2)
    dx = math.cos(angle)
    dy = math.sin(angle)
    ex, ey = kill_pos

    # Deal 50% damage to enemies in a small radius
    half_damage = max(1, data.get('damage', 10) // 2)
    for eid, e_pos, e_health, _ in world.query(Position, Health, EnemyTag):
        ddx = e_pos.x - ex
        ddy = e_pos.y - ey
        dist = math.sqrt(ddx * ddx + ddy * ddy)
        if dist < 3.0:
            # Direction check (loose cone)
            if dist > 0:
                ndx, ndy = ddx / dist, ddy / dist
                dot = ndx * dx + ndy * dy
                if dot < 0.0:
                    continue
            e_health.current -= half_damage

            flash = world.get_component(eid, HitFlash)
            if flash:
                flash.frames_remaining = 4

            # Chain kill check
            if e_health.current <= 0 and chain_depth < 3:
                fire_on_kill(world, weapon, eid, (e_pos.x, e_pos.y),
                             renderer, chain_depth + 1)

    # Visual: directional burst from kill point
    spawn_directional_burst(
        world, ex, ey, dx, dy,
        count=5,
        colors=[GRAY_MED, WHITE],
        chars=['.', '*', '+']
    )


# =============================================================================
# ECHO ATTACK SYSTEM
# =============================================================================

class _EchoMarker:
    """Marker component for delayed echo attacks. Not a real component — stored directly."""
    def __init__(self, damage=10, direction_x=0, direction_y=0, radius=2.5):
        self.damage = damage
        self.direction_x = direction_x
        self.direction_y = direction_y
        self.radius = radius


def echo_attack_system(world: World, renderer):
    """
    Process expired echo markers — deal delayed damage in an area.
    Called each frame from main update loop.
    """
    from .particles import spawn_directional_burst

    dead_echoes = []
    for eid, pos, lifetime in world.query(Position, Lifetime):
        marker = world.get_component(eid, _EchoMarker)
        if marker is None:
            continue

        # Only fire when lifetime is about to expire (1 frame left)
        if lifetime.frames_remaining > 1:
            continue

        # Deal echo damage to nearby enemies
        for enemy_id, e_pos, e_health, _ in world.query(Position, Health, EnemyTag):
            dx = e_pos.x - pos.x
            dy = e_pos.y - pos.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > marker.radius:
                continue
            # Direction check (loose cone)
            if dist > 0:
                ndx, ndy = dx / dist, dy / dist
                dot = ndx * marker.direction_x + ndy * marker.direction_y
                if dot < 0.0:
                    continue

            e_health.current -= marker.damage

            flash = world.get_component(enemy_id, HitFlash)
            if flash:
                flash.frames_remaining = 3

            # Dim spark
            spawn_directional_burst(
                world, e_pos.x, e_pos.y,
                marker.direction_x, marker.direction_y,
                count=3,
                colors=[GRAY_MED, GRAY_DARK],
                chars=['*', '+', '.']
            )

        # Echo visual
        spawn_directional_burst(
            world, pos.x, pos.y,
            marker.direction_x, marker.direction_y,
            count=4,
            colors=[GRAY_MED, NEON_CYAN],
            chars=['/', '\\', '*']
        )

        renderer.trigger_shake(intensity=1, frames=2)


# =============================================================================
# HOOK: on_attack (--verbose ground trail)
# =============================================================================

class _GroundHazard:
    """Marker for ground hazard that damages enemies standing on it."""
    def __init__(self, damage=1, tick_rate=60, color=NEON_ORANGE):
        self.damage = damage
        self.tick_rate = tick_rate  # Frames between damage ticks
        self.tick_timer = 0
        self.color = color


def fire_on_attack(world: World, weapon, attack_pos: tuple,
                   direction: tuple, pattern: str, renderer):
    """Fire on_attack hooks for weapon mods."""
    for mod_id in weapon.mods:
        if mod_id == 'verbose':
            _spawn_ground_trail(world, attack_pos, direction, pattern, weapon)


def _spawn_ground_trail(world, attack_pos, direction, pattern, weapon):
    """--verbose: spawn ground hazard entities along attack path."""
    from .weapons import get_weapon_data
    data = get_weapon_data(weapon)
    color = data.get('color', NEON_ORANGE)

    ax, ay = attack_pos
    dx, dy = direction

    if pattern in ('melee_arc', 'melee_slam', 'melee_sweep'):
        # Melee: trail at attack point and nearby cells
        radius = data.get('radius', 3.0)
        for i in range(int(radius) + 1):
            _create_hazard(world, ax + dx * i, ay + dy * i, color)
    else:
        # Projectile/beam: trail at origin only (projectile trails handled separately)
        _create_hazard(world, ax + dx, ay + dy, color)


def _create_hazard(world, x, y, color):
    """Create a single ground hazard entity."""
    eid = world.create_entity()
    world.add_component(eid, Position(x, y))
    world.add_component(eid, Velocity(0, 0))
    world.add_component(eid, Renderable(char='.', color=color, layer=1, visible=True))
    world.add_component(eid, Lifetime(frames_remaining=120))  # 2 seconds
    world.add_component(eid, _GroundHazard(damage=1, color=color))


def ground_hazard_system(world: World):
    """Tick ground hazards — damage enemies standing on them."""
    for haz_id, h_pos, hazard, lifetime in world.query(
        Position, _GroundHazard, Lifetime
    ):
        hazard.tick_timer += 1
        if hazard.tick_timer < hazard.tick_rate:
            continue
        hazard.tick_timer = 0

        # Check enemies on this tile
        for enemy_id, e_pos, e_health, _ in world.query(Position, Health, EnemyTag):
            dx = e_pos.x - h_pos.x
            dy = e_pos.y - h_pos.y
            if abs(dx) < 1.0 and abs(dy) < 1.0:
                e_health.current -= hazard.damage


# =============================================================================
# HOOK: passive_tick (--async auto-fire)
# =============================================================================

class _AsyncTimer:
    """Tracks per-weapon auto-fire timer for --async mod."""
    def __init__(self):
        self.timer = 0


def async_mod_system(world: World, renderer):
    """
    --async: auto-fire weapon every 90 frames (1.5s) while player is moving.
    Called each frame from main update loop.
    """
    from .weapons import execute_weapon_attack, get_active_weapon, get_weapon_data
    from .components import PlayerControlled

    for pid, _, ctrl in world.query(PlayerTag, PlayerControlled):
        inv = world.get_component(pid, WeaponInventory)
        if inv is None or not inv.weapons:
            continue

        weapon = inv.weapons[min(inv.active_index, len(inv.weapons) - 1)]
        if 'async_mod' not in weapon.mods:
            continue

        # Skip beam weapons (continuous can't auto-fire)
        data = get_weapon_data(weapon)
        if data.get('pattern') == 'beam_continuous':
            continue

        # Get or create timer
        timer = world.get_component(pid, _AsyncTimer)
        if timer is None:
            timer = _AsyncTimer()
            world.add_component(pid, timer)

        # Check if moving
        vel = world.get_component(pid, Velocity)
        if vel is None or (abs(vel.x) < 0.05 and abs(vel.y) < 0.05):
            return

        timer.timer += 1
        if timer.timer >= 90:  # 1.5s at 60fps
            timer.timer = 0
            # Auto-fire in last move direction
            direction = (ctrl.last_move_dir_x, ctrl.last_move_dir_y)
            execute_weapon_attack(world, pid, direction, renderer)


# =============================================================================
# HOOK: modify_projectile_velocity (--grep homing)
# =============================================================================

def grep_homing_system(world: World):
    """
    --grep: adjust projectile velocity toward nearest enemy (max 3° per frame).
    Called each frame from main update loop.
    """
    from .components import Projectile, ProjectileTag

    # Get player weapon to check for grep mod
    has_grep = False
    for pid, _, _, inv in world.query(PlayerTag, PlayerStats, WeaponInventory):
        if inv.weapons:
            weapon = inv.weapons[min(inv.active_index, len(inv.weapons) - 1)]
            if 'grep_mod' in weapon.mods:
                has_grep = True
        break

    if not has_grep:
        return

    max_turn = math.radians(3)  # 3 degrees per frame

    for proj_id, p_pos, vel, proj in world.query(
        Position, Velocity, Projectile
    ):
        # Find nearest enemy within 10 tiles
        nearest_dist = 10.0
        nearest_pos = None
        for eid, e_pos, _ in world.query(Position, EnemyTag):
            dx = e_pos.x - p_pos.x
            dy = e_pos.y - p_pos.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_pos = e_pos

        if nearest_pos is None:
            continue

        # Current velocity angle
        speed = math.sqrt(vel.x * vel.x + vel.y * vel.y)
        if speed < 0.01:
            continue

        current_angle = math.atan2(vel.y, vel.x)

        # Desired angle toward enemy
        dx = nearest_pos.x - p_pos.x
        dy = nearest_pos.y - p_pos.y
        target_angle = math.atan2(dy, dx)

        # Compute shortest turn
        diff = target_angle - current_angle
        # Normalize to [-pi, pi]
        while diff > math.pi:
            diff -= 2 * math.pi
        while diff < -math.pi:
            diff += 2 * math.pi

        # Clamp turn rate
        if abs(diff) > max_turn:
            diff = max_turn if diff > 0 else -max_turn

        new_angle = current_angle + diff
        vel.x = math.cos(new_angle) * speed
        vel.y = math.sin(new_angle) * speed
