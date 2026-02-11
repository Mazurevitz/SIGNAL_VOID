"""
Wave Spawning System
=====================
Choreographed enemy waves with spawn patterns and telegraphs.
Replaces flat enemy spawning with multi-wave, patterned encounters.
"""

import math
import random
import copy
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Callable

from .ecs import World
from .components import (
    Position, Renderable, Invulnerable, Health,
    EnemyTag, SpawnTelegraph
)
from .enemies import (
    create_buffer_leak, create_firewall, create_overclocker,
    create_spammer, create_sniper, _apply_depth_scaling
)
from .engine import NEON_RED, NEON_YELLOW, GRAY_DARK, WHITE
from .particles import spawn_explosion


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SpawnGroup:
    """A group of enemies that spawn together in a pattern."""
    enemy_type: str
    count: int
    spawn_pattern: str
    delay: float = 0.0  # seconds after wave trigger


@dataclass
class Wave:
    """A single wave of enemies with a trigger condition."""
    spawn_groups: List[SpawnGroup] = field(default_factory=list)
    trigger: str = 'on_start'  # on_start, on_kill_percent, on_timer
    trigger_value: float = 0
    announcement: Optional[str] = None


@dataclass
class RoomWaves:
    """Tracks wave state for a room."""
    waves: List[Wave] = field(default_factory=list)
    current_wave: int = 0
    room_timer: float = 0.0
    total_spawned: int = 0
    total_killed: int = 0
    pending_groups: list = field(default_factory=list)
    all_waves_triggered: bool = False
    active_announcement: Optional[str] = None
    announcement_timer: int = 0


# =============================================================================
# ENEMY FACTORIES
# =============================================================================

WAVE_ENEMY_FACTORIES: Dict[str, Optional[Callable]] = {
    'buffer_leak': create_buffer_leak,
    'firewall': create_firewall,
    'overclocker': create_overclocker,
    'spammer': create_spammer,
    'sniper': create_sniper,
    'worm': None,
    'daemon': None,
    'trojan': None,
}


# =============================================================================
# SPAWN PATTERNS
# =============================================================================

def _clamp_pos(x: float, y: float, w: int, h: int, margin: int) -> Tuple[float, float]:
    return (max(margin, min(w - margin, x)), max(margin, min(h - margin, y)))


