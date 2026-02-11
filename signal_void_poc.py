#!/usr/bin/env python3
"""
SIGNAL_VOID - A Terminal Hack-and-Slash POC
============================================
A neon-drenched, kinetic combat experience in your terminal.

Controls:
    WASD        - Move
    IJKL        - Slash Attack (I=up, K=down, J=left, L=right)
    Spacebar    - Dash
    H           - Execute Syntax Chain (when 3 verbs collected)
    Q/Escape    - Quit
"""

import random
import math
import time
import sys
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum, auto

try:
    from blessed import Terminal
except ImportError:
    print("ERROR: 'blessed' library required. Install with: pip install blessed")
    sys.exit(1)


# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

TARGET_FPS = 60
FRAME_TIME = 1.0 / TARGET_FPS

# Physics
PLAYER_ACCEL = 2.5
PLAYER_FRICTION = 0.85
PLAYER_MAX_SPEED = 1.2
DASH_SPEED = 3.5
DASH_DURATION = 8  # frames
DASH_COOLDOWN = 30  # frames

# Visual
DASH_ECHO_COUNT = 5
DASH_ECHO_LIFETIME = 5
SCREEN_SHAKE_DURATION = 3
SCREEN_SHAKE_INTENSITY = 2
PARTICLE_GRAVITY = 0.15
PARTICLE_LIFETIME = 30

# Braille sub-pixel rendering (2x4 dots per character)
BRAILLE_BASE = 0x2800
BRAILLE_DOTS = [
    (0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (0, 3, 0x40),
    (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (1, 3, 0x80),
]

# Color palettes (ANSI 256 color indices)
NEON_CYAN = 51
NEON_MAGENTA = 201
NEON_YELLOW = 226
NEON_GREEN = 46
NEON_RED = 196
NEON_ORANGE = 208

GRAY_LIGHT = 252
GRAY_MED = 245
GRAY_DARK = 238
GRAY_DARKER = 235

# Verbs for the Syntax Chain
VERBS = ["SLICE", "DASH", "VOID", "REND", "SEVER", "NULL", "BREAK", "CRASH"]


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Vec2:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: 'Vec2') -> 'Vec2':
        return Vec2(self.x + other.x, self.y + other.y)

    def __mul__(self, scalar: float) -> 'Vec2':
        return Vec2(self.x * scalar, self.y * scalar)

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y)

    def normalized(self) -> 'Vec2':
        l = self.length()
        if l > 0:
            return Vec2(self.x / l, self.y / l)
        return Vec2(0, 0)

    def copy(self) -> 'Vec2':
        return Vec2(self.x, self.y)


@dataclass
class Particle:
    pos: Vec2
    vel: Vec2
    char: str
    color: int
    lifetime: int
    max_lifetime: int
    gravity: float = PARTICLE_GRAVITY

    def update(self) -> bool:
        """Update particle, returns False if dead."""
        self.vel.y += self.gravity
        self.pos = self.pos + self.vel
        self.lifetime -= 1
        return self.lifetime > 0


@dataclass
class DashEcho:
    pos: Vec2
    lifetime: int
    max_lifetime: int = DASH_ECHO_LIFETIME


@dataclass
class SlashArc:
    center: Vec2
    direction: Vec2
    radius: float
    lifetime: int
    chars: List[Tuple[int, int, str]]  # pre-computed arc positions


@dataclass
class Star:
    x: float
    y: float
    speed: float
    char: str
    color: int


@dataclass
class Enemy:
    pos: Vec2
    char: str = 'X'
    color: int = NEON_RED
    health: int = 1
    hit_flash: int = 0


@dataclass
class Player:
    pos: Vec2
    vel: Vec2 = field(default_factory=lambda: Vec2(0, 0))
    char: str = '@'
    color: int = NEON_CYAN
    dashing: int = 0
    dash_cooldown: int = 0
    dash_dir: Vec2 = field(default_factory=lambda: Vec2(0, 0))
    invulnerable: int = 0
    last_move_dir: Vec2 = field(default_factory=lambda: Vec2(1, 0))  # Last movement direction


