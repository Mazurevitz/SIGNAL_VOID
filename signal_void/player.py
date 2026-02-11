"""
Player Module
==============
Player entity creation and input handling.
"""

from typing import Set, Optional
import math

from .ecs import World
from .components import (
    Position, Velocity, Friction, MaxSpeed,
    Renderable, GhostTrail, CollisionBox,
    PlayerControlled, DashState, AttackState,
    PlayerTag, SyntaxBuffer, Health, Invulnerable,
    PlayerStats, WeaponInventory
)
from .engine import NEON_CYAN, NEON_MAGENTA, GRAY_LIGHT, GRAY_MED, GRAY_DARK, GRAY_DARKER, WHITE


def create_player(world: World, x: float, y: float) -> int:
    """Create the player entity with all required components."""
    entity_id = world.create_entity()

    # Core physics
    world.add_component(entity_id, Position(x, y))
    world.add_component(entity_id, Velocity(0, 0))
    world.add_component(entity_id, Friction(0.78))
    world.add_component(entity_id, MaxSpeed(0.7))
    world.add_component(entity_id, CollisionBox(1.0, 1.0))

    # Rendering
    world.add_component(entity_id, Renderable(
        char='@',
        color=NEON_CYAN,
        layer=10  # Player renders on top
    ))
    world.add_component(entity_id, GhostTrail(
        enabled=False,
        max_echoes=5,
        colors=[WHITE, GRAY_LIGHT, GRAY_MED, GRAY_DARK, GRAY_DARKER]
    ))

    # Player control
    world.add_component(entity_id, PlayerControlled(
        acceleration=0.20,
        last_move_dir_x=1.0,
        last_move_dir_y=0.0
    ))
    world.add_component(entity_id, DashState(
        speed=2.5,
        duration=8,
        cooldown=30
    ))
    world.add_component(entity_id, AttackState())

    # Combat
    world.add_component(entity_id, Health(100, 100))
    world.add_component(entity_id, SyntaxBuffer([], 3))

    # Tags
    world.add_component(entity_id, PlayerTag())

    # Persistent stats for micro-upgrades
    world.add_component(entity_id, PlayerStats())

    # Weapon inventory (starts with Slash)
    from .weapons import create_weapon
    slash = create_weapon('slash')
    world.add_component(entity_id, WeaponInventory(weapons=[slash], active_index=0))

    return entity_id


class InputHandler:
    """
    Handles player input with key hold detection.

    Uses frame-based timers to simulate key hold in terminals
    that don't support key-up events.
    """

    def __init__(self, hold_duration: int = 12):
        self.keys_held: dict = {}  # key -> frames remaining
        self.hold_duration = hold_duration
        self.freeze_movement_decay = False  # Set True during dash to preserve held keys

        # Actions triggered this frame (consumed on read)
        self._dash_triggered = False
        self._attack_direction: Optional[tuple] = None
        self._execute_triggered = False
        self._quit_triggered = False
        self._toggle_fps = False
        self._debug_depth = False
        self._swap_weapon = False
        self._debug_weapon = False
        self._toggle_entity_count = False

    def process_key(self, key) -> None:
        """Process a single key press from blessed's inkey()."""
        if key is None or not key:
            return

        key_str = key.lower() if not key.is_sequence else ''

        # Quit
        if key_str == 'q' or key.name == 'KEY_ESCAPE':
            self._quit_triggered = True
            return

        # Movement keys (WASD) - refresh hold timer
        if key_str in 'wasd':
            self.keys_held[key_str] = self.hold_duration

        # Dash (spacebar)
        elif key_str == ' ':
            self._dash_triggered = True

        # Attack (IJKL)
        elif key_str == 'i':
            self._attack_direction = (0, -1)
        elif key_str == 'k':
            self._attack_direction = (0, 1)
        elif key_str == 'j':
            self._attack_direction = (-1, 0)
        elif key_str == 'l':
            self._attack_direction = (1, 0)

        # Execute syntax chain
        elif key_str == 'h':
            self._execute_triggered = True

        # Toggle FPS display
        elif key.name == 'KEY_F1' or key_str == 'f':
            self._toggle_fps = True

        # Weapon swap (TAB)
        elif key.name == 'KEY_TAB':
            self._swap_weapon = True

        # Debug depth cycle
        elif key.name == 'KEY_F3':
            self._debug_depth = True

        # Debug weapon cycle
        elif key.name == 'KEY_F4':
            self._debug_weapon = True

        # Toggle entity count display
        elif key.name == 'KEY_F6':
            self._toggle_entity_count = True

    def update(self) -> None:
        """Update key hold timers (call once per frame)."""
        expired = []
        for key, frames in self.keys_held.items():
            # Don't decay movement keys during dash so they survive
            if self.freeze_movement_decay and key in 'wasd':
                continue
            self.keys_held[key] = frames - 1
            if self.keys_held[key] <= 0:
                expired.append(key)
        for key in expired:
            del self.keys_held[key]

    def get_movement_vector(self) -> tuple:
        """Get current movement direction based on held keys."""
        dx, dy = 0.0, 0.0
        if 'w' in self.keys_held:
            dy -= 1
        if 's' in self.keys_held:
            dy += 1
        if 'a' in self.keys_held:
            dx -= 1
        if 'd' in self.keys_held:
            dx += 1

        # Normalize diagonal movement
        if dx != 0 and dy != 0:
            length = math.sqrt(dx * dx + dy * dy)
            dx /= length
            dy /= length

        return dx, dy

    def consume_dash(self) -> bool:
        """Check and consume dash trigger."""
        triggered = self._dash_triggered
        self._dash_triggered = False
        return triggered

    def consume_attack(self) -> Optional[tuple]:
        """Check and consume attack trigger, returns direction or None."""
        direction = self._attack_direction
        self._attack_direction = None
        return direction

    def consume_execute(self) -> bool:
        """Check and consume syntax chain execute trigger."""
        triggered = self._execute_triggered
        self._execute_triggered = False
        return triggered

    def consume_quit(self) -> bool:
        """Check and consume quit trigger."""
        triggered = self._quit_triggered
        self._quit_triggered = False
        return triggered

    def consume_toggle_fps(self) -> bool:
        """Check and consume FPS toggle trigger."""
        triggered = self._toggle_fps
        self._toggle_fps = False
        return triggered

    def consume_debug_depth(self) -> bool:
        """Check and consume debug depth cycle trigger."""
        triggered = self._debug_depth
        self._debug_depth = False
        return triggered

    def consume_toggle_entity_count(self) -> bool:
        """Check and consume entity count toggle trigger."""
        triggered = self._toggle_entity_count
        self._toggle_entity_count = False
        return triggered

    def consume_swap_weapon(self) -> bool:
        """Check and consume weapon swap trigger."""
        triggered = self._swap_weapon
        self._swap_weapon = False
        return triggered

    def consume_debug_weapon(self) -> bool:
        """Check and consume debug weapon cycle trigger."""
        triggered = self._debug_weapon
        self._debug_weapon = False
        return triggered


