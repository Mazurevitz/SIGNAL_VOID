"""
Micro-Upgrade System
=====================
Upgrade data, selection logic, application, and overlay rendering.
"""

import random

from .ecs import World
from .components import PlayerStats, Health, SyntaxBuffer
from .engine import (
    GameRenderer, NEON_CYAN, NEON_MAGENTA, NEON_YELLOW,
    NEON_GREEN, NEON_RED, WHITE, GRAY_DARK, GRAY_MED, GRAY_DARKER
)


# =============================================================================
# UPGRADE DEFINITIONS
# =============================================================================

UPGRADES = {
    # --- Offense ---
    'dmg_up': {
        'name': '+15% DMG',
        'category': 'offense',
        'stat': 'damage_multiplier',
        'per_level': 0.15,
        'max_level': 5,
    },
    'atk_speed': {
        'name': '+12% ATK SPD',
        'category': 'offense',
        'stat': 'attack_speed_multiplier',
        'per_level': 0.12,
        'max_level': 5,
    },
    'atk_size': {
        'name': '+20% ATK SIZE',
        'category': 'offense',
        'stat': 'attack_size_multiplier',
        'per_level': 0.20,
        'max_level': 3,
    },
    'crit_chance': {
        'name': '+8% CRIT',
        'category': 'offense',
        'stat': 'crit_chance',
        'per_level': 0.08,
        'max_level': 5,
    },
    'crit_dmg': {
        'name': '+50% CRIT DMG',
        'category': 'offense',
        'stat': 'crit_damage_multiplier',
        'per_level': 0.50,
        'max_level': 3,
    },
    # --- Defense ---
    'max_hp': {
        'name': '+20 MAX HP',
        'category': 'defense',
        'stat': 'bonus_max_hp',
        'per_level': 20,
        'max_level': 5,
    },
    'dmg_reduce': {
        'name': '+8% ARMOR',
        'category': 'defense',
        'stat': 'damage_reduction',
        'per_level': 0.08,
        'max_level': 5,
    },
    'iframes': {
        'name': '+10 I-FRAMES',
        'category': 'defense',
        'stat': 'invincibility_frames',
        'per_level': 10,
        'max_level': 3,
    },
    'dash_cd': {
        'name': '-12% DASH CD',
        'category': 'defense',
        'stat': 'dash_cooldown_multiplier',
        'per_level': -0.12,
        'max_level': 4,
    },
    'heal_rate': {
        'name': '+5% HEAL',
        'category': 'defense',
        'stat': 'heal_bonus',
        'per_level': 0.05,
        'max_level': 3,
    },
    # --- Utility ---
    'move_speed': {
        'name': '+10% SPEED',
        'category': 'utility',
        'stat': 'move_speed_multiplier',
        'per_level': 0.10,
        'max_level': 5,
    },
    'verb_drop': {
        'name': '+10% VERB DROP',
        'category': 'utility',
        'stat': 'verb_drop_rate',
        'per_level': 0.10,
        'max_level': 3,
    },
    'buffer_slot': {
        'name': '+1 BUFFER SLOT',
        'category': 'utility',
        'stat': 'bonus_buffer_slots',
        'per_level': 1,
        'max_level': 2,
    },
    'blast_radius': {
        'name': '+25% BLAST',
        'category': 'utility',
        'stat': 'logic_blast_radius_multiplier',
        'per_level': 0.25,
        'max_level': 3,
    },
    'projectile': {
        'name': '+1 PROJECTILE',
        'category': 'utility',
        'stat': 'bonus_projectile_count',
        'per_level': 1,
        'max_level': 2,
    },
}

CATEGORY_COLORS = {
    'offense': NEON_RED,
    'defense': NEON_GREEN,
    'utility': NEON_CYAN,
}


# =============================================================================
# SELECTION
# =============================================================================