# =============================================================================
# VIRTUAL BUFFER (Double Buffering)
# =============================================================================

class VirtualBuffer:
    """Double-buffered terminal rendering to prevent flicker."""

    def __init__(self, width: int, height: int, term: Terminal):
        self.width = width
        self.height = height
        self.term = term
        self.buffer: List[List[Tuple[str, int]]] = []
        self.prev_buffer: List[List[Tuple[str, int]]] = []
        self.clear()

    def clear(self):
        """Clear the buffer."""
        self.buffer = [[('' , 0) for _ in range(self.width)] for _ in range(self.height)]

    def resize(self, width: int, height: int):
        """Handle terminal resize."""
        self.width = width
        self.height = height
        self.prev_buffer = []
        self.clear()

    def put(self, x: int, y: int, char: str, color: int = 7):
        """Put a character in the buffer."""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.buffer[y][x] = (char, color)

    def put_string(self, x: int, y: int, text: str, color: int = 7):
        """Put a string in the buffer."""
        for i, char in enumerate(text):
            self.put(x + i, y, char, color)

    def render(self) -> str:
        """Render buffer to terminal, only updating changed cells."""
        output = []

        for y in range(self.height):
            for x in range(self.width):
                char, color = self.buffer[y][x]

                # Check if cell changed
                prev_char, prev_color = ('', 0)
                if self.prev_buffer and y < len(self.prev_buffer) and x < len(self.prev_buffer[y]):
                    prev_char, prev_color = self.prev_buffer[y][x]

                if char != prev_char or color != prev_color:
                    if char:
                        output.append(self.term.move_xy(x, y))
                        output.append(self.term.color(color))
                        output.append(char)
                    else:
                        output.append(self.term.move_xy(x, y))
                        output.append(' ')

        # Swap buffers
        self.prev_buffer = [row[:] for row in self.buffer]

        return ''.join(output)


# =============================================================================
# BRAILLE SUB-PIXEL RENDERER
# =============================================================================

class BrailleCanvas:
    """Sub-pixel rendering using Unicode Braille patterns."""

    def __init__(self, char_width: int, char_height: int):
        self.char_width = char_width
        self.char_height = char_height
        # Braille chars are 2 dots wide, 4 dots tall
        self.pixel_width = char_width * 2
        self.pixel_height = char_height * 4
        self.canvas: List[List[int]] = []
        self.colors: List[List[int]] = []
        self.clear()

    def clear(self):
        self.canvas = [[0 for _ in range(self.char_width)] for _ in range(self.char_height)]
        self.colors = [[7 for _ in range(self.char_width)] for _ in range(self.char_height)]

    def set_pixel(self, px: int, py: int, color: int = 7):
        """Set a sub-pixel dot."""
        if 0 <= px < self.pixel_width and 0 <= py < self.pixel_height:
            char_x = px // 2
            char_y = py // 4
            dot_x = px % 2
            dot_y = py % 4

            # Find the bit for this dot position
            for dx, dy, bit in BRAILLE_DOTS:
                if dx == dot_x and dy == dot_y:
                    self.canvas[char_y][char_x] |= bit
                    self.colors[char_y][char_x] = color
                    break

    def get_char(self, cx: int, cy: int) -> Tuple[str, int]:
        """Get the braille character at a cell position."""
        if 0 <= cx < self.char_width and 0 <= cy < self.char_height:
            pattern = self.canvas[cy][cx]
            if pattern > 0:
                return chr(BRAILLE_BASE + pattern), self.colors[cy][cx]
        return '', 7


# =============================================================================
# GAME STATE
# =============================================================================

