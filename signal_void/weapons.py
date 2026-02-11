"""
Weapon System
==============
Weapon definitions, attack pattern dispatch, and weapon utilities.
"""

import math
import random

from .ecs import World
from .components import (
    Position, Velocity, AttackState, PlayerTag, PlayerStats,
    WeaponComponent, WeaponInventory, PlayerControlled,
    Health, EnemyTag
)
from .engine import (
    NEON_CYAN, NEON_MAGENTA, NEON_YELLOW, NEON_GREEN, NEON_RED,
    NEON_ORANGE, WHITE, GRAY_DARK, GRAY_MED
)


# =============================================================================
# WEAPON DEFINITIONS
# =============================================================================
# All weapons in the game. Each entry defines stats and behavior.
# pattern types: melee_arc, melee_slam, melee_sweep,
#                projectile_single, projectile_spread, beam_continuous

WEAPONS = {
    'slash': {
        'symbol': '/',
        'name': 'Slash',
        'color': WHITE,
        'description': 'Fast melee arc',
        'damage': 25,
        'attack_frames': 12,
        'cooldown_frames': 3,
        'pattern': 'melee_arc',
        'arc_angle': 90,
        'radius': 4.5,
        'projectile_count': 0,
        'knockback': 1.2,
        'mod_slots': 2,
    },
    'ping': {
        'symbol': '\u2022',
        'name': 'Ping',
        'color': NEON_CYAN,
        'description': 'Ranged single shot',
        'damage': 35,
        'attack_frames': 8,
        'cooldown_frames': 28,
        'pattern': 'projectile_single',
        'projectile_count': 1,
        'projectile_speed': 1.5,
        'projectile_range': 30,
        'knockback': 0.6,
        'mod_slots': 2,
    },
    'fork': {
        'symbol': '\u2442',
        'name': 'Fork()',
        'color': NEON_GREEN,
        'description': '3-way projectile spread',
        'damage': 12,
        'attack_frames': 8,
        'cooldown_frames': 22,
        'pattern': 'projectile_spread',
        'projectile_count': 3,
        'spread_angle': 30,
        'projectile_speed': 1.2,
        'projectile_range': 20,
        'knockback': 0.4,
        'mod_slots': 2,
    },
    'kill9': {
        'symbol': '\u2588',
        'name': 'Kill -9',
        'color': NEON_RED,
        'description': 'Massive overhead slam',
        'damage': 100,
        'attack_frames': 20,
        'cooldown_frames': 52,
        'pattern': 'melee_slam',
        'radius': 2.5,
        'projectile_count': 0,
        'knockback': 4.0,
        'screen_shake_on_hit': True,
        'hit_stop_frames': 4,
        'mod_slots': 2,
    },
    'rmrf': {
        'symbol': '///',
        'name': 'Rm -rf',
        'color': NEON_ORANGE,
        'description': 'Wide 180\u00b0 sweep',
        'damage': 25,
        'attack_frames': 16,
        'cooldown_frames': 38,
        'pattern': 'melee_sweep',
        'arc_angle': 180,
        'radius': 5.0,
        'projectile_count': 0,
        'knockback': 2.0,
        'mod_slots': 2,
    },
    'overflow': {
        'symbol': '\u221e',
        'name': 'Overflow',
        'color': NEON_MAGENTA,
        'description': 'Continuous damage beam',
        'damage': 12,
        'attack_frames': 6,
        'cooldown_frames': 3,
        'pattern': 'beam_continuous',
        'beam_range': 15,
        'beam_width': 1,
        'projectile_count': 0,
        'knockback': 0.0,
        'locks_movement': True,
        'mod_slots': 2,
    },

    # =================================================================
    # EVOLVED WEAPONS
    # =================================================================
    'quicksort': {
        'symbol': '\u26a1/',
        'name': 'Quicksort',
        'color': NEON_YELLOW,
        'description': 'Blazing melee with afterimages',
        'damage': 20,
        'attack_frames': 6,
        'cooldown_frames': 1,
        'pattern': 'melee_arc',
        'arc_angle': 90,
        'radius': 4.0,
        'projectile_count': 0,
        'knockback': 0.5,
        'mod_slots': 3,
        'afterimage_interval': 3,
    },
    'segfault': {
        'symbol': '\u25c9',
        'name': 'Segfault',
        'color': NEON_RED,
        'description': 'Piercing shot that stuns',
        'damage': 60,
        'attack_frames': 8,
        'cooldown_frames': 42,
        'pattern': 'projectile_single',
        'projectile_count': 1,
        'projectile_speed': 2.5,
        'projectile_range': 50,
        'knockback': 1.5,
        'mod_slots': 3,
        'piercing': True,
        'stun_frames': 48,
    },
    'ddos': {
        'symbol': '\u2442',
        'name': 'DDoS',
        'color': NEON_GREEN,
        'description': '8-way omnidirectional burst',
        'damage': 10,
        'attack_frames': 8,
        'cooldown_frames': 30,
        'pattern': 'projectile_radial',
        'projectile_count': 8,
        'spread_angle': 360,
        'projectile_speed': 1.0,
        'projectile_range': 15,
        'knockback': 0.3,
        'mod_slots': 3,
    },
    'kernel_panic': {
        'symbol': '\u2593\u2588\u2593',
        'name': 'Kernel Panic',
        'color': NEON_RED,
        'description': 'Slam + expanding shockwave ring',
        'damage': 100,
        'attack_frames': 20,
        'cooldown_frames': 52,
        'pattern': 'melee_slam_shockwave',
        'radius': 1.5,
        'shockwave_radius': 5,
        'shockwave_damage': 30,
        'projectile_count': 0,
        'knockback': 2.5,
        'screen_shake_on_hit': True,
        'hit_stop_frames': 6,
        'mod_slots': 3,
        'auto_crit': True,
    },
    'format_c': {
        'symbol': '///*',
        'name': 'Format C:',
        'color': 220,
        'description': '360\u00b0 sweep + vacuum pull',
        'damage': 30,
        'attack_frames': 16,
        'cooldown_frames': 100,
        'pattern': 'melee_sweep',
        'arc_angle': 360,
        'radius': 5.0,
        'vacuum_radius': 8.0,
        'vacuum_force': 1.5,
        'projectile_count': 0,
        'knockback': 1.5,
        'mod_slots': 3,
    },
    'stack_overflow': {
        'symbol': '\u221e\u221e',
        'name': 'Stack Overflow',
        'color': NEON_MAGENTA,
        'description': 'Triple beam, overcharges at 3s',
        'damage': 12,
        'attack_frames': 6,
        'cooldown_frames': 3,
        'pattern': 'beam_triple',
        'beam_range': 18,
        'beam_width': 1,
        'beam_count': 3,
        'beam_spread_angle': 30,
        'projectile_count': 0,
        'knockback': 0.1,
        'locks_movement': True,
        'overcharge_frames': 180,
        'mod_slots': 3,
    },
}


