"""
Spawn Table and Progression System
====================================
Structured enemy spawning with depth-based progression,
weighted selection, and intro text flashes.
"""

import random
from typing import Dict, List, Optional, Tuple

from .ecs import World
from .enemies import (
    create_buffer_leak, create_firewall, create_overclocker,
    _apply_depth_scaling
)
from .components import Health


# =============================================================================
# SPAWN TABLE
# =============================================================================
# Maps depth -> (enemy_pool, count_range, intro_text)
# Boss depths map to "BOSS: NAME" strings (placeholder).
# intro_text is only shown the first time a new enemy type appears.

SPAWN_TABLE: Dict[int, object] = {
    1:  (['buffer_leak'], (2, 3), None),
    2:  (['buffer_leak'], (3, 4), None),
    3:  (['buffer_leak', 'firewall'], (3, 4),
         'NEW THREAT DETECTED: [H] FIREWALL'),
    4:  (['buffer_leak', 'firewall'], (3, 5), None),
    5:  'BOSS: KERNEL_PANIC',
    6:  (['buffer_leak', 'firewall', 'overclocker'], (3, 5),
         'NEW THREAT DETECTED: >> OVERCLOCKER'),
    7:  (['buffer_leak', 'firewall', 'overclocker'], (4, 5), None),
    8:  (['buffer_leak', 'firewall', 'overclocker'], (4, 6), None),
    9:  (['buffer_leak', 'firewall', 'overclocker', 'worm'], (4, 6),
         'NEW THREAT DETECTED: ~ WORM'),
    10: 'BOSS: STACK_OVERFLOW',
    11: (['buffer_leak', 'firewall', 'overclocker', 'worm'], (4, 7), None),
    12: (['buffer_leak', 'firewall', 'overclocker', 'worm', 'daemon'], (5, 7),
         'NEW THREAT DETECTED: $ DAEMON'),
    13: (['buffer_leak', 'firewall', 'overclocker', 'worm', 'daemon'], (5, 7), None),
    14: (['buffer_leak', 'firewall', 'overclocker', 'worm', 'daemon', 'trojan'], (5, 8),
         'NEW THREAT DETECTED: % TROJAN'),
    15: 'BOSS: ROOT_ACCESS',
}

# Default config for depth 16+
_DEFAULT_POOL = ['buffer_leak', 'firewall', 'overclocker', 'worm', 'daemon', 'trojan']
_DEFAULT_COUNT = (5, 8)


# =============================================================================
# ENEMY WEIGHTS
# =============================================================================

ENEMY_WEIGHTS: Dict[str, int] = {
    'buffer_leak': 3,
    'firewall': 2,
    'overclocker': 2,
    'worm': 1,
    'daemon': 1,
    'trojan': 1,
}


# =============================================================================
# ENEMY FACTORIES
# =============================================================================
# Maps type strings to factory functions.
# Unknown types (worm/daemon/trojan) return None until implemented.

ENEMY_FACTORIES: Dict[str, object] = {
    'buffer_leak': create_buffer_leak,
    'firewall': create_firewall,
    'overclocker': create_overclocker,
    # Future enemy types — silently skipped when selected
    'worm': None,
    'daemon': None,
    'trojan': None,
}


# =============================================================================
# INTRODUCED TYPES TRACKING
# =============================================================================

_introduced_types: set = set()


def reset_introduced():
    """Clear the set of introduced enemy types. Call on new game."""
    global _introduced_types
    _introduced_types = set()


# =============================================================================
# QUERY FUNCTIONS
# =============================================================================

def get_spawn_config(depth: int) -> Tuple[List[str], Tuple[int, int], Optional[str]]:
    """
    Get spawn configuration for a given depth.

    Returns (enemy_pool, count_range, intro_text).
    For boss depths, returns empty pool with no enemies.
    For depth 16+, returns the default full-pool config.
    """
    if depth in SPAWN_TABLE:
        entry = SPAWN_TABLE[depth]
        if isinstance(entry, str):
            # Boss depth — return empty config
            return [], (0, 0), None
        return entry
    # Depth 16+: default config
    return _DEFAULT_POOL, _DEFAULT_COUNT, None


def is_boss_depth(depth: int) -> bool:
    """Check if a depth is a boss encounter (placeholder)."""
    entry = SPAWN_TABLE.get(depth)
    return isinstance(entry, str)


def get_intro_text(depth: int) -> Optional[str]:
    """
    Get intro text for a depth, but only if it hasn't been shown yet.

    Returns the intro text string or None.
    """
    if is_boss_depth(depth):
        return None

    pool, _, intro = get_spawn_config(depth)
    if intro is None:
        return None

    # Check if all enemy types in pool have been introduced already
    new_types = set(pool) - _introduced_types
    if not new_types:
        return None

    # Mark all types in pool as introduced
    _introduced_types.update(pool)
    return intro


# =============================================================================
# WEIGHTED ENEMY SELECTION
# =============================================================================

def _select_weighted_enemies(pool: List[str], count: int) -> List[str]:
    """
    Select enemies from pool using weighted random selection.

    Guarantees at least 1 of each type in pool if count permits,
    then fills remaining slots with weighted random.choices().
    """
    if not pool or count <= 0:
        return []

    # Filter pool to only types that have factories
    available = [t for t in pool if ENEMY_FACTORIES.get(t) is not None]
    if not available:
        return []

    selected = []

    # Guarantee at least 1 of each available type (if count permits)
    if count >= len(available):
        selected = list(available)
        remaining = count - len(available)
    else:
        # Not enough slots for all types — just do weighted selection
        weights = [ENEMY_WEIGHTS.get(t, 1) for t in available]
        selected = random.choices(available, weights=weights, k=count)
        random.shuffle(selected)
        return selected

    # Fill remaining slots with weighted selection
    if remaining > 0:
        weights = [ENEMY_WEIGHTS.get(t, 1) for t in available]
        extras = random.choices(available, weights=weights, k=remaining)
        selected.extend(extras)

    random.shuffle(selected)
    return selected


# =============================================================================
# SPAWN FUNCTION
# =============================================================================

def spawn_enemies_for_depth(
    world: World,
    depth: int,
    room_width: int,
    room_height: int,
    player_x: float,
    player_y: float,
    min_distance: float = 8.0
) -> list:
    """
    Spawn enemies for a room based on depth using the spawn table.

    Replaces the old spawn_enemies_for_room function.
    Returns list of spawned entity IDs.
    """
    import math

    pool, count_range, _ = get_spawn_config(depth)
    if not pool or count_range == (0, 0):
        return []

    # Determine enemy count
    count = random.randint(count_range[0], count_range[1])

    # Select enemy types
    enemy_types = _select_weighted_enemies(pool, count)

    entities = []
    margin = 3

    for enemy_type in enemy_types:
        factory = ENEMY_FACTORIES.get(enemy_type)
        if factory is None:
            # Unknown type — skip silently
            continue

        # Find valid spawn position
        attempts = 0
        while attempts < 20:
            x = random.uniform(margin, room_width - margin)
            y = random.uniform(margin, room_height - margin)

            dx = x - player_x
            dy = y - player_y
            dist = math.sqrt(dx * dx + dy * dy)

            if dist >= min_distance:
                eid = factory(world, x, y)
                _apply_depth_scaling(world, eid, depth)

                # Additional compounding HP scaling for depth 16+
                if depth > 15:
                    health = world.get_component(eid, Health)
                    if health:
                        multiplier = 1.1 ** (depth - 15)
                        health.maximum = int(health.maximum * multiplier)
                        health.current = health.maximum

                entities.append(eid)
                break

            attempts += 1

    return entities