class GameState:
    def __init__(self, term: Terminal):
        self.term = term
        self.width = term.width
        self.height = term.height - 3  # Reserve space for UI

        self.buffer = VirtualBuffer(self.width, self.height + 3, term)
        self.braille = BrailleCanvas(self.width, self.height)

        # Game objects
        self.player = Player(pos=Vec2(self.width / 2, self.height / 2))
        self.enemies: List[Enemy] = []
        self.particles: List[Particle] = []
        self.dash_echoes: List[DashEcho] = []
        self.slash_arcs: List[SlashArc] = []
        self.stars: List[Star] = []

        # Syntax Chain
        self.verb_chain: List[str] = []
        self.super_move_active: int = 0
        self.wave_radius: float = 0

        # Screen effects
        self.screen_shake: int = 0
        self.shake_offset = Vec2(0, 0)

        # Input state - keys with their hold timers
        self.keys_held = {}  # key -> frames remaining
        self.key_hold_duration = 8  # frames a key stays "held" after press

        # Spawn initial enemies and stars
        self._spawn_enemies(5)
        self._spawn_starfield()

    def _spawn_enemies(self, count: int):
        """Spawn enemies at random positions."""
        for _ in range(count):
            pos = Vec2(
                random.uniform(5, self.width - 5),
                random.uniform(3, self.height - 3)
            )
            # Don't spawn too close to player
            while (pos.x - self.player.pos.x) ** 2 + (pos.y - self.player.pos.y) ** 2 < 100:
                pos = Vec2(
                    random.uniform(5, self.width - 5),
                    random.uniform(3, self.height - 3)
                )
            self.enemies.append(Enemy(pos=pos, color=random.choice([NEON_RED, NEON_ORANGE, NEON_MAGENTA])))

    def _spawn_starfield(self):
        """Create parallax starfield background."""
        star_chars = ['.', '*', '+', '`', "'"]
        star_colors = [GRAY_DARKER, GRAY_DARK, GRAY_MED, GRAY_DARK, GRAY_DARKER]

        for _ in range(50):
            self.stars.append(Star(
                x=random.uniform(0, self.width),
                y=random.uniform(0, self.height),
                speed=random.uniform(0.02, 0.1),
                char=random.choice(star_chars),
                color=random.choice(star_colors)
            ))

    def handle_resize(self):
        """Handle terminal resize."""
        self.width = self.term.width
        self.height = self.term.height - 3
        self.buffer.resize(self.width, self.height + 3)
        self.braille = BrailleCanvas(self.width, self.height)


# =============================================================================
# GAME LOGIC
# =============================================================================

def update_player(state: GameState, dt: float):
    """Update player physics and state."""
    player = state.player

    # Decay key hold timers
    expired_keys = []
    for key, frames in state.keys_held.items():
        state.keys_held[key] = frames - 1
        if state.keys_held[key] <= 0:
            expired_keys.append(key)
    for key in expired_keys:
        del state.keys_held[key]

    # Handle dash state
    if player.dashing > 0:
        player.dashing -= 1
        # Add dash echo
        if player.dashing % 2 == 0:
            state.dash_echoes.append(DashEcho(
                pos=player.pos.copy(),
                lifetime=DASH_ECHO_LIFETIME
            ))
        # Apply dash velocity
        player.pos = player.pos + player.dash_dir * DASH_SPEED * dt * 60
        player.invulnerable = 5
    else:
        # Normal movement with momentum
        accel = Vec2(0, 0)

        if 'w' in state.keys_held:
            accel.y -= PLAYER_ACCEL
        if 's' in state.keys_held:
            accel.y += PLAYER_ACCEL
        if 'a' in state.keys_held:
            accel.x -= PLAYER_ACCEL
        if 'd' in state.keys_held:
            accel.x += PLAYER_ACCEL

        # Track last movement direction based on input
        if accel.length() > 0:
            player.last_move_dir = accel.normalized()

        # Apply acceleration
        player.vel = player.vel + accel * dt

        # Apply friction
        player.vel = player.vel * PLAYER_FRICTION

        # Clamp velocity
        speed = player.vel.length()
        if speed > PLAYER_MAX_SPEED:
            player.vel = player.vel.normalized() * PLAYER_MAX_SPEED

        # Apply velocity
        player.pos = player.pos + player.vel * dt * 60

    # Update cooldowns
    if player.dash_cooldown > 0:
        player.dash_cooldown -= 1
    if player.invulnerable > 0:
        player.invulnerable -= 1

    # Clamp position to bounds
    player.pos.x = max(1, min(state.width - 2, player.pos.x))
    player.pos.y = max(1, min(state.height - 2, player.pos.y))