# =============================================================================
# WEAPON UTILITIES
# =============================================================================

def create_weapon(weapon_type: str) -> WeaponComponent:
    """Create a WeaponComponent for the given weapon type."""
    data = WEAPONS.get(weapon_type)
    if data is None:
        data = WEAPONS['slash']
        weapon_type = 'slash'
    return WeaponComponent(
        weapon_type=weapon_type,
        base_type=weapon_type,
        mod_slots=data['mod_slots'],
    )


def get_active_weapon(world: World, player_id: int) -> WeaponComponent:
    """Get the player's active weapon component. Returns None if missing."""
    inv = world.get_component(player_id, WeaponInventory)
    if inv is None or not inv.weapons:
        return None
    idx = min(inv.active_index, len(inv.weapons) - 1)
    return inv.weapons[idx]


def get_weapon_data(weapon: WeaponComponent) -> dict:
    """Get the static data dict for a weapon component."""
    return WEAPONS.get(weapon.weapon_type, WEAPONS['slash'])


def swap_weapon(world: World, player_id: int):
    """Swap to the other weapon slot."""
    inv = world.get_component(player_id, WeaponInventory)
    if inv is None or len(inv.weapons) < 2:
        return
    inv.active_index = 1 - inv.active_index


def select_weapon_offer(world: World, player_id: int):
    """Pick a random weapon the player doesn't already have. Returns weapon_type or None."""
    import random as _rand
    inv = world.get_component(player_id, WeaponInventory)
    if inv is None:
        return None

    owned = {w.weapon_type for w in inv.weapons}
    available = [wt for wt in WEAPONS if wt not in owned]
    if not available:
        return None
    return _rand.choice(available)