def select_upgrades(stats: PlayerStats, count: int = 3) -> list:
    """Pick up to `count` non-maxed upgrades with category diversity."""
    # Group available (non-maxed) upgrades by category
    by_category = {}
    for uid, data in UPGRADES.items():
        current = stats.upgrade_counts.get(uid, 0)
        if current < data['max_level']:
            cat = data['category']
            by_category.setdefault(cat, []).append(uid)

    if not by_category:
        return []

    chosen = []
    categories = list(by_category.keys())
    random.shuffle(categories)

    # Pick 1 from each category (up to count)
    for cat in categories:
        if len(chosen) >= count:
            break
        pick = random.choice(by_category[cat])
        chosen.append(pick)
        by_category[cat].remove(pick)

    # Fill remaining slots from largest pools
    if len(chosen) < count:
        remaining = []
        for cat in by_category:
            remaining.extend(by_category[cat])
        random.shuffle(remaining)
        for uid in remaining:
            if uid not in chosen and len(chosen) < count:
                chosen.append(uid)

    random.shuffle(chosen)
    return chosen


# =============================================================================
# APPLICATION
# =============================================================================

def apply_upgrade(world: World, player_id: int, upgrade_id: str):
    """Apply a single upgrade level to the player."""
    stats = world.get_component(player_id, PlayerStats)
    if stats is None:
        return

    data = UPGRADES.get(upgrade_id)
    if data is None:
        return

    current_level = stats.upgrade_counts.get(upgrade_id, 0)
    if current_level >= data['max_level']:
        return

    # Increment count
    stats.upgrade_counts[upgrade_id] = current_level + 1

    # Apply stat change
    stat_name = data['stat']
    old_val = getattr(stats, stat_name)
    setattr(stats, stat_name, old_val + data['per_level'])

    # Special cases: directly modify other components
    if upgrade_id == 'max_hp':
        health = world.get_component(player_id, Health)
        if health:
            health.maximum += 20
            health.current += 20

    elif upgrade_id == 'buffer_slot':
        buf = world.get_component(player_id, SyntaxBuffer)
        if buf:
            buf.max_verbs += 1


# =============================================================================
# RENDERING
# =============================================================================

def render_upgrade_select(renderer: GameRenderer, choices: list,
                          stats: PlayerStats, frame: int):
    """Render the upgrade selection overlay."""
    width = renderer.width
    height = renderer.game_height

    # Box dimensions
    box_w = 40
    box_h = 4 + len(choices) * 2 + 2
    box_x = width // 2 - box_w // 2
    box_y = height // 2 - box_h // 2

    # Draw box background (clear area)
    for row in range(box_h):
        renderer.buffer.put_string(
            box_x, box_y + row, ' ' * box_w, GRAY_DARK
        )

    # Border
    top = '\u250c\u2500\u2500\u2500 RUNTIME PATCH ' + '\u2500' * (box_w - 20) + '\u2510'
    bot = '\u2514' + '\u2500' * (box_w - 2) + '\u2518'
    renderer.buffer.put_string(box_x, box_y, top, NEON_MAGENTA)
    renderer.buffer.put_string(box_x, box_y + box_h - 1, bot, NEON_MAGENTA)
    for row in range(1, box_h - 1):
        renderer.buffer.put_string(box_x, box_y + row, '\u2502', NEON_MAGENTA)
        renderer.buffer.put_string(box_x + box_w - 1, box_y + row, '\u2502', NEON_MAGENTA)

    # Choices
    for i, uid in enumerate(choices):
        data = UPGRADES[uid]
        row_y = box_y + 2 + i * 2
        cat_color = CATEGORY_COLORS.get(data['category'], WHITE)
        current = stats.upgrade_counts.get(uid, 0)
        max_lvl = data['max_level']

        # Key prompt
        key_str = f'[{i + 1}]'
        renderer.buffer.put_string(box_x + 2, row_y, key_str, WHITE)

        # Upgrade name
        renderer.buffer.put_string(box_x + 6, row_y, data['name'], cat_color)

        # Level bar
        bar_filled = '|' * current
        bar_empty = '.' * (max_lvl - current)
        bar_str = bar_filled + bar_empty
        level_str = f'{bar_str}  {current}/{max_lvl}'
        renderer.buffer.put_string(box_x + box_w - len(level_str) - 2, row_y, level_str, GRAY_MED)

    # Prompt
    prompt_y = box_y + box_h - 2
    prompt = 'PRESS 1, 2, or 3'
    # Blink prompt
    if (frame // 20) % 2 == 0:
        px = box_x + box_w // 2 - len(prompt) // 2
        renderer.buffer.put_string(px, prompt_y, prompt, NEON_YELLOW)