def trigger_dash(state: GameState):
    """Initiate a dash if possible."""
    player = state.player

    if player.dash_cooldown > 0 or player.dashing > 0:
        return

    # Determine dash direction: current input > current velocity > last move direction
    dx, dy = 0, 0
    if 'w' in state.keys_held: dy -= 1
    if 's' in state.keys_held: dy += 1
    if 'a' in state.keys_held: dx -= 1
    if 'd' in state.keys_held: dx += 1

    if dx != 0 or dy != 0:
        # Use current input direction
        player.dash_dir = Vec2(dx, dy).normalized()
    elif player.vel.length() > 0.1:
        # Use current velocity
        player.dash_dir = player.vel.normalized()
    else:
        # Use last movement direction
        player.dash_dir = player.last_move_dir

    player.dashing = DASH_DURATION
    player.dash_cooldown = DASH_COOLDOWN

    # Add DASH verb
    add_verb(state, "DASH")


def trigger_slash(state: GameState, direction: str):
    """Create a slash arc in the given direction."""
    player = state.player

    dir_map = {
        'up': Vec2(0, -1),
        'down': Vec2(0, 1),
        'left': Vec2(-1, 0),
        'right': Vec2(1, 0)
    }

    dir_vec = dir_map.get(direction, Vec2(1, 0))

    # Direction-specific slash characters for more dramatic visuals
    slash_patterns = {
        'up':    ['\\', '|', '/', '─', '\\', '|', '/'],
        'down':  ['/', '|', '\\', '─', '/', '|', '\\'],
        'left':  ['/', '─', '\\', '│', '/', '─', '\\'],
        'right': ['\\', '─', '/', '│', '\\', '─', '/'],
    }

    # Heavy/dramatic characters for the main arc
    heavy_chars = ['█', '▓', '▒', '░', '╱', '╲', '│', '─', '┼', '╳']

    chars = []
    radius = 5.0  # Larger radius for visibility
    angle_offset = math.atan2(dir_vec.y, dir_vec.x)

    # Create multiple layers of the arc for thickness
    for layer in range(3):  # 3 layers: inner, middle, outer
        layer_radius = radius + layer * 0.8
        num_segments = 9 + layer * 2  # More segments on outer layers

        for i in range(num_segments):
            # Spread across a 120-degree arc (±60 degrees from direction)
            t = (i / (num_segments - 1)) - 0.5  # -0.5 to 0.5
            angle = angle_offset + (t * 2.0)  # ±1 radian spread

            x = int(player.pos.x + math.cos(angle) * layer_radius)
            y = int(player.pos.y + math.sin(angle) * layer_radius * 0.5)

            # Choose character based on angle and layer
            if layer == 0:
                char = heavy_chars[i % len(heavy_chars)]
            elif layer == 1:
                pattern = slash_patterns.get(direction, slash_patterns['right'])
                char = pattern[i % len(pattern)]
            else:
                char = random.choice(['*', '+', '×', '·', '•'])

            chars.append((x, y, char))

    # Add slash trail particles for extra juice
    for _ in range(8):
        angle = angle_offset + random.uniform(-0.8, 0.8)
        dist = random.uniform(2, radius + 2)
        px = player.pos.x + math.cos(angle) * dist
        py = player.pos.y + math.sin(angle) * dist * 0.5

        state.particles.append(Particle(
            pos=Vec2(px, py),
            vel=Vec2(math.cos(angle) * 0.3, math.sin(angle) * 0.2),
            char=random.choice(['*', '·', '✦', '+']),
            color=random.choice([NEON_YELLOW, NEON_CYAN, 255]),
            lifetime=random.randint(8, 15),
            max_lifetime=15,
            gravity=0
        ))

    state.slash_arcs.append(SlashArc(
        center=player.pos.copy(),
        direction=dir_vec,
        radius=radius,
        lifetime=12,  # Longer lifetime for visibility
        chars=chars
    ))

    # Screen shake
    state.screen_shake = SCREEN_SHAKE_DURATION

    # Check for enemy hits
    check_slash_hits(state, player.pos, dir_vec, radius)


