"""
Rendering Engine
=================
Double-buffered terminal renderer with visual effects.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import random

try:
    from blessed import Terminal
except ImportError:
    raise ImportError("'blessed' library required. Install with: pip install blessed")


# ANSI 256 color constants
NEON_CYAN = 51
NEON_MAGENTA = 201
NEON_YELLOW = 226
NEON_GREEN = 46
NEON_RED = 196
NEON_ORANGE = 208
NEON_PINK = 199

GRAY_LIGHT = 252
GRAY_MED = 245
GRAY_DARK = 238
GRAY_DARKER = 235

WHITE = 255
BLACK = 0


@dataclass
class Cell:
    """A single cell in the render buffer."""
    char: str = ' '
    fg_color: int = 7
    bg_color: int = -1  # -1 = transparent/default

    def matches(self, other: 'Cell') -> bool:
        """Check if two cells are visually identical."""
        return (
            self.char == other.char and
            self.fg_color == other.fg_color and
            self.bg_color == other.bg_color
        )

    def reset(self):
        """Reset to empty state."""
        self.char = ' '
        self.fg_color = 7
        self.bg_color = -1


class DoubleBuffer:
    """
    Double-buffered terminal renderer.

    Writes to a back buffer, then swaps to front buffer,
    only updating cells that changed. No screen clears needed.
    """

    def __init__(self, term: Terminal):
        self.term = term
        self.width = term.width
        self.height = term.height
        self.front: List[List[Cell]] = []
        self.back: List[List[Cell]] = []
        self._init_buffers()
        self._normal = term.normal  # Cache reset sequence

    def _init_buffers(self):
        """Initialize both buffers with empty cells."""
        self.front = [
            [Cell() for _ in range(self.width)]
            for _ in range(self.height)
        ]
        self.back = [
            [Cell() for _ in range(self.width)]
            for _ in range(self.height)
        ]

    def resize(self, width: int, height: int):
        """Handle terminal resize."""
        self.width = width
        self.height = height
        self._init_buffers()

    def clear_back(self):
        """Clear the back buffer by resetting cells in-place."""
        for row in self.back:
            for cell in row:
                cell.reset()

    def put(self, x: int, y: int, char: str, fg_color: int = 7, bg_color: int = -1):
        """Put a character in the back buffer at exact position."""
        if 0 <= x < self.width and 0 <= y < self.height:
            cell = self.back[y][x]
            cell.char = char
            cell.fg_color = fg_color
            cell.bg_color = bg_color

    def put_string(self, x: int, y: int, text: str, fg_color: int = 7, bg_color: int = -1):
        """Put a string in the back buffer."""
        for i, char in enumerate(text):
            self.put(x + i, y, char, fg_color, bg_color)

    def present(self) -> str:
        """
        Swap buffers and generate output for changed cells only.

        Uses dirty-cell comparison between front and back buffers.
        All positioning (including screen shake) is handled upstream
        when writing to the buffer. Present does 1:1 mapping.
        """
        output_parts = []
        normal = self._normal

        for y in range(self.height):
            for x in range(self.width):
                back_cell = self.back[y][x]
                front_cell = self.front[y][x]

                if not back_cell.matches(front_cell):
                    # Position cursor
                    output_parts.append(self.term.move_xy(x, y))
                    # Reset colors to prevent bleed
                    output_parts.append(normal)
                    # Apply colors
                    if back_cell.bg_color >= 0:
                        output_parts.append(self.term.on_color(back_cell.bg_color))
                    output_parts.append(self.term.color(back_cell.fg_color))
                    output_parts.append(back_cell.char if back_cell.char else ' ')

        # Swap: back becomes the new front, old front becomes next back
        self.front, self.back = self.back, self.front

        return ''.join(output_parts)


class BrailleCanvas:
    """
    Sub-pixel rendering using Unicode Braille patterns.

    Each character cell maps to a 2x4 pixel grid, giving 8x
    the resolution of plain characters for particle effects.
    """

    # Braille dot bit positions: (column, row, bit_value)
    DOTS = [
        (0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (0, 3, 0x40),
        (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (1, 3, 0x80),
    ]
    BASE = 0x2800

    def __init__(self, char_width: int, char_height: int):
        self.char_width = char_width
        self.char_height = char_height
        self.pixel_width = char_width * 2
        self.pixel_height = char_height * 4
        self.canvas: List[List[int]] = []
        self.colors: List[List[int]] = []
        self.clear()

    def clear(self):
        """Clear the canvas."""
        self.canvas = [
            [0 for _ in range(self.char_width)]
            for _ in range(self.char_height)
        ]
        self.colors = [
            [WHITE for _ in range(self.char_width)]
            for _ in range(self.char_height)
        ]

    def set_pixel(self, px: int, py: int, color: int = WHITE):
        """Set a sub-pixel dot at pixel coordinates."""
        if 0 <= px < self.pixel_width and 0 <= py < self.pixel_height:
            char_x = px // 2
            char_y = py // 4
            dot_x = px % 2
            dot_y = py % 4

            for dx, dy, bit in self.DOTS:
                if dx == dot_x and dy == dot_y:
                    self.canvas[char_y][char_x] |= bit
                    self.colors[char_y][char_x] = color
                    break

    def get_char(self, cx: int, cy: int) -> Tuple[str, int]:
        """Get the braille character and color at a cell position."""
        if 0 <= cx < self.char_width and 0 <= cy < self.char_height:
            pattern = self.canvas[cy][cx]
            if pattern > 0:
                return chr(self.BASE + pattern), self.colors[cy][cx]
        return '', WHITE

    def blit_to_buffer(self, buffer: DoubleBuffer, offset_x: int = 0, offset_y: int = 0):
        """Render braille canvas onto the buffer. Only overlays empty cells."""
        for cy in range(self.char_height):
            for cx in range(self.char_width):
                char, color = self.get_char(cx, cy)
                if char:
                    bx = cx + offset_x
                    by = cy + offset_y
                    if 0 <= bx < buffer.width and 0 <= by < buffer.height:
                        current = buffer.back[by][bx]
                        if current.char == ' ':
                            buffer.put(bx, by, char, color)


@dataclass
class GameRenderer:
    """
    High-level game renderer with screen shake and hit-stop.

    Screen shake works by offsetting game-area coordinates when
    writing to the buffer. UI elements bypass the offset.
    """
    term: Terminal
    buffer: DoubleBuffer = field(init=False)
    braille: BrailleCanvas = field(init=False)

    # Screen shake state
    shake_x: int = 0
    shake_y: int = 0
    shake_frames: int = 0
    shake_intensity: int = 2

    # Hit-stop state
    hitstop_frames: int = 0

    # FPS display
    show_fps: bool = False
    current_fps: float = 60.0

    def __post_init__(self):
        self.buffer = DoubleBuffer(self.term)
        self.braille = BrailleCanvas(self.term.width, self.term.height - 3)

    @property
    def width(self) -> int:
        return self.buffer.width

    @property
    def height(self) -> int:
        return self.buffer.height

    @property
    def game_height(self) -> int:
        """Height of the playable area (excluding UI rows)."""
        return self.buffer.height - 3

    def is_frozen(self) -> bool:
        """Check if the game is in hit-stop freeze."""
        return self.hitstop_frames > 0

    def trigger_hitstop(self, frames: int = 3):
        """Freeze gameplay for N frames on heavy impact."""
        self.hitstop_frames = max(self.hitstop_frames, frames)

    def trigger_shake(self, intensity: int = 2, frames: int = 3):
        """Trigger screen shake for N frames."""
        self.shake_intensity = intensity
        self.shake_frames = max(self.shake_frames, frames)

    def update_effects(self):
        """Tick screen shake and hit-stop timers."""
        if self.shake_frames > 0:
            self.shake_x = random.randint(-self.shake_intensity, self.shake_intensity)
            self.shake_y = random.randint(-max(1, self.shake_intensity // 2),
                                          max(1, self.shake_intensity // 2))
            self.shake_frames -= 1
        else:
            self.shake_x = 0
            self.shake_y = 0

        if self.hitstop_frames > 0:
            self.hitstop_frames -= 1

    def begin_frame(self):
        """Begin rendering a new frame."""
        self.buffer.clear_back()
        self.braille.clear()

    def end_frame(self) -> str:
        """Finalize frame: blit braille overlay and present."""
        # Blit braille canvas (no extra offset - shake was applied at pixel-set time)
        self.braille.blit_to_buffer(self.buffer)

        # Advance effect timers
        self.update_effects()

        # Output only changed cells
        return self.buffer.present()

    def put(self, x: int, y: int, char: str, fg_color: int = 7,
            with_shake: bool = True):
        """
        Put a character in the buffer.

        Game-area elements use with_shake=True so they jitter during
        screen shake. UI elements use with_shake=False.
        """
        if with_shake and y < self.game_height:
            x += self.shake_x
            y += self.shake_y
        self.buffer.put(x, y, char, fg_color)

    def put_string(self, x: int, y: int, text: str, fg_color: int = 7,
                   with_shake: bool = True):
        """Put a string, optionally with shake offset."""
        if with_shake and y < self.game_height:
            x += self.shake_x
            y += self.shake_y
        self.buffer.put_string(x, y, text, fg_color)

    def put_braille_pixel(self, px: float, py: float, color: int = WHITE):
        """
        Set a sub-pixel braille dot at world coordinates.

        Shake is applied here so braille particles jitter with everything else.
        """
        bx = int(px * 2) + self.shake_x * 2
        by = int(py * 4) + self.shake_y * 4
        self.braille.set_pixel(bx, by, color)

    def resize(self, width: int, height: int):
        """Handle terminal resize."""
        self.buffer.resize(width, height)
        self.braille = BrailleCanvas(width, height - 3)

    def draw_box(self, x: int, y: int, w: int, h: int, color: int = GRAY_DARK,
                 char: str = '#', with_shake: bool = True):
        """Draw a rectangular border."""
        for i in range(w):
            self.put(x + i, y, char, color, with_shake)
            self.put(x + i, y + h - 1, char, color, with_shake)
        for j in range(1, h - 1):
            self.put(x, y + j, char, color, with_shake)
            self.put(x + w - 1, y + j, char, color, with_shake)
