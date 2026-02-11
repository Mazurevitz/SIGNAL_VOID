"""
Syntax Chain System
====================
Verb collection, buffer UI, and Logic Blast execution.
"""

from typing import Dict, Callable, Optional
import math

from .ecs import World
from .components import Position, SyntaxBuffer, PlayerTag, EnemyTag, Health, AttackMultiplier, PlayerStats
from .engine import GameRenderer, NEON_MAGENTA, NEON_CYAN, WHITE
from .player import get_player_entity


# =============================================================================
# VERB DEFINITIONS
# =============================================================================
# Verbs and their effects are data-driven for easy extension.

VERB_EFFECTS: Dict[str, dict] = {
    'RECURSIVE': {
        'description': 'Next attack hits twice',
        'color': 46,  # Green
        'on_execute': lambda world, player_id: apply_recursive(world, player_id)
    },
    'SUDO': {
        'description': 'Temporary invincibility',
        'color': 208,  # Orange
        'on_execute': lambda world, player_id: apply_sudo(world, player_id)
    },
    'DASH': {
        'description': 'Increased move speed',
        'color': 51,  # Cyan
        'on_execute': lambda world, player_id: apply_dash_boost(world, player_id)
    },
    'SLICE': {
        'description': 'Damage boost',
        'color': 196,  # Red
        'on_execute': lambda world, player_id: apply_damage_boost(world, player_id)
    },
    'VOID': {
        'description': 'Area damage',
        'color': 201,  # Magenta
        'on_execute': lambda world, player_id: apply_void_damage(world, player_id)
    },
    'NULL': {
        'description': 'Reset cooldowns',
        'color': 255,  # White
        'on_execute': lambda world, player_id: apply_cooldown_reset(world, player_id)
    }
}


# =============================================================================
# VERB EFFECT IMPLEMENTATIONS
# =============================================================================

def apply_recursive(world: World, player_id: int):
    """Apply RECURSIVE effect - next attack hits twice."""
    existing = world.get_component(player_id, AttackMultiplier)
    if existing:
        existing.hits = 2
        existing.uses_remaining = 3
    else:
        world.add_component(player_id, AttackMultiplier(
            hits=2, uses_remaining=3
        ))


def apply_sudo(world: World, player_id: int):
    """Apply SUDO effect - temporary invincibility."""
    from .components import Invulnerable
    world.add_component(player_id, Invulnerable(frames_remaining=180))  # 3 seconds


def apply_dash_boost(world: World, player_id: int):
    """Apply DASH effect - increased move speed."""
    from .components import MaxSpeed
    max_speed = world.get_component(player_id, MaxSpeed)
    if max_speed:
        max_speed.value *= 1.5  # 50% speed boost


def apply_damage_boost(world: World, player_id: int):
    """Apply SLICE effect - damage boost for next 5 attacks."""
    existing = world.get_component(player_id, AttackMultiplier)
    if existing:
        existing.damage_multiplier = 2.0
        existing.uses_remaining = max(existing.uses_remaining, 5)
    else:
        world.add_component(player_id, AttackMultiplier(
            damage_multiplier=2.0, uses_remaining=5
        ))


def apply_void_damage(world: World, player_id: int):
    """Apply VOID effect - area damage to all enemies."""
    player_pos = world.get_component(player_id, Position)
    if not player_pos:
        return

    stats = world.get_component(player_id, PlayerStats)
    blast_radius = 15.0
    if stats:
        blast_radius *= stats.logic_blast_radius_multiplier

    for entity_id, pos, health, _ in world.query(Position, Health, EnemyTag):
        dx = pos.x - player_pos.x
        dy = pos.y - player_pos.y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < blast_radius:
            health.current -= 25


def apply_cooldown_reset(world: World, player_id: int):
    """Apply NULL effect - reset all cooldowns."""
    from .components import DashState
    dash = world.get_component(player_id, DashState)
    if dash:
        dash.cooldown_remaining = 0


# =============================================================================
# SYNTAX CHAIN FUNCTIONS
# =============================================================================

def add_verb(world: World, verb: str) -> bool:
    """
    Add a verb to the player's syntax buffer.

    Returns True if verb was added, False if buffer is full.
    """
    player_id = get_player_entity(world)
    if player_id is None:
        return False

    buffer = world.get_component(player_id, SyntaxBuffer)
    if buffer is None:
        return False

    if len(buffer.verbs) < buffer.max_verbs:
        buffer.verbs.append(verb)
        return True

    return False


def remove_verb(world: World) -> Optional[str]:
    """
    Remove a verb from the player's syntax buffer (FIFO).

    Returns the removed verb or None if buffer is empty.
    """
    player_id = get_player_entity(world)
    if player_id is None:
        return None

    buffer = world.get_component(player_id, SyntaxBuffer)
    if buffer is None or not buffer.verbs:
        return None

    return buffer.verbs.pop(0)


def is_buffer_full(world: World) -> bool:
    """Check if the syntax buffer is full."""
    player_id = get_player_entity(world)
    if player_id is None:
        return False

    buffer = world.get_component(player_id, SyntaxBuffer)
    if buffer is None:
        return False

    return len(buffer.verbs) >= buffer.max_verbs


def execute_syntax_chain(world: World, renderer: GameRenderer) -> bool:
    """
    Execute the syntax chain if buffer is full.

    Returns True if chain was executed.
    """
    if not is_buffer_full(world):
        return False

    player_id = get_player_entity(world)
    if player_id is None:
        return False

    buffer = world.get_component(player_id, SyntaxBuffer)
    if buffer is None:
        return False

    # Execute all verb effects
    for verb in buffer.verbs:
        if verb in VERB_EFFECTS:
            effect = VERB_EFFECTS[verb]
            if 'on_execute' in effect:
                effect['on_execute'](world, player_id)

    # Trigger Logic Blast visual
    trigger_logic_blast(world, renderer)

    # Clear buffer
    buffer.verbs.clear()

    return True


def trigger_logic_blast(world: World, renderer: GameRenderer):
    """
    Trigger the Logic Blast visual effect.

    Expanding circular wave of ASCII characters that damages all enemies.
    """
    player_id = get_player_entity(world)
    if player_id is None:
        return

    player_pos = world.get_component(player_id, Position)
    if player_pos is None:
        return

    # Screen shake + hitstop for impact
    renderer.trigger_shake(intensity=3, frames=10)
    renderer.trigger_hitstop(5)

    # Compute blast radius from stats
    stats = world.get_component(player_id, PlayerStats)
    blast_radius = 15.0
    if stats:
        blast_radius *= stats.logic_blast_radius_multiplier

    # Damage enemies within blast radius with knockback from player
    from .components import Knockback
    for entity_id, pos, health, _ in world.query(Position, Health, EnemyTag):
        dx = pos.x - player_pos.x
        dy = pos.y - player_pos.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > blast_radius:
            continue
        health.current -= 50
        # Knockback away from player
        if dist > 0:
            kb_x = dx / dist * 2.0
            kb_y = dy / dist * 2.0
            world.add_component(entity_id, Knockback(kb_x, kb_y, decay=0.6))

    # Expanding wave particles
    from .particles import spawn_logic_blast_wave
    spawn_logic_blast_wave(world, player_pos.x, player_pos.y)