def check_slash_hits(state: GameState, center: Vec2, direction: Vec2, radius: float):
    """Check if slash hits any enemies."""
    hit_any = False

    for enemy in state.enemies[:]:
        dx = enemy.pos.x - center.x
        dy = enemy.pos.y - center.y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < radius + 1:
            # Check if enemy is in the slash direction (within 90 degrees)
            if dist > 0:
                dot = (dx * direction.x + dy * direction.y) / dist
                if dot > -0.3:  # Generous hit detection
                    enemy.health -= 1
                    enemy.hit_flash = 3
                    hit_any = True

                    if enemy.health <= 0:
                        spawn_death_particles(state, enemy.pos, enemy.color)
                        state.enemies.remove(enemy)
                        add_verb(state, random.choice(["SLICE", "REND", "SEVER"]))

    if hit_any:
        state.screen_shake = max(state.screen_shake, SCREEN_SHAKE_DURATION)


def add_verb(state: GameState, verb: str):
    """Add a verb to the syntax chain."""
    if len(state.verb_chain) < 3:
        state.verb_chain.append(verb)


def execute_super_move(state: GameState):
    """Execute the syntax chain super move."""
    if len(state.verb_chain) >= 3:
        state.super_move_active = 45  # frames
        state.wave_radius = 0
        state.verb_chain.clear()

        # Massive screen shake
        state.screen_shake = 10


def spawn_death_particles(state: GameState, pos: Vec2, color: int):
    """Spawn explosion particles when enemy dies."""
    chars = ['.', '*', '!', '+', 'x', "'", '`']
    colors = [color, NEON_YELLOW, 255, GRAY_LIGHT]

    for _ in range(15):
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(0.3, 1.2)

        state.particles.append(Particle(
            pos=pos.copy(),
            vel=Vec2(math.cos(angle) * speed, math.sin(angle) * speed - 0.5),
            char=random.choice(chars),
            color=random.choice(colors),
            lifetime=random.randint(15, PARTICLE_LIFETIME),
            max_lifetime=PARTICLE_LIFETIME
        ))


def update_particles(state: GameState):
    """Update all particles."""
    state.particles = [p for p in state.particles if p.update()]


def update_dash_echoes(state: GameState):
    """Update dash echo trails."""
    for echo in state.dash_echoes[:]:
        echo.lifetime -= 1
        if echo.lifetime <= 0:
            state.dash_echoes.remove(echo)


def update_slash_arcs(state: GameState):
    """Update slash arc animations."""
    for arc in state.slash_arcs[:]:
        arc.lifetime -= 1
        if arc.lifetime <= 0:
            state.slash_arcs.remove(arc)


def update_enemies(state: GameState, dt: float):
    """Update enemy behavior."""
    for enemy in state.enemies:
        if enemy.hit_flash > 0:
            enemy.hit_flash -= 1

        # Simple chase behavior
        dx = state.player.pos.x - enemy.pos.x
        dy = state.player.pos.y - enemy.pos.y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist > 0 and dist < 30:
            enemy.pos.x += (dx / dist) * 0.3 * dt * 60
            enemy.pos.y += (dy / dist) * 0.15 * dt * 60