def player_input_system(world: World, input_handler: InputHandler) -> None:
    """
    Apply input to player entity.

    Processes: Position, Velocity, PlayerControlled, DashState
    """
    for entity_id, pos, vel, ctrl, dash in world.query(
        Position, Velocity, PlayerControlled, DashState
    ):
        # Freeze movement key decay during dash so held keys survive
        input_handler.freeze_movement_decay = dash.frames_remaining > 0

        # Skip if dashing - dash overrides movement
        if dash.frames_remaining > 0:
            continue

        # Get movement input
        dx, dy = input_handler.get_movement_vector()

        # Apply acceleration
        if dx != 0 or dy != 0:
            vel.x += dx * ctrl.acceleration
            vel.y += dy * ctrl.acceleration

            # Track last movement direction
            ctrl.last_move_dir_x = dx
            ctrl.last_move_dir_y = dy

        # Handle dash trigger
        if input_handler.consume_dash():
            if dash.cooldown_remaining <= 0:
                # Determine dash direction
                if dx != 0 or dy != 0:
                    # Use current input direction
                    dash.direction_x = dx
                    dash.direction_y = dy
                elif abs(vel.x) > 0.1 or abs(vel.y) > 0.1:
                    # Use current velocity
                    speed = math.sqrt(vel.x * vel.x + vel.y * vel.y)
                    dash.direction_x = vel.x / speed
                    dash.direction_y = vel.y / speed
                else:
                    # Use last movement direction
                    dash.direction_x = ctrl.last_move_dir_x
                    dash.direction_y = ctrl.last_move_dir_y

                # Normalize
                length = math.sqrt(
                    dash.direction_x * dash.direction_x +
                    dash.direction_y * dash.direction_y
                )
                if length > 0:
                    dash.direction_x /= length
                    dash.direction_y /= length

                # Start dash
                dash.frames_remaining = dash.duration
                stats = world.get_component(entity_id, PlayerStats)
                if stats:
                    dash.cooldown_remaining = max(5, int(dash.cooldown * stats.dash_cooldown_multiplier))
                else:
                    dash.cooldown_remaining = dash.cooldown


def get_player_entity(world: World) -> Optional[int]:
    """Get the player entity ID."""
    for entity_id, _ in world.query(PlayerTag):
        return entity_id
    return None


def get_player_position(world: World) -> Optional[Position]:
    """Get the player's position component."""
    player_id = get_player_entity(world)
    if player_id is not None:
        return world.get_component(player_id, Position)
    return None
