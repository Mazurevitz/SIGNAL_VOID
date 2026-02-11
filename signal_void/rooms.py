"""
Room System
============
Room generation, transitions, and the "compile" animation.
"""

import random
import math
from typing import List, Optional

from .ecs import World
from .components import Position, Velocity, EnemyTag, Health
from .engine import (
    GameRenderer, GRAY_DARK, GRAY_DARKER, GRAY_MED,
    NEON_CYAN, NEON_MAGENTA, NEON_GREEN, WHITE
)
from .spawner import spawn_enemies_for_depth, is_boss_depth
from .player import get_player_position


# Fake code lines for the compile transition
_COMPILE_LINES = [
    'compiling signal_void::kernel...',
    'linking runtime.exec()',
    'resolving void_ptr -> 0x{:04X}',
    'malloc(depth * 0xFF) -> OK',
    'init thread_pool[{}]',
    'loading enemy_table.bin',
    'decrypt: ████████████ OK',
    'spawn_daemon --pid={}',
    'verify checksum... PASS',
    'injecting combat_sys v2.1',
    'patching memory @0x{:04X}',
    'kernel.depth = {}',
    'flush() -> sync OK',
    'READY.',
]


class RoomState:
    """Tracks room state and progression."""

    def __init__(self):
        self.depth = 1
        self.enemies_spawned = 0
        self.cleared = False
        self.transitioning = False
        self.transition_frame = 0
        self.transition_duration = 90  # 1.5 seconds at 60fps
        self._transition_lines: List[str] = []
        self.intro_text: Optional[str] = None
        self.intro_timer: int = 0
        self.waves = None  # RoomWaves from wave_spawner

    def set_intro(self, text: str, duration: int = 120):
        """Set intro text to display for a duration (frames)."""
        self.intro_text = text
        self.intro_timer = duration

    def update_intro(self) -> bool:
        """Tick intro timer. Returns True when intro is finished."""
        if self.intro_timer <= 0:
            return True
        self.intro_timer -= 1
        if self.intro_timer <= 0:
            self.intro_text = None
            return True
        return False

    def check_cleared(self, world: World) -> bool:
        """Check if all enemies are dead (wave-aware)."""
        if self.waves is not None:
            from .wave_spawner import is_room_cleared
            self.cleared = is_room_cleared(world, self.waves)
            return self.cleared

        # Legacy fallback
        enemy_count = 0
        for entity_id, _ in world.query(EnemyTag):
            if world.is_alive(entity_id):
                enemy_count += 1

        self.cleared = enemy_count == 0 and self.enemies_spawned > 0
        return self.cleared

    def start_transition(self):
        """Start the room transition animation."""
        self.transitioning = True
        self.transition_frame = 0
        # Pre-generate compile lines for this transition
        self._transition_lines = []
        next_depth = self.depth + 1
        for template in _COMPILE_LINES:
            try:
                line = template.format(
                    random.randint(0x1000, 0xFFFF),
                    next_depth
                )
            except (IndexError, KeyError):
                line = template
            self._transition_lines.append(line)

    def update_transition(self) -> bool:
        """
        Update transition animation.

        Returns True when transition is complete.
        """
        if not self.transitioning:
            return False

        self.transition_frame += 1
        if self.transition_frame >= self.transition_duration:
            self.transitioning = False
            self.depth += 1
            self.cleared = False
            self.enemies_spawned = 0
            return True

        return False


def spawn_room(world: World, room_state: RoomState, width: int, height: int):
    """
    Spawn enemies for a new room based on current depth.

    Uses the spawn table for structured progression.
    Boss depths are skipped (placeholder for future phases).
    """
    if is_boss_depth(room_state.depth):
        return

    player_pos = get_player_position(world)
    player_x = player_pos.x if player_pos else width / 2
    player_y = player_pos.y if player_pos else height / 2

    entities = spawn_enemies_for_depth(
        world,
        depth=room_state.depth,
        room_width=width,
        room_height=height,
        player_x=player_x,
        player_y=player_y,
    )

    room_state.enemies_spawned = len(entities)


def render_compile_transition(
    renderer: GameRenderer,
    room_state: RoomState,
    width: int,
    height: int
):
    """
    Render the "compile" transition animation.

    Phase 1: Screen fills with scrolling code lines (terminal compile effect)
    Phase 2: Flash
    Phase 3: New room border fades in
    """
    if not room_state.transitioning:
        return

    progress = room_state.transition_frame / room_state.transition_duration
    lines = room_state._transition_lines

    # Phase 1: Scrolling compile output (0-0.65)
    if progress < 0.65:
        phase_progress = progress / 0.65
        # How many lines to show (reveal progressively)
        visible_count = int(phase_progress * len(lines))

        # Scroll offset so lines scroll upward as more appear
        scroll_start = max(0, visible_count - height + 2)

        for i in range(scroll_start, visible_count):
            draw_y = i - scroll_start
            if draw_y >= height:
                break

            line = lines[i % len(lines)]
            # Prefix with prompt
            prefix = f'[{room_state.depth}]> '
            full_line = prefix + line

            # Newest line is bright, older lines dim
            age = visible_count - i
            if age <= 1:
                color = NEON_GREEN
            elif age <= 3:
                color = NEON_CYAN
            elif age <= 6:
                color = GRAY_MED
            else:
                color = GRAY_DARK

            renderer.put_string(1, draw_y, full_line[:width - 2], color, with_shake=False)

        # Blinking cursor on the newest line
        cursor_y = min(visible_count - scroll_start, height - 1)
        if room_state.transition_frame % 8 < 4:
            cursor_x = 1
            if visible_count > 0:
                last_line = f'[{room_state.depth}]> ' + lines[(visible_count - 1) % len(lines)]
                cursor_x = min(len(last_line) + 1, width - 2)
            renderer.put(cursor_x, cursor_y, '_', NEON_GREEN, with_shake=False)

    # Phase 2: Flash frames (0.65-0.80)
    elif progress < 0.80:
        flash_progress = (progress - 0.65) / 0.15
        frame_idx = int(flash_progress * 6)
        if frame_idx % 2 == 0:
            # Bright magenta flash
            for y in range(min(3, height)):
                flash_text = '=' * width
                renderer.put_string(0, height // 2 - 1 + y, flash_text, NEON_MAGENTA, with_shake=False)
            # Center text
            msg = f'>> DEPTH {room_state.depth + 1} <<'
            cx = width // 2 - len(msg) // 2
            renderer.put_string(cx, height // 2, msg, WHITE, with_shake=False)

    # Phase 3: New room fades in (0.80-1.0)
    else:
        fade_progress = (progress - 0.80) / 0.20
        if fade_progress > 0.3:
            renderer.draw_box(0, 0, width, height, GRAY_DARK, '#', with_shake=False)
        if fade_progress > 0.6:
            # Show depth indicator
            msg = f'DEPTH {room_state.depth + 1}'
            cx = width // 2 - len(msg) // 2
            renderer.put_string(cx, height // 2, msg, NEON_CYAN, with_shake=False)


def get_room_difficulty(depth: int) -> dict:
    """Get difficulty parameters for a room based on depth."""
    return {
        'enemy_count': min(3 + depth, 10),
        'enemy_health_mult': 1.0 + (depth * 0.1),
        'enemy_speed_mult': 1.0 + (depth * 0.05),
        'enemy_damage_mult': 1.0 + (depth * 0.1)
    }