def update_super_move(state: GameState):
    """Update the super move wave effect."""
    if state.super_move_active > 0:
        state.super_move_active -= 1
        state.wave_radius += 3

        # Kill enemies caught in the wave
        for enemy in state.enemies[:]:
            dx = enemy.pos.x - state.player.pos.x
            dy = enemy.pos.y - state.player.pos.y
            dist = math.sqrt(dx * dx + dy * dy)

            if abs(dist - state.wave_radius) < 3:
                spawn_death_particles(state, enemy.pos, NEON_MAGENTA)
                state.enemies.remove(enemy)


def update_starfield(state: GameState):
    """Update parallax starfield."""
    for star in state.stars:
        star.x -= star.speed
        if star.x < 0:
            star.x = state.width
            star.y = random.uniform(0, state.height)


def update_screen_shake(state: GameState):
    """Update screen shake effect."""
    if state.screen_shake > 0:
        state.screen_shake -= 1
        state.shake_offset = Vec2(
            random.randint(-SCREEN_SHAKE_INTENSITY, SCREEN_SHAKE_INTENSITY),
            random.randint(-SCREEN_SHAKE_INTENSITY // 2, SCREEN_SHAKE_INTENSITY // 2)
        )
    else:
        state.shake_offset = Vec2(0, 0)


# =============================================================================
# RENDERING
# =============================================================================

def render_frame(state: GameState) -> str:
    """Render the complete frame."""
    state.buffer.clear()
    state.braille.clear()

    # Get shake offset for this frame
    shake_x = int(state.shake_offset.x)
    shake_y = int(state.shake_offset.y)

    # Render starfield (background layer) - with shake
    render_starfield(state, shake_x, shake_y)

    # Render super move wave - with shake
    if state.super_move_active > 0:
        render_super_wave(state, shake_x, shake_y)

    # Render dash echoes - with shake
    render_dash_echoes(state, shake_x, shake_y)

    # Render particles (sub-pixel and regular) - with shake
    render_particles(state, shake_x, shake_y)

    # Render enemies - with shake
    render_enemies(state, shake_x, shake_y)

    # Render slash arcs - with shake
    render_slash_arcs(state, shake_x, shake_y)

    # Render player - with shake
    render_player(state, shake_x, shake_y)

    # Render braille overlay (sub-pixel particles) - with shake
    render_braille_overlay(state, shake_x, shake_y)

    # Render UI - NO shake (stays stable)
    render_ui(state)

    # Compile and return frame
    return state.buffer.render()


def render_starfield(state: GameState, shake_x: int = 0, shake_y: int = 0):
    """Render the parallax starfield."""
    for star in state.stars:
        x, y = int(star.x) + shake_x, int(star.y) + shake_y
        if 0 <= x < state.width and 0 <= y < state.height:
            state.buffer.put(x, y, star.char, star.color)


def render_super_wave(state: GameState, shake_x: int = 0, shake_y: int = 0):
    """Render the expanding super move wave."""
    cx, cy = int(state.player.pos.x), int(state.player.pos.y)
    wave_chars = ['#', '=', '-', '~', '.']
    colors = [NEON_MAGENTA, NEON_CYAN, NEON_YELLOW, 255, GRAY_LIGHT]

    for angle in range(0, 360, 5):
        rad = math.radians(angle)
        for i, (char, color) in enumerate(zip(wave_chars, colors)):
            r = state.wave_radius - i * 2
            if r > 0:
                x = int(cx + math.cos(rad) * r) + shake_x
                y = int(cy + math.sin(rad) * r * 0.5) + shake_y
                if 0 <= x < state.width and 0 <= y < state.height:
                    state.buffer.put(x, y, char, color)


def render_dash_echoes(state: GameState, shake_x: int = 0, shake_y: int = 0):
    """Render fading dash echoes."""
    echo_colors = [255, GRAY_LIGHT, GRAY_MED, GRAY_DARK, GRAY_DARKER]

    for echo in state.dash_echoes:
        color_idx = DASH_ECHO_LIFETIME - echo.lifetime
        if color_idx < len(echo_colors):
            x, y = int(echo.pos.x) + shake_x, int(echo.pos.y) + shake_y
            if 0 <= x < state.width and 0 <= y < state.height:
                state.buffer.put(x, y, state.player.char, echo_colors[color_idx])


def render_particles(state: GameState, shake_x: int = 0, shake_y: int = 0):
    """Render particles with both regular chars and sub-pixel dots."""
    for particle in state.particles:
        # Fade color based on lifetime
        life_ratio = particle.lifetime / particle.max_lifetime

        if life_ratio > 0.5:
            # Regular character particles
            x, y = int(particle.pos.x) + shake_x, int(particle.pos.y) + shake_y
            if 0 <= x < state.width and 0 <= y < state.height:
                state.buffer.put(x, y, particle.char, particle.color)
        else:
            # Sub-pixel braille dots for fading particles
            px = int(particle.pos.x * 2) + shake_x * 2
            py = int(particle.pos.y * 4) + shake_y * 4
            fade_color = GRAY_DARK if life_ratio > 0.25 else GRAY_DARKER
            state.braille.set_pixel(px, py, fade_color)


def render_enemies(state: GameState, shake_x: int = 0, shake_y: int = 0):
    """Render enemies."""
    for enemy in state.enemies:
        x, y = int(enemy.pos.x) + shake_x, int(enemy.pos.y) + shake_y
        if 0 <= x < state.width and 0 <= y < state.height:
            color = 255 if enemy.hit_flash > 0 else enemy.color
            state.buffer.put(x, y, enemy.char, color)


def render_slash_arcs(state: GameState, shake_x: int = 0, shake_y: int = 0):
    """Render slash attack arcs with dramatic color fade."""
    # Extended color palette for 12-frame animation
    arc_colors = [
        255,         # Bright white (frame 12-11)
        NEON_YELLOW, # Yellow (frame 10-9)
        NEON_YELLOW,
        NEON_CYAN,   # Cyan (frame 8-7)
        NEON_CYAN,
        NEON_MAGENTA,# Magenta (frame 6-5)
        NEON_MAGENTA,
        GRAY_LIGHT,  # Fade to gray (frame 4-3)
        GRAY_MED,
        GRAY_DARK,   # Dark gray (frame 2-1)
        GRAY_DARK,
        GRAY_DARKER,
    ]

    for arc in state.slash_arcs:
        color_idx = 12 - arc.lifetime
        if 0 <= color_idx < len(arc_colors):
            color = arc_colors[color_idx]
            for x, y, char in arc.chars:
                x, y = x + shake_x, y + shake_y
                if 0 <= x < state.width and 0 <= y < state.height:
                    state.buffer.put(x, y, char, color)


def render_player(state: GameState, shake_x: int = 0, shake_y: int = 0):
    """Render the player character."""
    x, y = int(state.player.pos.x) + shake_x, int(state.player.pos.y) + shake_y

    # Flicker effect during invulnerability/dash
    if state.player.invulnerable > 0 and state.player.invulnerable % 2 == 0:
        return

    if 0 <= x < state.width and 0 <= y < state.height:
        color = NEON_MAGENTA if state.player.dashing > 0 else state.player.color
        state.buffer.put(x, y, state.player.char, color)


def render_braille_overlay(state: GameState, shake_x: int = 0, shake_y: int = 0):
    """Overlay braille sub-pixel canvas onto buffer."""
    for cy in range(state.braille.char_height):
        for cx in range(state.braille.char_width):
            char, color = state.braille.get_char(cx, cy)
            if char:
                rx, ry = cx + shake_x, cy + shake_y
                # Only overlay if in bounds and current cell is empty or a star
                if 0 <= rx < state.width and 0 <= ry < state.height:
                    current = state.buffer.buffer[ry][rx]
                    if current[0] in ('', '.', "'", '`', '*', '+'):
                        state.buffer.put(rx, ry, char, color)


def render_ui(state: GameState):
    """Render the UI elements."""
    ui_y = state.height

    # Border line
    border = "=" * state.width
    state.buffer.put_string(0, ui_y, border, GRAY_DARK)

    # Title
    title = " SIGNAL_VOID "
    state.buffer.put_string(2, ui_y, title, NEON_MAGENTA)

    # Syntax Chain
    chain_x = state.width // 2 - 15
    state.buffer.put_string(chain_x, ui_y + 1, "SYNTAX CHAIN: ", GRAY_MED)

    verb_x = chain_x + 14
    for i, verb in enumerate(state.verb_chain):
        text = f"[{verb}]"
        colors = [NEON_CYAN, NEON_YELLOW, NEON_MAGENTA]
        state.buffer.put_string(verb_x, ui_y + 1, text, colors[i % len(colors)])
        verb_x += len(text) + 1

    # Empty slots
    for i in range(len(state.verb_chain), 3):
        state.buffer.put_string(verb_x, ui_y + 1, "[    ]", GRAY_DARK)
        verb_x += 7

    # Ready indicator
    if len(state.verb_chain) >= 3:
        state.buffer.put_string(verb_x + 2, ui_y + 1, ">>> ENTER TO EXECUTE <<<", NEON_GREEN)

    # Controls hint
    controls = "WASD:Move  IJKL:Slash  Space:Dash  H:Execute  Q:Quit"
    state.buffer.put_string(2, ui_y + 2, controls, GRAY_MED)

    # Enemy counter
    enemy_text = f"ENEMIES: {len(state.enemies)}"
    state.buffer.put_string(state.width - len(enemy_text) - 2, ui_y + 2, enemy_text, NEON_RED)


# =============================================================================
# MAIN GAME LOOP
# =============================================================================

def main():
    term = Terminal()

    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        state = GameState(term)

        last_time = time.perf_counter()
        accumulator = 0.0
        running = True

        # Initial render
        print(term.home + term.clear)

        while running:
            current_time = time.perf_counter()
            delta_time = current_time - last_time
            last_time = current_time

            # Accumulate time for fixed timestep
            accumulator += delta_time

            # Process input (non-blocking)
            key = term.inkey(timeout=0)

            while key:
                key_str = key.lower() if key.is_sequence is False else ''

                if key_str == 'q' or key.name == 'KEY_ESCAPE':
                    running = False
                elif key_str in 'wasd':
                    # Refresh hold timer on key press
                    state.keys_held[key_str] = state.key_hold_duration
                elif key_str == ' ':
                    trigger_dash(state)
                # IJKL for slash attacks (vim-style)
                elif key_str == 'i':
                    trigger_slash(state, 'up')
                elif key_str == 'k':
                    trigger_slash(state, 'down')
                elif key_str == 'j':
                    trigger_slash(state, 'left')
                elif key_str == 'l':
                    trigger_slash(state, 'right')
                # H to execute super move
                elif key_str == 'h':
                    execute_super_move(state)

                key = term.inkey(timeout=0)

            # Fixed timestep updates
            while accumulator >= FRAME_TIME:
                # Game updates
                update_player(state, FRAME_TIME)
                update_enemies(state, FRAME_TIME)
                update_particles(state)
                update_dash_echoes(state)
                update_slash_arcs(state)
                update_super_move(state)
                update_starfield(state)
                update_screen_shake(state)

                # Spawn more enemies if needed
                if len(state.enemies) < 3:
                    state._spawn_enemies(3)

                accumulator -= FRAME_TIME

            # Render
            frame = render_frame(state)
            print(frame, end='', flush=True)

            # Frame timing - sleep for remaining time
            elapsed = time.perf_counter() - current_time
            sleep_time = FRAME_TIME - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time * 0.9)  # Slight under-sleep to prevent drift

        # Cleanup
        print(term.normal)


if __name__ == "__main__":
    main()