def _get_spawn_positions(
    pattern: str, count: int,
    room_w: int, room_h: int,
    player_x: float, player_y: float,
    facing_x: float = 1.0, facing_y: float = 0.0
) -> List[Tuple[float, float]]:
    """Calculate spawn positions for a spawn pattern."""
    margin = 2
    positions = []

    if pattern == 'surround':
        radius = random.uniform(8, 12)
        for i in range(count):
            angle = (2 * math.pi * i / count) + random.uniform(-0.2, 0.2)
            x = player_x + math.cos(angle) * radius
            y = player_y + math.sin(angle) * radius
            positions.append(_clamp_pos(x, y, room_w, room_h, margin))

    elif pattern == 'line_top':
        spacing = max(2, (room_w - margin * 2) / max(count, 1))
        start_x = margin + spacing / 2
        for i in range(count):
            x = start_x + i * spacing
            y = margin + random.uniform(0, 2)
            positions.append(_clamp_pos(x, y, room_w, room_h, margin))

    elif pattern == 'line_bottom':
        spacing = max(2, (room_w - margin * 2) / max(count, 1))
        start_x = margin + spacing / 2
        for i in range(count):
            x = start_x + i * spacing
            y = room_h - margin - random.uniform(0, 2)
            positions.append(_clamp_pos(x, y, room_w, room_h, margin))

    elif pattern == 'corners':
        corner_positions = [
            (margin + 2, margin + 2),
            (room_w - margin - 2, margin + 2),
            (margin + 2, room_h - margin - 2),
            (room_w - margin - 2, room_h - margin - 2),
        ]
        for i in range(count):
            cx, cy = corner_positions[i % 4]
            x = cx + random.uniform(-1, 1)
            y = cy + random.uniform(-1, 1)
            positions.append(_clamp_pos(x, y, room_w, room_h, margin))

    elif pattern == 'behind_player':
        behind_x = -facing_x
        behind_y = -facing_y
        if abs(behind_x) < 0.1 and abs(behind_y) < 0.1:
            behind_x, behind_y = -1.0, 0.0

        base_dist = random.uniform(6, 10)
        perp_x = -behind_y
        perp_y = behind_x
        for i in range(count):
            spread = random.uniform(-2, 2)
            dist = base_dist + random.uniform(-1, 1)
            x = player_x + behind_x * dist + perp_x * spread
            y = player_y + behind_y * dist + perp_y * spread
            positions.append(_clamp_pos(x, y, room_w, room_h, margin))

    elif pattern == 'ring':
        radius = random.uniform(4, 5)
        for i in range(count):
            angle = (2 * math.pi * i / count) + random.uniform(-0.15, 0.15)
            x = player_x + math.cos(angle) * radius
            y = player_y + math.sin(angle) * radius
            positions.append(_clamp_pos(x, y, room_w, room_h, margin))

    elif pattern == 'pincer':
        half = count // 2
        # Perpendicular to facing direction
        perp_x = -facing_y
        perp_y = facing_x
        length = math.sqrt(perp_x * perp_x + perp_y * perp_y)
        if length > 0:
            perp_x /= length
            perp_y /= length
        else:
            perp_x, perp_y = 0, -1

        for i in range(half):
            dist = random.uniform(6, 10)
            spread = random.uniform(-1, 1)
            x = player_x + perp_x * dist + facing_x * spread
            y = player_y + perp_y * dist + facing_y * spread
            positions.append(_clamp_pos(x, y, room_w, room_h, margin))

        for i in range(count - half):
            dist = random.uniform(6, 10)
            spread = random.uniform(-1, 1)
            x = player_x - perp_x * dist + facing_x * spread
            y = player_y - perp_y * dist + facing_y * spread
            positions.append(_clamp_pos(x, y, room_w, room_h, margin))

    else:  # 'random' or fallback
        for _ in range(count):
            attempts = 0
            while attempts < 20:
                x = random.uniform(margin, room_w - margin)
                y = random.uniform(margin, room_h - margin)
                dx = x - player_x
                dy = y - player_y
                if math.sqrt(dx * dx + dy * dy) >= 6:
                    positions.append((x, y))
                    break
                attempts += 1
            else:
                positions.append(_clamp_pos(
                    random.uniform(margin, room_w - margin),
                    random.uniform(margin, room_h - margin),
                    room_w, room_h, margin
                ))

    return positions


# =============================================================================
# ROOM TEMPLATES
# =============================================================================