def replace_weapon(world: World, player_id: int, slot: int, new_type: str):
    """Replace a weapon in the given slot (0 or 1) with a new weapon type."""
    inv = world.get_component(player_id, WeaponInventory)
    if inv is None:
        return

    new_weapon = create_weapon(new_type)
    if slot < len(inv.weapons):
        inv.weapons[slot] = new_weapon
    else:
        inv.weapons.append(new_weapon)

    # If only 1 weapon, this becomes active
    if len(inv.weapons) == 1:
        inv.active_index = 0


def render_weapon_select(renderer, offered_type: str, current_weapons: list,
                         frame: int):
    """Render the weapon selection overlay."""
    width = renderer.width
    height = renderer.game_height

    offered = WEAPONS[offered_type]

    # Box dimensions
    box_w = 47
    box_h = 13
    bx = width // 2 - box_w // 2
    by = height // 2 - box_h // 2

    # Draw box background
    for y in range(by, by + box_h):
        renderer.buffer.put_string(bx, y, ' ' * box_w, 0)

    # Borders
    renderer.buffer.put_string(bx, by,
        '\u250c\u2500\u2500\u2500 ARMORY CACHE ' + '\u2500' * (box_w - 17) + '\u2510',
        NEON_CYAN)
    for y in range(by + 1, by + box_h - 1):
        renderer.buffer.put_string(bx, y, '\u2502', NEON_CYAN)
        renderer.buffer.put_string(bx + box_w - 1, y, '\u2502', NEON_CYAN)
    renderer.buffer.put_string(bx, by + box_h - 1,
        '\u2514' + '\u2500' * (box_w - 2) + '\u2518', NEON_CYAN)

    # Current weapons
    cy = by + 2
    renderer.buffer.put_string(bx + 3, cy, 'Current:', GRAY_MED)
    cx = bx + 12
    for i, w in enumerate(current_weapons):
        wdata = WEAPONS.get(w.weapon_type, WEAPONS['slash'])
        text = f'[{i+1}] {wdata["symbol"]} {wdata["name"]}'
        renderer.buffer.put_string(cx, cy, text, wdata['color'])
        cx += len(text) + 3

    # Found weapon
    cy = by + 4
    renderer.buffer.put_string(bx + 3, cy, 'Found:', NEON_YELLOW)
    # Pulse the offered weapon
    pulse = (frame // 8) % 2 == 0
    o_color = offered['color'] if pulse else WHITE
    renderer.buffer.put_string(bx + 10, cy,
        f'{offered["symbol"]}  {offered["name"]}', o_color)
    renderer.buffer.put_string(bx + 3, cy + 1,
        f'"{offered["description"]}"', GRAY_MED)

    # Options
    cy = by + 7
    for i, w in enumerate(current_weapons):
        wdata = WEAPONS.get(w.weapon_type, WEAPONS['slash'])
        has_mods = len(w.mods) > 0
        mod_warn = f' ({len(w.mods)} mod{"s" if len(w.mods) != 1 else ""} lost!)' if has_mods else ''
        text = f'[{i+1}] Replace {wdata["name"]} {wdata["symbol"]}{mod_warn}'
        renderer.buffer.put_string(bx + 3, cy + i, text, wdata['color'])

    # Add to empty slot if only 1 weapon
    if len(current_weapons) < 2:
        renderer.buffer.put_string(bx + 3, cy + len(current_weapons),
            f'[{len(current_weapons)+1}] Add to empty slot', NEON_GREEN)

    renderer.buffer.put_string(bx + 3, cy + max(len(current_weapons), 2) + 1,
        '[ESC] Discard', GRAY_DARK)

    # Hint at bottom
    renderer.buffer.put_string(bx + 3, by + box_h - 2,
        'Press 1, 2, or ESC', GRAY_MED)


# =============================================================================
# ATTACK DISPATCH
# =============================================================================

def execute_weapon_attack(world: World, player_id: int, direction: tuple,
                          renderer) -> bool:
    """
    Execute an attack with the active weapon.

    Sets up AttackState and spawns pattern-specific visuals.
    Returns True if attack was initiated.
    """
    weapon = get_active_weapon(world, player_id)
    if weapon is None:
        return False

    # Check cooldown
    if weapon.attack_timer > 0:
        return False

    data = dict(get_weapon_data(weapon))  # Copy so mods don't mutate base
    pos = world.get_component(player_id, Position)
    attack = world.get_component(player_id, AttackState)
    stats = world.get_component(player_id, PlayerStats)
    if pos is None or attack is None:
        return False

    if attack.active:
        return False

    # Apply mod params before attack
    if weapon.mods:
        from .weapon_mods import apply_mod_params
        apply_mod_params(weapon, data)

    # Calculate attack frames with stats
    base_frames = data['attack_frames']
    if stats and stats.attack_speed_multiplier > 1.0:
        base_frames = max(4, int(base_frames / stats.attack_speed_multiplier))

    # Activate attack state
    attack.active = True
    attack.frames_remaining = base_frames
    attack.direction_x = direction[0]
    attack.direction_y = direction[1]

    # Set attack radius from weapon (used by combat_system)
    attack.radius = data.get('radius', 3.0)

    # Beam flag
    attack.is_beam = data['pattern'] in ('beam_continuous', 'beam_triple')
    attack.beam_range = data.get('beam_range', 0.0)
    if not attack.is_beam:
        attack.beam_continuous_frames = 0

    # Set weapon cooldown
    cooldown = data.get('cooldown_frames', 0)
    if stats and stats.attack_speed_multiplier > 1.0:
        cooldown = max(1, int(cooldown / stats.attack_speed_multiplier))
    weapon.attack_timer = base_frames + cooldown

    # Dispatch to pattern-specific visual/spawn
    pattern = data['pattern']
    if pattern == 'melee_arc':
        _spawn_melee_arc(world, pos, direction, data, renderer)
    elif pattern == 'melee_slam':
        _spawn_melee_slam(world, pos, direction, data, renderer)
    elif pattern == 'melee_slam_shockwave':
        _spawn_melee_slam(world, pos, direction, data, renderer)
        from .evolution import spawn_shockwave
        sw_x = pos.x + direction[0]
        sw_y = pos.y + direction[1]
        spawn_shockwave(
            world, sw_x, sw_y,
            max_radius=data.get('shockwave_radius', 5),
            damage=data.get('shockwave_damage', 30)
        )
    elif pattern == 'melee_sweep':
        # Format C: vacuum pull before sweep
        if data.get('vacuum_radius'):
            _apply_vacuum_pull(world, player_id, pos, data)
        _spawn_melee_sweep(world, pos, direction, data, renderer)
    elif pattern == 'projectile_single':
        bonus = stats.bonus_projectile_count if stats else 0
        _spawn_projectile_single(world, pos, direction, data, player_id, bonus)
    elif pattern == 'projectile_spread':
        bonus = stats.bonus_projectile_count if stats else 0
        _spawn_projectile_spread(world, pos, direction, data, player_id, bonus)
    elif pattern == 'projectile_radial':
        bonus = stats.bonus_projectile_count if stats else 0
        _spawn_projectile_radial(world, pos, direction, data, player_id, weapon, bonus)
    elif pattern in ('beam_continuous', 'beam_triple'):
        pass  # Beam is rendered live each frame, no spawn needed

    # Fire on_attack mod hooks (e.g. --verbose ground trail)
    if weapon.mods:
        from .weapon_mods import fire_on_attack
        fire_on_attack(world, weapon, (pos.x, pos.y), direction, pattern, renderer)

    # Quicksort afterimage: every Nth attack spawns an echo at 30% damage
    afterimage_interval = data.get('afterimage_interval', 0)
    if afterimage_interval > 0:
        weapon.attack_counter += 1
        if weapon.attack_counter >= afterimage_interval:
            weapon.attack_counter = 0
            _spawn_afterimage(world, pos, direction, data)

    # Screen shake for attack feedback (skip for beam — it fires too fast)
    if not attack.is_beam:
        shake_intensity = 2 if data.get('screen_shake_on_hit') else 1
        renderer.trigger_shake(intensity=shake_intensity, frames=2)

    return True


def weapon_cooldown_system(world: World):
    """Tick down weapon attack timers."""
    for eid, inv in world.query(WeaponInventory):
        for weapon in inv.weapons:
            if weapon.attack_timer > 0:
                weapon.attack_timer -= 1


# =============================================================================
# MELEE PATTERNS
# =============================================================================

# Slash arc patterns: offsets relative to player for each direction
_SLASH_ARCS = {
    (0, -1): [  # Up
        (-2, -2), (-1, -2), (0, -2), (1, -2), (2, -2),
        (-1, -1), (0, -1), (1, -1),
    ],
    (0, 1): [  # Down
        (-2, 2), (-1, 2), (0, 2), (1, 2), (2, 2),
        (-1, 1), (0, 1), (1, 1),
    ],
    (-1, 0): [  # Left
        (-2, -2), (-2, -1), (-2, 0), (-2, 1), (-2, 2),
        (-1, -1), (-1, 0), (-1, 1),
    ],
    (1, 0): [  # Right
        (2, -2), (2, -1), (2, 0), (2, 1), (2, 2),
        (1, -1), (1, 0), (1, 1),
    ],
}

_SLASH_CHARS = ['/', '\\', '|', '-', '*', 'x', '+']
_SLASH_COLORS = [WHITE, NEON_CYAN, NEON_MAGENTA, NEON_CYAN, GRAY_MED, GRAY_DARK]


def _spawn_melee_arc(world, pos, direction, weapon_data, renderer):
    """Spawn a melee arc slash visual (same as existing spawn_slash_arc)."""
    from .particles import spawn_particle

    key = (int(direction[0]), int(direction[1]))
    arc_cells = _SLASH_ARCS.get(key, [])
    weapon_color = weapon_data.get('color', WHITE)

    for i, (ox, oy) in enumerate(arc_cells):
        base_life = 12
        life = base_life - (i % 3) * 2

        char = random.choice(_SLASH_CHARS)
        # Use weapon color for first few cells, then fade
        if i < 3:
            color = weapon_color
        else:
            color_idx = min(i - 3, len(_SLASH_COLORS) - 1)
            color = _SLASH_COLORS[color_idx]

        spawn_particle(
            world,
            pos.x + ox, pos.y + oy,
            vx=direction[0] * 0.1, vy=direction[1] * 0.1,
            char=char,
            color=color,
            lifetime=max(life, 4),
            gravity=0
        )


def _spawn_melee_slam(world, pos, direction, weapon_data, renderer):
    """Spawn a melee slam visual (heavy single-point impact)."""
    from .particles import spawn_particle

    weapon_color = weapon_data.get('color', NEON_RED)
    # Impact at 1 tile in front of player
    ix = pos.x + direction[0]
    iy = pos.y + direction[1]

    # Heavy impact particles
    slam_chars = ['\u2588', '#', '*', '!', 'x']
    for i in range(6):
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(0.3, 0.8)
        spawn_particle(
            world, ix, iy,
            vx=math.cos(angle) * speed,
            vy=math.sin(angle) * speed,
            char=random.choice(slam_chars),
            color=weapon_color if i < 3 else NEON_YELLOW,
            lifetime=random.randint(8, 16),
            gravity=0.05
        )


def _spawn_melee_sweep(world, pos, direction, weapon_data, renderer):
    """Spawn a wide sweep visual (180 degree arc)."""
    from .particles import spawn_particle

    weapon_color = weapon_data.get('color', NEON_ORANGE)
    radius = weapon_data.get('radius', 4.0)

    # Generate a 180-degree arc of particles
    base_angle = math.atan2(direction[1], direction[0])
    sweep_chars = ['\u2500', '\u2502', '/', '\\', '*']

    for i in range(12):
        angle = base_angle - math.pi / 2 + (math.pi * i / 11)
        dist = random.uniform(1.5, radius)
        ox = math.cos(angle) * dist
        oy = math.sin(angle) * dist
        spawn_particle(
            world,
            pos.x + ox, pos.y + oy,
            vx=math.cos(angle) * 0.15,
            vy=math.sin(angle) * 0.15,
            char=random.choice(sweep_chars),
            color=weapon_color if i % 2 == 0 else NEON_YELLOW,
            lifetime=random.randint(8, 14),
            gravity=0
        )


# =============================================================================
# PROJECTILE PATTERNS
# =============================================================================

def _spawn_projectile_single(world, pos, direction, weapon_data, owner_id,
                             bonus_count=0):
    """Spawn a single aimed projectile (Ping pattern)."""
    from .projectiles import spawn_projectile

    weapon_color = weapon_data.get('color', NEON_CYAN)
    speed = weapon_data.get('projectile_speed', 1.5)
    max_range = weapon_data.get('projectile_range', 30)
    damage = weapon_data.get('damage', 35)
    knockback = weapon_data.get('knockback', 0.6)
    char = weapon_data.get('symbol', '\u2022')

    total_count = 1 + bonus_count

    is_piercing = weapon_data.get('piercing', False)
    stun = weapon_data.get('stun_frames', 0)

    if total_count == 1:
        # Single shot
        eid = spawn_projectile(
            world,
            pos.x + direction[0] * 1.5,
            pos.y + direction[1] * 1.5,
            vx=direction[0] * speed,
            vy=direction[1] * speed,
            damage=damage,
            knockback=knockback,
            max_range=max_range,
            char=char,
            color=weapon_color,
            owner_id=owner_id,
        )
        if is_piercing or stun:
            from .components import Projectile as ProjComp
            proj = world.get_component(eid, ProjComp)
            if proj:
                proj.piercing = is_piercing
                proj.stun_frames = stun
    else:
        # Multiple shots in a tight spread
        base_angle = math.atan2(direction[1], direction[0])
        spread = 10  # degrees total
        spread_rad = math.radians(spread)

        for i in range(total_count):
            offset = -spread_rad / 2 + spread_rad * i / max(1, total_count - 1)
            angle = base_angle + offset
            eid = spawn_projectile(
                world,
                pos.x + direction[0] * 1.5,
                pos.y + direction[1] * 1.5,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                damage=damage,
                knockback=knockback,
                max_range=max_range,
                char=char,
                color=weapon_color,
                owner_id=owner_id,
            )
            if is_piercing or stun:
                from .components import Projectile as ProjComp
                proj = world.get_component(eid, ProjComp)
                if proj:
                    proj.piercing = is_piercing
                    proj.stun_frames = stun


def _spawn_projectile_spread(world, pos, direction, weapon_data, owner_id,
                             bonus_count=0):
    """Spawn a spread of projectiles (Fork() pattern)."""
    from .projectiles import spawn_projectile

    weapon_color = weapon_data.get('color', NEON_GREEN)
    speed = weapon_data.get('projectile_speed', 1.2)
    max_range = weapon_data.get('projectile_range', 20)
    damage = weapon_data.get('damage', 12)
    knockback = weapon_data.get('knockback', 0.4)
    char = weapon_data.get('symbol', '\u2442')
    base_count = weapon_data.get('projectile_count', 3)
    spread_angle = weapon_data.get('spread_angle', 30)

    total_count = base_count + bonus_count
    spread_rad = math.radians(spread_angle)
    base_angle = math.atan2(direction[1], direction[0])

    for i in range(total_count):
        if total_count == 1:
            offset = 0
        else:
            offset = -spread_rad / 2 + spread_rad * i / (total_count - 1)
        angle = base_angle + offset

        spawn_projectile(
            world,
            pos.x + direction[0] * 1.5,
            pos.y + direction[1] * 1.5,
            vx=math.cos(angle) * speed,
            vy=math.sin(angle) * speed,
            damage=damage,
            knockback=knockback,
            max_range=max_range,
            char=char,
            color=weapon_color,
            owner_id=owner_id,
        )


def _spawn_projectile_radial(world, pos, direction, weapon_data, owner_id,
                              weapon, bonus_count=0):
    """Spawn projectiles in a full circle (DDoS pattern)."""
    from .projectiles import spawn_projectile

    weapon_color = weapon_data.get('color', NEON_GREEN)
    speed = weapon_data.get('projectile_speed', 1.0)
    max_range = weapon_data.get('projectile_range', 15)
    damage = weapon_data.get('damage', 10)
    knockback = weapon_data.get('knockback', 0.3)
    char = weapon_data.get('symbol', '\u2442')
    base_count = weapon_data.get('projectile_count', 8)

    total_count = base_count + bonus_count

    # Alternate offset every other attack for wave pattern
    weapon.attack_counter += 1
    angle_offset = math.pi / total_count if weapon.attack_counter % 2 == 0 else 0

    for i in range(total_count):
        angle = angle_offset + (2 * math.pi * i) / total_count
        spawn_projectile(
            world,
            pos.x + math.cos(angle) * 1.5,
            pos.y + math.sin(angle) * 1.5,
            vx=math.cos(angle) * speed,
            vy=math.sin(angle) * speed,
            damage=damage,
            knockback=knockback,
            max_range=max_range,
            char=char,
            color=weapon_color,
            owner_id=owner_id,
        )


# =============================================================================
# EVOLVED WEAPON HELPERS
# =============================================================================

def _spawn_afterimage(world, pos, direction, weapon_data):
    """Quicksort: spawn a delayed echo attack at 30% damage."""
    from .weapon_mods import _EchoMarker
    from .components import Lifetime, Velocity
    from .particles import spawn_particle

    echo_damage = max(1, int(weapon_data.get('damage', 20) * 0.3))

    eid = world.create_entity()
    world.add_component(eid, Position(pos.x, pos.y))
    world.add_component(eid, Velocity(0, 0))
    world.add_component(eid, Lifetime(frames_remaining=12))  # 0.2s delay
    world.add_component(eid, _EchoMarker(
        damage=echo_damage,
        direction_x=direction[0],
        direction_y=direction[1],
        radius=2.5,
    ))

    # Dim afterimage preview
    spawn_particle(
        world, pos.x, pos.y,
        vx=0, vy=0,
        char='@',
        color=GRAY_MED,
        lifetime=12,
        gravity=0
    )


def _apply_vacuum_pull(world, player_id, pos, weapon_data):
    """Format C: pull enemies toward player before sweep."""
    from .components import Knockback as KB

    vacuum_radius = weapon_data.get('vacuum_radius', 8.0)
    vacuum_force = weapon_data.get('vacuum_force', 1.5)

    for enemy_id, e_pos, _, _ in world.query(Position, Health, EnemyTag):
        dx = e_pos.x - pos.x
        dy = e_pos.y - pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        if 0 < dist < vacuum_radius:
            # Pull toward player (negative direction)
            pull_x = -dx / dist * vacuum_force
            pull_y = -dy / dist * vacuum_force
            world.add_component(enemy_id, KB(pull_x, pull_y, decay=0.6))