def _make_templates():
    templates = {}

    # --- Depth 1-2: Tutorial ---
    templates['tutorial_1'] = {
        'depth_range': (1, 2),
        'waves': [
            Wave([SpawnGroup('buffer_leak', 4, 'random')], 'on_start'),
            Wave([SpawnGroup('buffer_leak', 3, 'behind_player')],
                 'on_kill_percent', 0.75),
        ],
    }
    templates['tutorial_2'] = {
        'depth_range': (1, 2),
        'waves': [
            Wave([SpawnGroup('buffer_leak', 3, 'surround')], 'on_start'),
            Wave([SpawnGroup('buffer_leak', 4, 'corners')],
                 'on_kill_percent', 0.60),
        ],
    }
    templates['tutorial_3'] = {
        'depth_range': (1, 2),
        'waves': [
            Wave([SpawnGroup('buffer_leak', 3, 'line_top')], 'on_start'),
            Wave([SpawnGroup('buffer_leak', 3, 'line_bottom')],
                 'on_kill_percent', 0.60),
        ],
    }

    # --- Depth 3-4: Firewalls + Spammers introduced ---
    templates['early_mixed_1'] = {
        'depth_range': (3, 4),
        'waves': [
            Wave([
                SpawnGroup('buffer_leak', 4, 'surround'),
                SpawnGroup('firewall', 1, 'line_top', 0.5),
            ], 'on_start'),
            Wave([
                SpawnGroup('buffer_leak', 3, 'behind_player'),
                SpawnGroup('spammer', 2, 'corners', 0.3),
            ], 'on_kill_percent', 0.60, '>>> INCOMING <<<'),
            Wave([SpawnGroup('firewall', 2, 'pincer')],
                 'on_kill_percent', 0.50),
        ],
    }
    templates['early_mixed_2'] = {
        'depth_range': (3, 4),
        'waves': [
            Wave([
                SpawnGroup('buffer_leak', 3, 'corners'),
                SpawnGroup('spammer', 1, 'line_top', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('buffer_leak', 4, 'surround'),
                SpawnGroup('firewall', 1, 'behind_player', 0.5),
            ], 'on_kill_percent', 0.50, '>>> WAVE 2 <<<'),
        ],
    }
    templates['early_mixed_3'] = {
        'depth_range': (3, 4),
        'waves': [
            Wave([
                SpawnGroup('firewall', 2, 'pincer'),
                SpawnGroup('buffer_leak', 2, 'random', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('buffer_leak', 3, 'ring'),
                SpawnGroup('spammer', 1, 'behind_player', 0.3),
            ], 'on_kill_percent', 0.60),
        ],
    }

    # --- Depth 5-7: Overclockers + Spammers, full pressure ---
    templates['mid_pressure_1'] = {
        'depth_range': (5, 7),
        'waves': [
            Wave([
                SpawnGroup('buffer_leak', 5, 'surround'),
                SpawnGroup('spammer', 3, 'corners', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('overclocker', 2, 'line_top'),
                SpawnGroup('buffer_leak', 3, 'behind_player', 0.5),
            ], 'on_kill_percent', 0.50, '>>> WAVE 2 <<<'),
            Wave([
                SpawnGroup('firewall', 2, 'corners'),
                SpawnGroup('spammer', 2, 'random', 0.3),
                SpawnGroup('buffer_leak', 3, 'surround', 0.5),
            ], 'on_kill_percent', 0.50, '>>> WAVE 3 <<<'),
        ],
    }
    templates['mid_pressure_2'] = {
        'depth_range': (5, 7),
        'waves': [
            Wave([
                SpawnGroup('buffer_leak', 4, 'corners'),
                SpawnGroup('spammer', 2, 'line_top', 0.3),
                SpawnGroup('firewall', 1, 'random', 0.5),
            ], 'on_start'),
            Wave([
                SpawnGroup('overclocker', 2, 'pincer'),
                SpawnGroup('sniper', 1, 'corners', 0.3),
                SpawnGroup('buffer_leak', 3, 'ring', 0.3),
            ], 'on_kill_percent', 0.50, '>>> WAVE 2 <<<'),
        ],
    }
    templates['mid_pressure_3'] = {
        'depth_range': (5, 7),
        'waves': [
            Wave([
                SpawnGroup('overclocker', 1, 'random'),
                SpawnGroup('spammer', 2, 'line_top', 0.2),
                SpawnGroup('buffer_leak', 4, 'surround', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('firewall', 1, 'behind_player'),
                SpawnGroup('sniper', 1, 'corners', 0.3),
                SpawnGroup('buffer_leak', 3, 'line_bottom', 0.5),
            ], 'on_kill_percent', 0.60, '>>> INCOMING <<<'),
            Wave([
                SpawnGroup('overclocker', 2, 'corners'),
                SpawnGroup('spammer', 2, 'behind_player', 0.3),
            ], 'on_kill_percent', 0.40, '>>> FINAL WAVE <<<'),
        ],
    }

    # --- Depth 8-10: Intense, timer waves ---
    templates['late_intense_1'] = {
        'depth_range': (8, 10),
        'waves': [
            Wave([
                SpawnGroup('buffer_leak', 4, 'surround'),
                SpawnGroup('spammer', 3, 'line_top', 0.2),
                SpawnGroup('sniper', 2, 'corners', 0.5),
            ], 'on_start'),
            Wave([
                SpawnGroup('overclocker', 2, 'pincer'),
                SpawnGroup('buffer_leak', 3, 'behind_player', 0.3),
            ], 'on_timer', 8.0, '>>> REINFORCEMENTS <<<'),
            Wave([
                SpawnGroup('firewall', 2, 'surround'),
                SpawnGroup('spammer', 3, 'behind_player', 0.3),
                SpawnGroup('buffer_leak', 4, 'ring', 0.5),
            ], 'on_kill_percent', 0.40, '>>> FINAL WAVE <<<'),
        ],
    }
    templates['late_intense_2'] = {
        'depth_range': (8, 10),
        'waves': [
            Wave([
                SpawnGroup('overclocker', 2, 'line_top'),
                SpawnGroup('spammer', 2, 'corners', 0.2),
                SpawnGroup('buffer_leak', 4, 'surround', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('firewall', 2, 'pincer'),
                SpawnGroup('sniper', 1, 'corners', 0.3),
                SpawnGroup('spammer', 2, 'behind_player', 0.3),
            ], 'on_kill_percent', 0.50, '>>> WAVE 2 <<<'),
            Wave([
                SpawnGroup('overclocker', 2, 'behind_player'),
                SpawnGroup('buffer_leak', 3, 'surround', 0.3),
            ], 'on_timer', 6.0, '>>> FINAL WAVE <<<'),
        ],
    }
    templates['late_intense_3'] = {
        'depth_range': (8, 10),
        'waves': [
            Wave([
                SpawnGroup('buffer_leak', 3, 'surround'),
                SpawnGroup('spammer', 2, 'line_bottom', 0.2),
                SpawnGroup('sniper', 1, 'corners', 0.3),
                SpawnGroup('firewall', 2, 'corners', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('overclocker', 3, 'ring'),
                SpawnGroup('spammer', 2, 'random', 0.3),
            ], 'on_timer', 6.0, '>>> INCOMING <<<'),
            Wave([
                SpawnGroup('buffer_leak', 5, 'behind_player'),
                SpawnGroup('sniper', 1, 'random', 0.3),
                SpawnGroup('firewall', 1, 'random', 0.5),
            ], 'on_kill_percent', 0.40, '>>> FINAL WAVE <<<'),
        ],
    }

    # --- Depth 11+: Endgame chaos ---
    templates['endgame_1'] = {
        'depth_range': (11, 99),
        'waves': [
            Wave([
                SpawnGroup('spammer', 4, 'corners'),
                SpawnGroup('sniper', 2, 'line_top', 0.2),
                SpawnGroup('buffer_leak', 5, 'surround', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('overclocker', 3, 'pincer'),
                SpawnGroup('spammer', 2, 'behind_player', 0.3),
                SpawnGroup('firewall', 1, 'random', 0.5),
            ], 'on_timer', 6.0, '>>> WAVE 2 <<<'),
            Wave([
                SpawnGroup('buffer_leak', 4, 'behind_player'),
                SpawnGroup('sniper', 2, 'corners', 0.3),
                SpawnGroup('spammer', 3, 'line_bottom', 0.5),
            ], 'on_kill_percent', 0.40, '>>> WAVE 3 <<<'),
            Wave([
                SpawnGroup('overclocker', 2, 'corners'),
                SpawnGroup('buffer_leak', 6, 'ring', 0.3),
            ], 'on_timer', 5.0, '>>> FINAL WAVE <<<'),
        ],
    }
    templates['endgame_2'] = {
        'depth_range': (11, 99),
        'waves': [
            Wave([
                SpawnGroup('overclocker', 3, 'line_top'),
                SpawnGroup('sniper', 3, 'corners', 0.2),
                SpawnGroup('spammer', 3, 'line_bottom', 0.3),
                SpawnGroup('buffer_leak', 4, 'surround', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('firewall', 2, 'pincer'),
                SpawnGroup('buffer_leak', 3, 'behind_player', 0.3),
            ], 'on_kill_percent', 0.50, '>>> WAVE 2 <<<'),
            Wave([
                SpawnGroup('overclocker', 2, 'ring'),
                SpawnGroup('spammer', 3, 'behind_player', 0.3),
                SpawnGroup('buffer_leak', 4, 'corners', 0.5),
            ], 'on_timer', 5.0, '>>> WAVE 3 <<<'),
            Wave([
                SpawnGroup('firewall', 3, 'surround'),
                SpawnGroup('sniper', 2, 'corners', 0.2),
                SpawnGroup('overclocker', 2, 'behind_player', 0.3),
            ], 'on_kill_percent', 0.30, '>>> FINAL WAVE <<<'),
        ],
    }
    templates['endgame_3'] = {
        'depth_range': (11, 99),
        'waves': [
            Wave([
                SpawnGroup('firewall', 2, 'line_top'),
                SpawnGroup('sniper', 2, 'corners', 0.2),
                SpawnGroup('spammer', 3, 'line_bottom', 0.3),
                SpawnGroup('buffer_leak', 5, 'surround', 0.3),
            ], 'on_start'),
            Wave([
                SpawnGroup('overclocker', 3, 'behind_player'),
                SpawnGroup('spammer', 2, 'random', 0.3),
            ], 'on_timer', 7.0, '>>> WAVE 2 <<<'),
            Wave([
                SpawnGroup('buffer_leak', 5, 'ring'),
                SpawnGroup('sniper', 1, 'corners', 0.3),
                SpawnGroup('firewall', 1, 'random', 0.3),
            ], 'on_kill_percent', 0.40, '>>> WAVE 3 <<<'),
            Wave([
                SpawnGroup('overclocker', 3, 'pincer'),
                SpawnGroup('spammer', 3, 'line_bottom', 0.3),
                SpawnGroup('buffer_leak', 4, 'surround', 0.5),
            ], 'on_timer', 5.0, '>>> FINAL WAVE <<<'),
        ],
    }

    return templates


ROOM_TEMPLATES = _make_templates()


def get_template_for_depth(depth: int) -> dict:
    """Select a random room template appropriate for the given depth."""
    matching = [
        t for t in ROOM_TEMPLATES.values()
        if t['depth_range'][0] <= depth <= t['depth_range'][1]
    ]
    if not matching:
        matching = [
            t for t in ROOM_TEMPLATES.values()
            if t['depth_range'][1] >= 99
        ]
    return random.choice(matching) if matching else None


def create_room_waves(depth: int) -> Optional[RoomWaves]:
    """Create a RoomWaves instance for a given depth."""
    template = get_template_for_depth(depth)
    if template is None:
        return None
    waves = copy.deepcopy(template['waves'])
    return RoomWaves(waves=waves)


# =============================================================================
# WAVE UPDATE SYSTEM
# =============================================================================

def update_wave_system(
    world: World, room_waves: RoomWaves,
    room_w: int, room_h: int,
    player_x: float, player_y: float,
    facing_x: float, facing_y: float,
    depth: int, dt: float = 1.0 / 60
):
    """Check wave triggers and queue spawn groups. Call once per frame."""
    room_waves.room_timer += dt

    # Process pending spawn groups (delayed spawns within a wave)
    new_pending = []
    for group, delay_frames in room_waves.pending_groups:
        delay_frames -= 1
        if delay_frames <= 0:
            _spawn_telegraphs(
                world, group, room_w, room_h,
                player_x, player_y, facing_x, facing_y, depth
            )
            room_waves.total_spawned += _count_spawnable(group)
        else:
            new_pending.append((group, delay_frames))
    room_waves.pending_groups = new_pending

    # Check if all waves have been triggered
    if room_waves.current_wave >= len(room_waves.waves):
        room_waves.all_waves_triggered = True
        _tick_announcement(room_waves)
        return

    # Check trigger for current wave
    wave = room_waves.waves[room_waves.current_wave]
    triggered = False

    if wave.trigger == 'on_start':
        triggered = True
    elif wave.trigger == 'on_kill_percent':
        if room_waves.total_spawned > 0:
            kill_ratio = room_waves.total_killed / room_waves.total_spawned
            if kill_ratio >= wave.trigger_value:
                triggered = True
    elif wave.trigger == 'on_timer':
        if room_waves.room_timer >= wave.trigger_value:
            triggered = True

    if triggered:
        for group in wave.spawn_groups:
            delay_frames = int(group.delay * 60)
            if delay_frames <= 0:
                _spawn_telegraphs(
                    world, group, room_w, room_h,
                    player_x, player_y, facing_x, facing_y, depth
                )
                room_waves.total_spawned += _count_spawnable(group)
            else:
                room_waves.pending_groups.append((group, delay_frames))

        if wave.announcement:
            room_waves.active_announcement = wave.announcement
            room_waves.announcement_timer = 90

        room_waves.current_wave += 1

        # Check if that was the last wave
        if room_waves.current_wave >= len(room_waves.waves):
            room_waves.all_waves_triggered = True
        else:
            # Recursively check next wave (on_start can chain)
            next_wave = room_waves.waves[room_waves.current_wave]
            if next_wave.trigger == 'on_start':
                update_wave_system(
                    world, room_waves, room_w, room_h,
                    player_x, player_y, facing_x, facing_y, depth, dt
                )

    _tick_announcement(room_waves)


def _count_spawnable(group: SpawnGroup) -> int:
    """Count how many enemies in a group have working factories."""
    if WAVE_ENEMY_FACTORIES.get(group.enemy_type) is not None:
        return group.count
    return 0


def _tick_announcement(room_waves: RoomWaves):
    if room_waves.announcement_timer > 0:
        room_waves.announcement_timer -= 1
        if room_waves.announcement_timer <= 0:
            room_waves.active_announcement = None


def _spawn_telegraphs(
    world: World, group: SpawnGroup,
    room_w: int, room_h: int,
    player_x: float, player_y: float,
    facing_x: float, facing_y: float,
    depth: int
):
    """Create spawn telegraph entities for a spawn group."""
    factory = WAVE_ENEMY_FACTORIES.get(group.enemy_type)
    if factory is None:
        return

    positions = _get_spawn_positions(
        group.spawn_pattern, group.count,
        room_w, room_h, player_x, player_y,
        facing_x, facing_y
    )

    for x, y in positions:
        eid = world.create_entity()
        world.add_component(eid, Position(x, y))
        world.add_component(eid, SpawnTelegraph(
            enemy_type=group.enemy_type,
            frames_remaining=30,
            total_frames=30,
            depth=depth,
        ))
        world.add_component(eid, Renderable(
            char='\u00d7',  # ×
            color=NEON_RED,
            layer=3,
            visible=True,
        ))


# =============================================================================
# TELEGRAPH SYSTEM
# =============================================================================

def telegraph_system(world: World) -> int:
    """
    Tick spawn telegraphs and spawn enemies when ready.
    Returns number of enemies spawned this frame.
    """
    spawned = 0
    to_destroy = []

    for eid, pos, telegraph, rend in world.query(
        Position, SpawnTelegraph, Renderable
    ):
        telegraph.frames_remaining -= 1

        # Flicker effect
        if telegraph.frames_remaining > 5:
            rend.visible = (telegraph.frames_remaining % 4) < 3
            rend.color = NEON_RED if (telegraph.frames_remaining % 6) < 3 else 52
        else:
            # Bright flash in final frames
            rend.visible = True
            rend.color = NEON_YELLOW if (telegraph.frames_remaining % 2) == 0 else WHITE

        if telegraph.frames_remaining <= 0:
            factory = WAVE_ENEMY_FACTORIES.get(telegraph.enemy_type)
            if factory:
                enemy_id = factory(world, pos.x, pos.y)
                _apply_depth_scaling(world, enemy_id, telegraph.depth)

                # Spawn invulnerability (0.2 seconds)
                world.add_component(enemy_id, Invulnerable(frames_remaining=12))

                # Spawn burst
                spawn_explosion(
                    world, pos.x, pos.y,
                    count=6,
                    colors=[NEON_RED, NEON_YELLOW, WHITE],
                    chars=['*', '+', '.'],
                    speed_min=0.3, speed_max=0.8,
                    lifetime_min=8, lifetime_max=15,
                    gravity=0
                )
                spawned += 1

            to_destroy.append(eid)

    for eid in to_destroy:
        world.destroy_entity(eid)

    return spawned


# =============================================================================
# RENDER
# =============================================================================

def render_wave_announcement(renderer, room_waves: Optional[RoomWaves]):
    """Render wave announcement text."""
    if not room_waves or not room_waves.active_announcement:
        return

    text = room_waves.active_announcement
    width = renderer.width
    height = renderer.game_height

    cx = width // 2 - len(text) // 2
    cy = height // 2 - 3

    timer = room_waves.announcement_timer
    if timer > 60:
        color = NEON_YELLOW
    elif timer > 10:
        color = NEON_YELLOW if (timer % 6) < 4 else NEON_RED
    else:
        color = GRAY_DARK

    renderer.put_string(cx, cy, text, color, with_shake=False)


# =============================================================================
# ROOM CLEAR CHECK
# =============================================================================

def is_room_cleared(world: World, room_waves: Optional[RoomWaves]) -> bool:
    """
    Check if room is fully cleared.
    All waves triggered, no pending groups, no telegraphs, no alive enemies.
    """
    if room_waves is None:
        return False

    if not room_waves.all_waves_triggered:
        return False

    if room_waves.pending_groups:
        return False

    # Check for remaining telegraphs
    for eid, _ in world.query(SpawnTelegraph):
        return False

    # Check for remaining enemies
    for eid, _ in world.query(EnemyTag):
        if world.is_alive(eid):
            return False

    return room_waves.total_spawned > 0
