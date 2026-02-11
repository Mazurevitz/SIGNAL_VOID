#!/usr/bin/env python3
"""
SIGNAL_VOID - Terminal Hack-and-Slash
======================================
A neon-drenched, kinetic combat experience in your terminal.

Controls:
    WASD    - Move (momentum-based)
    IJKL    - Attack (I=up, K=down, J=left, L=right)
    SPACE   - Dash
    H       - Execute Syntax Chain (when buffer is full)
    F       - Toggle FPS display
    Q/ESC   - Quit
"""

import sys
import time
import math
import random

try:
    from blessed import Terminal
except ImportError:
    print("ERROR: 'blessed' library required. Install with: pip install blessed")
    sys.exit(1)

from .ecs import World
from .engine import (
    GameRenderer, GRAY_DARK, GRAY_MED, GRAY_DARKER,
    NEON_CYAN, NEON_MAGENTA, NEON_YELLOW, NEON_GREEN, NEON_RED, WHITE
)
from .player import (
    create_player, InputHandler, player_input_system,
    get_player_entity, get_player_position
)
from .systems import (
    movement_system,
    boundary_system,
    ghost_trail_system,
    dash_system,
    render_system,
    lifetime_system,
    gravity_system,
    particle_render_system,
    hit_flash_system,
    animation_system,
    render_starfield,
    generate_starfield,
    spawn_slash_arc,
    ai_system,
    combat_system,
    invulnerability_system,
    death_system,
)
from .particles import spawn_explosion
from .enemies import create_buffer_leak, create_firewall, create_overclocker
from .syntax_chain import add_verb, execute_syntax_chain, VERB_EFFECTS
from .rooms import RoomState, spawn_room, render_compile_transition
from .spawner import reset_introduced, get_intro_text, is_boss_depth
from .components import (
    Position, Velocity, Health, SyntaxBuffer, DashState,
    PlayerTag, EnemyTag, AttackState, PlayerControlled,
    Invulnerable, Renderable, PlayerStats, WeaponInventory
)
from .micro_upgrades import select_upgrades, apply_upgrade, render_upgrade_select
from .weapons import (
    execute_weapon_attack, weapon_cooldown_system, swap_weapon,
    get_active_weapon, get_weapon_data, create_weapon, WEAPONS,
    select_weapon_offer, replace_weapon, render_weapon_select
)
from .projectiles import projectile_system
from .enemy_projectiles import enemy_projectile_system, render_sniper_beams
from .weapon_mods import (
    echo_attack_system, ground_hazard_system,
    async_mod_system, grep_homing_system,
    select_mod_offer, attach_mod, render_mod_select
)
from .evolution import (
    check_all_evolutions, evolve_weapon, render_evolution_screen,
    shockwave_system
)
from .wave_spawner import (
    create_room_waves, update_wave_system, telegraph_system,
    render_wave_announcement
)


# =============================================================================
# CONSTANTS
# =============================================================================

TARGET_FPS = 60
FRAME_TIME = 1.0 / TARGET_FPS
MIN_WIDTH = 80
MIN_HEIGHT = 24

# Game phases
PHASE_TITLE = 'title'
PHASE_PLAYING = 'playing'
PHASE_GAME_OVER = 'game_over'
PHASE_UPGRADE_SELECT = 'upgrade_select'
PHASE_WEAPON_SELECT = 'weapon_select'
PHASE_MOD_SELECT = 'mod_select'
PHASE_EVOLUTION = 'evolution'

# Title screen ASCII art
TITLE_ART = [
    r"  ___ ___ ___ _  _   _   _       __   _____  ___ ___  ",
    r" / __|_ _/ __| \| | /_\ | |      \ \ / / _ \|_ _|   \ ",
    r" \__ \| | (_ | .` |/ _ \| |__     \ V / (_) || || |) |",
    r" |___/___\___|_|\_/_/ \_\____|     \_/ \___/|___|___/ ",
]


# =============================================================================
# UI RENDERING
# =============================================================================

def render_ui(world: World, renderer: GameRenderer, room_depth: int,
              enemies_killed: int = 0):
    """Render the HUD in the bottom 3 rows."""
    ui_y = renderer.game_height
    width = renderer.width

    # Separator line with title
    sep = '=' * width
    renderer.buffer.put_string(0, ui_y, sep, GRAY_DARK)
    renderer.buffer.put_string(2, ui_y, ' SIGNAL_VOID ', NEON_MAGENTA)

    # Kernel depth + enemy count
    enemy_count = sum(1 for _ in world.query(EnemyTag))
    status_text = f' DEPTH:{room_depth}  ENEMIES:{enemy_count} '
    renderer.buffer.put_string(width - len(status_text) - 1, ui_y, status_text, NEON_YELLOW)

    # Get player components
    player_id = get_player_entity(world)
    if player_id is None:
        return

    health = world.get_component(player_id, Health)
    syntax = world.get_component(player_id, SyntaxBuffer)
    dash = world.get_component(player_id, DashState)

    # Row 1: Health bar + Syntax buffer + Dash indicator
    row1_y = ui_y + 1

    # Health bar (System Stability)
    if health:
        bar_width = 20
        filled = max(0, int((health.current / health.maximum) * bar_width))
        bar = '|' * filled + '.' * (bar_width - filled)
        color = NEON_CYAN if health.current > health.maximum * 0.3 else NEON_RED
        renderer.buffer.put_string(2, row1_y, 'STABILITY:', GRAY_MED)
        renderer.buffer.put_string(13, row1_y, f'[{bar}]', color)

    # Syntax Chain buffer (centered)
    if syntax:
        buf_start = max(36, width // 2 - 18)
        renderer.buffer.put_string(buf_start, row1_y, 'BUFFER:', GRAY_MED)

        verb_x = buf_start + 8
        for i in range(syntax.max_verbs):
            if i < len(syntax.verbs):
                verb = syntax.verbs[i]
                text = f'[{verb:^9}]'
                color = VERB_EFFECTS.get(verb, {}).get('color', NEON_CYAN)
                renderer.buffer.put_string(verb_x, row1_y, text, color)
            else:
                renderer.buffer.put_string(verb_x, row1_y, '[         ]', GRAY_DARK)
            verb_x += 12

        if len(syntax.verbs) >= syntax.max_verbs:
            renderer.buffer.put_string(verb_x + 1, row1_y, '>>H<<', 46)

    # Dash cooldown
    if dash:
        dash_x = width - 15
        if dash.cooldown_remaining > 0:
            cd_pct = dash.cooldown_remaining / dash.cooldown
            filled = int((1 - cd_pct) * 5)
            bar = '#' * filled + '.' * (5 - filled)
            renderer.buffer.put_string(dash_x, row1_y, f'DASH:[{bar}]', GRAY_MED)
        else:
            renderer.buffer.put_string(dash_x, row1_y, 'DASH:[#####]', NEON_CYAN)

    # Row 2: Weapon HUD + controls
    inv = world.get_component(player_id, WeaponInventory) if player_id is not None else None
    if inv and inv.weapons:
        wx = 2
        for i, weapon in enumerate(inv.weapons):
            wdata = WEAPONS.get(weapon.weapon_type, WEAPONS['slash'])
            is_active = (i == inv.active_index)
            sym = wdata['symbol']
            name = wdata['name']
            color = wdata['color'] if is_active else GRAY_DARK
            marker = '\u2190' if is_active else ' '
            text = f'[{sym}] {name}{marker}'
            renderer.buffer.put_string(wx, ui_y + 2, text, color)
            wx += len(text) + 2
        if len(inv.weapons) >= 2:
            renderer.buffer.put_string(wx, ui_y + 2, 'TAB:Swap', GRAY_DARKER)
            wx += 10
        renderer.buffer.put_string(wx, ui_y + 2, 'H:Execute  Q:Quit', GRAY_DARKER)
    else:
        controls = 'WASD:Move  IJKL:Attack  SPACE:Dash  H:Execute  Q:Quit'
        renderer.buffer.put_string(2, ui_y + 2, controls, GRAY_DARKER)

    # FPS counter (top-right, bypasses shake)
    if renderer.show_fps:
        fps_text = f'FPS:{renderer.current_fps:.0f}'
        renderer.buffer.put_string(width - len(fps_text) - 2, 0, fps_text, GRAY_MED)


def render_room_border(renderer: GameRenderer):
    """Render the room walls."""
    renderer.draw_box(0, 0, renderer.width, renderer.game_height, GRAY_DARK, '#')


def render_invulnerability_blink(world: World, renderer: GameRenderer):
    """Make player blink during i-frames by toggling visibility."""
    player_id = get_player_entity(world)
    if player_id is None:
        return

    invuln = world.get_component(player_id, Invulnerable)
    rend = world.get_component(player_id, Renderable)
    if invuln and rend:
        if invuln.frames_remaining > 0:
            # Blink every 4 frames
            rend.visible = (invuln.frames_remaining // 4) % 2 == 0
        else:
            rend.visible = True


def render_verb_pickup_flash(renderer: GameRenderer, verb: str, x: float, y: float, timer: int):
    """Render a floating verb pickup indicator."""
    if timer <= 0:
        return
    # Float upward
    draw_y = int(y) - (30 - timer) // 5
    text = f'+[{verb}]'
    alpha = min(timer, 10) / 10.0  # Fade
    verb_color = VERB_EFFECTS.get(verb, {}).get('color', NEON_GREEN)
    color = verb_color if alpha > 0.5 else GRAY_MED
    renderer.put_string(int(x) - len(text) // 2, draw_y, text, color, with_shake=False)


def render_intro_text(renderer: GameRenderer, text: str,
                      timer: int, duration: int):
    """Render intro text centered with yellow flash effect."""
    width = renderer.width
    y = 2

    # Fade phases: fade in (first 15 frames), solid, fade out (last 30 frames)
    elapsed = duration - timer
    if elapsed < 15:
        # Fade in
        alpha = elapsed / 15.0
        color = NEON_YELLOW if alpha > 0.5 else GRAY_MED
    elif timer < 30:
        # Fade out
        alpha = timer / 30.0
        color = NEON_YELLOW if alpha > 0.5 else GRAY_MED
    else:
        # Solid
        color = NEON_YELLOW

    cx = width // 2 - len(text) // 2
    renderer.put_string(cx, y, text, color, with_shake=False)

    # Decorative brackets
    bar = '=' * (len(text) + 4)
    bx = width // 2 - len(bar) // 2
    renderer.put_string(bx, y - 1, bar, GRAY_DARK, with_shake=False)
    renderer.put_string(bx, y + 1, bar, GRAY_DARK, with_shake=False)


def render_title_screen(renderer: GameRenderer, frame: int):
    """Render the title screen."""
    width = renderer.width
    height = renderer.game_height

    # Title art
    art_y = height // 2 - 5
    for i, line in enumerate(TITLE_ART):
        x = width // 2 - len(line) // 2
        color = NEON_MAGENTA if i % 2 == 0 else NEON_CYAN
        renderer.buffer.put_string(max(0, x), art_y + i, line, color)

    # Subtitle
    sub = 'TERMINAL HACK-AND-SLASH'
    sx = width // 2 - len(sub) // 2
    renderer.buffer.put_string(sx, art_y + len(TITLE_ART) + 1, sub, GRAY_MED)

    # Blinking prompt
    if (frame // 30) % 2 == 0:
        prompt = '[ PRESS ANY KEY TO START ]'
        px = width // 2 - len(prompt) // 2
        renderer.buffer.put_string(px, art_y + len(TITLE_ART) + 4, prompt, NEON_GREEN)

    # Level select
    level_hint = '[ 1-9 ] Start at depth'
    lx = width // 2 - len(level_hint) // 2
    renderer.buffer.put_string(lx, art_y + len(TITLE_ART) + 6, level_hint, GRAY_MED)

    # Controls
    controls = [
        'WASD - Move      IJKL - Attack',
        'SPACE - Dash     H - Execute Chain',
        'Q/ESC - Quit     F - Toggle FPS',
    ]
    cy = art_y + len(TITLE_ART) + 8
    for i, line in enumerate(controls):
        cx = width // 2 - len(line) // 2
        renderer.buffer.put_string(cx, cy + i, line, GRAY_DARK)

    # Decorative border
    renderer.draw_box(0, 0, width, height, GRAY_DARKER, '.', with_shake=False)


def render_game_over_screen(renderer: GameRenderer, depth: int,
                            enemies_killed: int, frame: int):
    """Render the game over screen."""
    width = renderer.width
    height = renderer.game_height

    # GAME OVER text
    game_over_art = [
        ' ___   _   __  __ ___    _____   _____ ___ ',
        '/ __| /_\\ |  \\/  | __|  / _ \\ \\ / / __| _ \\',
        '| (_ |/ _ \\| |\\/| | _|  | (_) \\ V /| _||   /',
        ' \\___/_/ \\_\\_|  |_|___|  \\___/ \\_/ |___|_|_\\',
    ]

    art_y = height // 2 - 6
    for i, line in enumerate(game_over_art):
        x = width // 2 - len(line) // 2
        renderer.buffer.put_string(max(0, x), art_y + i, line, NEON_RED)

    # Stats
    stats_y = art_y + len(game_over_art) + 2
    stat_lines = [
        f'DEPTH REACHED: {depth}',
        f'ENEMIES TERMINATED: {enemies_killed}',
    ]
    for i, line in enumerate(stat_lines):
        sx = width // 2 - len(line) // 2
        renderer.buffer.put_string(sx, stats_y + i, line, NEON_YELLOW)

    # Prompt
    prompt_y = stats_y + len(stat_lines) + 2
    if (frame // 30) % 2 == 0:
        restart = '[ R - RESTART ]    [ Q - QUIT ]'
        rx = width // 2 - len(restart) // 2
        renderer.buffer.put_string(rx, prompt_y, restart, NEON_CYAN)

    # Static noise background
    for _ in range(int(width * height * 0.02)):
        nx = random.randint(0, width - 1)
        ny = random.randint(0, height - 1)
        renderer.buffer.put(nx, ny, random.choice(['.', '*', '~']),
                           random.choice([GRAY_DARKER, GRAY_DARK, 236]))


# =============================================================================
# GAME STATE
# =============================================================================

class GameState:
    """Central game state container. Passed through all systems."""

    def __init__(self, term: Terminal):
        self.term = term
        self.renderer = GameRenderer(term)
        self.input_handler = InputHandler()

        self.running = True
        self.phase = PHASE_TITLE
        self.phase_frame = 0

        # Stats
        self.enemies_killed = 0
        self.kill_streak_count = 0
        self.kill_streak_timer = 0  # frames (30 = 0.5s)

        # These get set up on game start
        self.world = None
        self.room = None
        self.room_clear_delay = 0
        self.player_id = None
        self.starfield = None
        self.game_over_timer = 0

        # Verb pickup flash effects
        self.verb_flash_timer = 0
        self.verb_flash_text = ''
        self.verb_flash_x = 0.0
        self.verb_flash_y = 0.0

        # Intro text overlay
        self.intro_text = ''
        self.intro_timer = 0
        self.intro_text_active = False

        # Upgrade selection
        self.upgrade_choices = []
        self.upgrade_select_frame = 0

        # Debug depth cycling
        self._debug_depth_index = 0
        self._debug_depths = [1, 3, 5, 6, 8, 9, 10, 12, 15, 16, 20]
        self.show_entity_count = False

    def start_game(self, starting_depth: int = 1):
        """Initialize a new game session."""
        self.world = World()
        self.room = RoomState()
        self.room.depth = starting_depth
        self.room_clear_delay = 0
        self.enemies_killed = 0
        self.kill_streak_count = 0
        self.kill_streak_timer = 0
        self.game_over_timer = 0
        self.verb_flash_timer = 0
        self.intro_text_active = False
        self.intro_timer = 0
        self.intro_text = ''
        self.upgrade_choices = []
        self.upgrade_select_frame = 0
        self.weapon_offered = None
        self.weapon_select_frame = 0
        self.mod_offered = None
        self.mod_select_frame = 0
        self.evolution_weapon_idx = -1
        self.evolution_data = None
        self.evolution_frame = 0
        self._boss_reward_pending = False
        reset_introduced()

        # Background starfield
        self.starfield = generate_starfield(
            self.renderer.width, self.renderer.game_height
        )

        # Create player at center of room
        self.player_id = create_player(
            self.world,
            self.renderer.width / 2,
            self.renderer.game_height / 2
        )

        # Create wave-based spawning for this room
        self.room.waves = create_room_waves(self.room.depth)

        self.phase = PHASE_PLAYING
        self.phase_frame = 0

    def _advance_room(self):
        """Advance to next room after transition completes."""
        player_id = get_player_entity(self.world)
        if player_id is not None:
            # Center player
            pos = self.world.get_component(player_id, Position)
            if pos:
                pos.x = self.renderer.width / 2
                pos.y = self.renderer.game_height / 2
            vel = self.world.get_component(player_id, Velocity)
            if vel:
                vel.x = 0
                vel.y = 0

            # Heal on room clear (base 25% + heal_bonus from upgrades)
            health = self.world.get_component(player_id, Health)
            if health:
                stats = self.world.get_component(player_id, PlayerStats)
                heal_pct = 0.25 + (stats.heal_bonus if stats else 0.0)
                heal_amount = int(health.maximum * heal_pct)
                health.current = min(health.maximum, health.current + heal_amount)

            # Heal burst particles
            if pos:
                spawn_explosion(
                    self.world, pos.x, pos.y,
                    count=12,
                    colors=[NEON_GREEN, NEON_CYAN, WHITE],
                    chars=['+', '*', '.'],
                    speed_min=0.3, speed_max=0.8,
                    lifetime_min=15, lifetime_max=25,
                    gravity=-0.02  # Float upward
                )

        # Regenerate starfield
        self.starfield = generate_starfield(
            self.renderer.width, self.renderer.game_height
        )

        # Boss depth: skip past it (placeholder for future phases)
        if is_boss_depth(self.room.depth):
            self.room.depth += 1
            self.room.cleared = False
            self.room.enemies_spawned = 0

        # Create wave-based spawning for new room
        self.room.waves = create_room_waves(self.room.depth)

        # Check for intro text (new enemy type introduction) — non-blocking overlay
        intro = get_intro_text(self.room.depth)
        if intro:
            self.intro_text = intro
            self.intro_timer = 120  # 2 seconds at 60fps
            self.intro_text_active = True

    def _enter_upgrade_select(self):
        """Show upgrade selection screen after room clear."""
        player_id = get_player_entity(self.world)
        if player_id is None:
            self.room.start_transition()
            return

        stats = self.world.get_component(player_id, PlayerStats)
        if stats is None:
            self.room.start_transition()
            return

        choices = select_upgrades(stats)
        if not choices:
            self.room.start_transition()
            return

        self.upgrade_choices = choices
        self.upgrade_select_frame = 0
        self.phase = PHASE_UPGRADE_SELECT

    def _apply_upgrade_choice(self, index: int):
        """Apply the chosen upgrade and proceed to next screen."""
        if index < 0 or index >= len(self.upgrade_choices):
            return

        player_id = get_player_entity(self.world)
        if player_id is not None:
            apply_upgrade(self.world, player_id, self.upgrade_choices[index])

        self.upgrade_choices = []

        # Boss jackpot: if next room is boss, give weapon + mod + evolution
        self._boss_reward_pending = is_boss_depth(self.room.depth + 1)

        # Check if this is a weapon offer room (every 3 rooms or boss jackpot)
        if self._boss_reward_pending or self.room.depth % 3 == 0:
            self._enter_weapon_select()
        # Check if this is a mod offer room (offset: 2, 5, 8...)
        elif self.room.depth % 3 == 2:
            self._enter_mod_select()
        else:
            self._check_evolution()

    def _enter_weapon_select(self):
        """Show weapon selection screen if available."""
        player_id = get_player_entity(self.world)
        if player_id is None:
            self._post_weapon_select()
            return

        offered = select_weapon_offer(self.world, player_id)
        if offered is None:
            self._post_weapon_select()
            return

        self.weapon_offered = offered
        self.weapon_select_frame = 0
        self.phase = PHASE_WEAPON_SELECT

    def _apply_weapon_choice(self, slot: int):
        """Replace weapon in slot with offered weapon."""
        player_id = get_player_entity(self.world)
        if player_id is not None and self.weapon_offered:
            replace_weapon(self.world, player_id, slot, self.weapon_offered)
        self.weapon_offered = None
        self._post_weapon_select()

    def _discard_weapon_offer(self):
        """Discard the offered weapon."""
        self.weapon_offered = None
        self._post_weapon_select()

    def _post_weapon_select(self):
        """Route after weapon select: boss gives mod too, else evolution check."""
        if self._boss_reward_pending:
            self._enter_mod_select()
        else:
            self._check_evolution()

    def _enter_mod_select(self):
        """Show mod selection screen."""
        player_id = get_player_entity(self.world)
        if player_id is None:
            self._check_evolution()
            return

        inv = self.world.get_component(player_id, WeaponInventory)
        if inv is None or not inv.weapons:
            self._check_evolution()
            return

        self.mod_offered = select_mod_offer()
        self.mod_select_frame = 0
        self.phase = PHASE_MOD_SELECT

    def _apply_mod_choice(self, weapon_slot: int):
        """Attach offered mod to chosen weapon."""
        player_id = get_player_entity(self.world)
        if player_id is not None and self.mod_offered:
            inv = self.world.get_component(player_id, WeaponInventory)
            if inv and weapon_slot < len(inv.weapons):
                weapon = inv.weapons[weapon_slot]
                if len(weapon.mods) < weapon.mod_slots:
                    attach_mod(weapon, self.mod_offered)
                else:
                    # Replace oldest mod
                    attach_mod(weapon, self.mod_offered, slot=0)
        self.mod_offered = None
        self._check_evolution()

    def _discard_mod_offer(self):
        """Discard the offered mod."""
        self.mod_offered = None
        self._check_evolution()

    def _check_evolution(self):
        """Check if any weapon can evolve. If so, show evolution screen."""
        self._boss_reward_pending = False

        player_id = get_player_entity(self.world)
        if player_id is None:
            self._start_transition()
            return

        evolutions = check_all_evolutions(self.world, player_id)
        if not evolutions:
            self._start_transition()
            return

        # Offer the first eligible evolution
        weapon_idx, evo_data = evolutions[0]
        self.evolution_weapon_idx = weapon_idx
        self.evolution_data = evo_data
        self.evolution_frame = 0
        self.phase = PHASE_EVOLUTION

    def _accept_evolution(self):
        """Accept the offered evolution."""
        player_id = get_player_entity(self.world)
        if player_id is not None and self.evolution_data is not None:
            inv = self.world.get_component(player_id, WeaponInventory)
            if inv and self.evolution_weapon_idx < len(inv.weapons):
                weapon = inv.weapons[self.evolution_weapon_idx]
                evolve_weapon(weapon, self.evolution_data)
        self.evolution_data = None
        self._start_transition()

    def _decline_evolution(self):
        """Decline the offered evolution."""
        self.evolution_data = None
        self._start_transition()

    def _start_transition(self):
        """Common: enter room transition."""
        self.phase = PHASE_PLAYING
        self.room.start_transition()

    def _trigger_game_over(self):
        """Handle player death - trigger death effect then game over."""
        player_id = get_player_entity(self.world)
        if player_id is not None:
            pos = self.world.get_component(player_id, Position)
            if pos:
                # Big death explosion
                spawn_explosion(
                    self.world, pos.x, pos.y,
                    count=30,
                    colors=[NEON_RED, NEON_MAGENTA, NEON_YELLOW, WHITE],
                    chars=['@', '#', '*', '!', 'x', '+', '~'],
                    speed_min=0.5, speed_max=1.5,
                    lifetime_min=20, lifetime_max=40,
                    gravity=0.03
                )
            # Hide player
            rend = self.world.get_component(player_id, Renderable)
            if rend:
                rend.visible = False

        self.renderer.trigger_shake(intensity=4, frames=15)
        self.renderer.trigger_hitstop(10)
        self.game_over_timer = 90  # 1.5s of death particles before game over screen

    def update(self, dt: float):
        """Run one fixed-timestep tick of game logic."""
        self.phase_frame += 1

        if self.phase == PHASE_TITLE:
            return

        if self.phase == PHASE_GAME_OVER:
            return

        if self.phase == PHASE_UPGRADE_SELECT:
            self.upgrade_select_frame += 1
            return

        if self.phase == PHASE_WEAPON_SELECT:
            self.weapon_select_frame += 1
            return

        if self.phase == PHASE_MOD_SELECT:
            self.mod_select_frame += 1
            return

        if self.phase == PHASE_EVOLUTION:
            self.evolution_frame += 1
            return

        if self.phase != PHASE_PLAYING:
            return

        # Hit-stop: freeze all logic but still render
        if self.renderer.is_frozen():
            return

        # Game over delay: let death particles play out
        if self.game_over_timer > 0:
            self.game_over_timer -= 1
            lifetime_system(self.world)
            gravity_system(self.world)
            movement_system(self.world, dt)
            self.world.process_dead_entities()
            if self.game_over_timer <= 0:
                self.phase = PHASE_GAME_OVER
                self.phase_frame = 0
            return

        # Room transition: only tick transition, skip gameplay
        if self.room.transitioning:
            transition_done = self.room.update_transition()
            if transition_done:
                self._advance_room()
            return

        # Intro text overlay (non-blocking — waves handle spawning)
        if self.intro_text_active:
            self.intro_timer -= 1
            if self.intro_timer <= 0:
                self.intro_text_active = False

        # Room clear delay: wait before starting transition
        if self.room.cleared and self.room_clear_delay > 0:
            self.room_clear_delay -= 1
            if self.room_clear_delay <= 0:
                self._enter_upgrade_select()
            # Still run particles/lifetime during delay
            lifetime_system(self.world)
            gravity_system(self.world)
            movement_system(self.world, dt)
            self.world.process_dead_entities()
            return

        # Input -> intent
        self.input_handler.update()
        player_input_system(self.world, self.input_handler)

        # Handle weapon swap
        if self.input_handler.consume_swap_weapon():
            player_id = get_player_entity(self.world)
            if player_id is not None:
                swap_weapon(self.world, player_id)

        # Handle attack input
        attack_dir = self.input_handler.consume_attack()
        if attack_dir is not None:
            self._do_attack(attack_dir)

        # Handle execute chain
        if self.input_handler.consume_execute():
            execute_syntax_chain(self.world, self.renderer)

        # Beam movement lock + continuous frame tracking
        player_id = get_player_entity(self.world)
        if player_id is not None:
            attack = self.world.get_component(player_id, AttackState)
            if attack and attack.active and attack.is_beam:
                vel = self.world.get_component(player_id, Velocity)
                if vel:
                    vel.x = 0.0
                    vel.y = 0.0
                attack.beam_continuous_frames += 1
            elif attack and not attack.is_beam:
                attack.beam_continuous_frames = 0

        # Wave spawning system
        if self.room.waves is not None:
            player_id = get_player_entity(self.world)
            px, py, fx, fy = self.renderer.width / 2, self.renderer.game_height / 2, 1.0, 0.0
            if player_id is not None:
                p_pos = self.world.get_component(player_id, Position)
                p_ctrl = self.world.get_component(player_id, PlayerControlled)
                if p_pos:
                    px, py = p_pos.x, p_pos.y
                if p_ctrl:
                    fx, fy = p_ctrl.last_move_dir_x, p_ctrl.last_move_dir_y
            update_wave_system(
                self.world, self.room.waves,
                self.renderer.width - 1, self.renderer.game_height - 1,
                px, py, fx, fy, self.room.depth
            )
            telegraph_system(self.world)

        # AI
        ai_system(self.world)

        # Dash (overrides normal velocity)
        dash_system(self.world)

        # Record ghost trail BEFORE movement
        ghost_trail_system(self.world)

        # Physics
        movement_system(self.world, dt)
        gravity_system(self.world)

        # Boundaries
        wall_hits = boundary_system(
            self.world,
            self.renderer.width - 1,
            self.renderer.game_height - 1,
            margin=1
        )
        self._handle_wall_hits(wall_hits)

        # Combat
        combat_events = combat_system(self.world, self.renderer)
        for event in combat_events:
            if event['type'] == 'verb_removed':
                self.renderer.trigger_shake(intensity=1, frames=3)

        # Projectile collision
        projectile_system(
            self.world, self.renderer,
            self.renderer.width - 1, self.renderer.game_height - 1
        )

        # Enemy projectile collision
        enemy_projectile_system(
            self.world, self.renderer,
            self.renderer.width - 1, self.renderer.game_height - 1
        )

        # Mod systems
        echo_attack_system(self.world, self.renderer)
        ground_hazard_system(self.world)
        async_mod_system(self.world, self.renderer)
        grep_homing_system(self.world)
        shockwave_system(self.world, self.renderer)

        # Kill streak timer decay
        if self.kill_streak_timer > 0:
            self.kill_streak_timer -= 1
            if self.kill_streak_timer <= 0:
                self.kill_streak_count = 0

        # Death + verb drops
        death_events = death_system(self.world, self.renderer)
        kills_this_frame = []
        for event in death_events:
            if event['type'] == 'verb_drop':
                self._handle_verb_drop(event)
            elif event['type'] == 'enemy_killed':
                self.enemies_killed += 1
                kills_this_frame.append(event)
                if self.room.waves is not None:
                    self.room.waves.total_killed += 1

        # Update kill streak
        if kills_this_frame:
            self.kill_streak_count += len(kills_this_frame)
            self.kill_streak_timer = 30  # 0.5s window

            # Scale feedback based on streak
            if self.kill_streak_count >= 5:
                # Massive: heavy shake, bonus particles per kill
                self.renderer.trigger_shake(intensity=3, frames=6)
                for ev in kills_this_frame:
                    spawn_explosion(
                        self.world, ev['x'], ev['y'],
                        count=12,
                        colors=[NEON_YELLOW, WHITE, NEON_RED, NEON_CYAN],
                        chars=['*', '+', '.', '!'],
                        speed_min=0.5, speed_max=1.5,
                        lifetime_min=10, lifetime_max=20, gravity=0.02
                    )
            elif self.kill_streak_count >= 3:
                # Large: medium shake, extra particles
                self.renderer.trigger_shake(intensity=2, frames=4)
                for ev in kills_this_frame:
                    spawn_explosion(
                        self.world, ev['x'], ev['y'],
                        count=6,
                        colors=[NEON_YELLOW, WHITE],
                        chars=['*', '+', '.'],
                        speed_min=0.3, speed_max=1.0,
                        lifetime_min=8, lifetime_max=15, gravity=0.02
                    )
            elif self.kill_streak_count >= 2:
                # Small extra shake
                self.renderer.trigger_shake(intensity=1, frames=2)

        # Attack state decay
        for eid, attack in self.world.query(AttackState):
            if attack.active:
                attack.frames_remaining -= 1
                if attack.frames_remaining <= 0:
                    attack.active = False

        # Weapon cooldowns
        weapon_cooldown_system(self.world)

        # Invulnerability
        invulnerability_system(self.world)

        # Visual effect ticks
        hit_flash_system(self.world)
        animation_system(self.world)

        # Particle lifetime
        lifetime_system(self.world)

        # Verb flash timer
        if self.verb_flash_timer > 0:
            self.verb_flash_timer -= 1

        # Check player death
        player_id = get_player_entity(self.world)
        if player_id is not None:
            health = self.world.get_component(player_id, Health)
            if health and health.current <= 0:
                self._trigger_game_over()

        # Check room cleared
        if not self.room.cleared and self.room.check_cleared(self.world):
            self.room_clear_delay = 60  # 1 second delay before transition

        # Cleanup destroyed entities
        self.world.process_dead_entities()

    def _do_attack(self, direction: tuple):
        """Handle an attack in the given direction using the active weapon."""
        player_id = get_player_entity(self.world)
        if player_id is None:
            return
        execute_weapon_attack(
            self.world, player_id, direction, self.renderer
        )

    def _handle_wall_hits(self, wall_hits: list):
        """Trigger effects when entities hit walls."""
        for entity_id, impact_speed in wall_hits:
            if not self.world.has_component(entity_id, PlayerTag):
                continue

            pos = self.world.get_component(entity_id, Position)
            if pos is None:
                continue

            intensity = min(2, max(1, int(impact_speed * 2)))
            self.renderer.trigger_shake(intensity=intensity, frames=3)

            spawn_explosion(
                self.world, pos.x, pos.y,
                count=5,
                colors=[GRAY_MED, GRAY_DARK, NEON_CYAN],
                chars=['*', '.', '+'],
                speed_min=0.2,
                speed_max=0.6,
                lifetime_min=8,
                lifetime_max=15,
                gravity=0.05
            )

    def _handle_verb_drop(self, event: dict):
        """Handle a verb being dropped by a killed enemy."""
        verb = event['verb']
        added = add_verb(self.world, verb)
        if added:
            self.verb_flash_timer = 30
            self.verb_flash_text = verb
            self.verb_flash_x = event['x']
            self.verb_flash_y = event['y']

    def _cycle_debug_depth(self):
        """Debug: cycle through test depths and force room clear."""
        depth = self._debug_depths[self._debug_depth_index]
        self._debug_depth_index = (self._debug_depth_index + 1) % len(self._debug_depths)

        # Kill all existing enemies and telegraphs
        from .components import SpawnTelegraph
        for eid, _ in self.world.query(EnemyTag):
            self.world.destroy_entity(eid)
        for eid, _ in self.world.query(SpawnTelegraph):
            self.world.destroy_entity(eid)
        self.world.process_dead_entities()

        # Set depth and create waves
        self.room.depth = depth
        self.room.cleared = False
        self.room.enemies_spawned = 0
        self.room_clear_delay = 0
        self.intro_text_active = False
        self.room.waves = create_room_waves(depth)

        # Check for intro text
        intro = get_intro_text(self.room.depth)
        if intro:
            self.intro_text = intro
            self.intro_timer = 120
            self.intro_text_active = True

    def _cycle_debug_weapon(self):
        """Debug: cycle through all weapon types on F4."""
        player_id = get_player_entity(self.world)
        if player_id is None:
            return

        inv = self.world.get_component(player_id, WeaponInventory)
        if inv is None:
            return

        weapon_types = list(WEAPONS.keys())
        # Find current weapon type and advance
        current = inv.weapons[0].weapon_type if inv.weapons else 'slash'
        idx = weapon_types.index(current) if current in weapon_types else -1
        next_idx = (idx + 1) % len(weapon_types)
        next_type = weapon_types[next_idx]

        # Replace slot 0 with new weapon
        inv.weapons[0] = create_weapon(next_type)

        # If only 1 weapon, add a second slot with the next one
        if len(inv.weapons) < 2:
            next2 = weapon_types[(next_idx + 1) % len(weapon_types)]
            inv.weapons.append(create_weapon(next2))

    def _render_beam(self):
        """Render beam visual(s) when beam attack is active."""
        player_id = get_player_entity(self.world)
        if player_id is None:
            return

        attack = self.world.get_component(player_id, AttackState)
        if not attack or not attack.active or not attack.is_beam:
            return

        pos = self.world.get_component(player_id, Position)
        if pos is None:
            return

        # Get weapon data for beam count/spread/overcharge
        inv = self.world.get_component(player_id, WeaponInventory)
        _wdata = {}
        if inv and inv.weapons:
            _w = inv.weapons[min(inv.active_index, len(inv.weapons) - 1)]
            _wdata = WEAPONS.get(_w.weapon_type, {})

        beam_count = _wdata.get('beam_count', 1)
        beam_spread = _wdata.get('beam_spread_angle', 0)
        overcharge_thresh = _wdata.get('overcharge_frames', 0)
        is_overcharged = (overcharge_thresh > 0 and
                          attack.beam_continuous_frames >= overcharge_thresh)

        base_angle = math.atan2(attack.direction_y, attack.direction_x)
        beam_dirs = [(attack.direction_x, attack.direction_y)]
        if beam_count >= 3 and beam_spread > 0:
            spread_rad = math.radians(beam_spread)
            for off in (spread_rad, -spread_rad):
                a = base_angle + off
                beam_dirs.append((math.cos(a), math.sin(a)))

        beam_range = int(attack.beam_range)
        frame = self.phase_frame
        base_color = _wdata.get('color', NEON_MAGENTA)

        for dx, dy in beam_dirs:
            # Determine beam character from direction
            if abs(dx) > abs(dy):
                beam_char = '\u2500'
            elif abs(dy) > abs(dx):
                beam_char = '\u2502'
            elif dx > 0 and dy > 0:
                beam_char = '\\'
            elif dx > 0 and dy < 0:
                beam_char = '/'
            elif dx < 0 and dy > 0:
                beam_char = '/'
            else:
                beam_char = '\\'

            for i in range(1, beam_range + 1):
                bx = int(pos.x + dx * i)
                by = int(pos.y + dy * i)
                if bx < 1 or bx >= self.renderer.width - 1:
                    break
                if by < 1 or by >= self.renderer.game_height - 1:
                    break

                if is_overcharged:
                    color = WHITE if (frame + i) % 3 < 2 else NEON_YELLOW
                else:
                    pulse = (frame + i) % 4
                    color = base_color if pulse < 2 else 133

                self.renderer.put(bx, by, beam_char, color)

    def render(self):
        """Render one frame."""
        self.renderer.begin_frame()

        if self.phase == PHASE_TITLE:
            render_title_screen(self.renderer, self.phase_frame)
            output = self.renderer.end_frame()
            if output:
                print(output, end='', flush=True)
            return

        if self.phase == PHASE_GAME_OVER:
            render_game_over_screen(
                self.renderer, self.room.depth,
                self.enemies_killed, self.phase_frame
            )
            output = self.renderer.end_frame()
            if output:
                print(output, end='', flush=True)
            return

        if self.phase == PHASE_UPGRADE_SELECT:
            # Render frozen game world as background
            render_starfield(self.renderer, self.starfield)
            render_room_border(self.renderer)
            render_invulnerability_blink(self.world, self.renderer)
            render_system(self.world, self.renderer)
            particle_render_system(self.world, self.renderer)
            render_ui(self.world, self.renderer, self.room.depth,
                      self.enemies_killed)

            # Overlay upgrade selection
            player_id = get_player_entity(self.world)
            if player_id is not None:
                stats = self.world.get_component(player_id, PlayerStats)
                if stats:
                    render_upgrade_select(
                        self.renderer, self.upgrade_choices,
                        stats, self.upgrade_select_frame
                    )

            output = self.renderer.end_frame()
            if output:
                print(output, end='', flush=True)
            return

        if self.phase == PHASE_WEAPON_SELECT:
            # Render frozen game world as background
            render_starfield(self.renderer, self.starfield)
            render_room_border(self.renderer)
            render_invulnerability_blink(self.world, self.renderer)
            render_system(self.world, self.renderer)
            particle_render_system(self.world, self.renderer)
            render_ui(self.world, self.renderer, self.room.depth,
                      self.enemies_killed)

            # Overlay weapon selection
            player_id = get_player_entity(self.world)
            if player_id is not None and self.weapon_offered:
                inv = self.world.get_component(player_id, WeaponInventory)
                if inv:
                    render_weapon_select(
                        self.renderer, self.weapon_offered,
                        inv.weapons, self.weapon_select_frame
                    )

            output = self.renderer.end_frame()
            if output:
                print(output, end='', flush=True)
            return

        if self.phase == PHASE_MOD_SELECT:
            render_starfield(self.renderer, self.starfield)
            render_room_border(self.renderer)
            render_invulnerability_blink(self.world, self.renderer)
            render_system(self.world, self.renderer)
            particle_render_system(self.world, self.renderer)
            render_ui(self.world, self.renderer, self.room.depth,
                      self.enemies_killed)

            player_id = get_player_entity(self.world)
            if player_id is not None and self.mod_offered:
                inv = self.world.get_component(player_id, WeaponInventory)
                if inv:
                    render_mod_select(
                        self.renderer, self.mod_offered,
                        inv.weapons, self.mod_select_frame
                    )

            output = self.renderer.end_frame()
            if output:
                print(output, end='', flush=True)
            return

        if self.phase == PHASE_EVOLUTION:
            render_starfield(self.renderer, self.starfield)
            render_room_border(self.renderer)
            render_invulnerability_blink(self.world, self.renderer)
            render_system(self.world, self.renderer)
            particle_render_system(self.world, self.renderer)
            render_ui(self.world, self.renderer, self.room.depth,
                      self.enemies_killed)

            player_id = get_player_entity(self.world)
            if player_id is not None and self.evolution_data is not None:
                inv = self.world.get_component(player_id, WeaponInventory)
                if inv and self.evolution_weapon_idx < len(inv.weapons):
                    weapon = inv.weapons[self.evolution_weapon_idx]
                    render_evolution_screen(
                        self.renderer, weapon, self.evolution_data,
                        self.evolution_frame
                    )

            output = self.renderer.end_frame()
            if output:
                print(output, end='', flush=True)
            return

        # --- PLAYING phase ---

        # Transition animation overrides normal rendering
        if self.room.transitioning:
            render_compile_transition(
                self.renderer, self.room,
                self.renderer.width, self.renderer.game_height
            )
            render_ui(self.world, self.renderer, self.room.depth,
                      self.enemies_killed)
            output = self.renderer.end_frame()
            if output:
                print(output, end='', flush=True)
            return

        # Background layer: starfield
        render_starfield(self.renderer, self.starfield)

        # Room border
        render_room_border(self.renderer)

        # Invulnerability blink (toggle player visibility)
        render_invulnerability_blink(self.world, self.renderer)

        # Game entities (sorted by layer, includes ghost trails)
        render_system(self.world, self.renderer)

        # Particles (with braille fade)
        particle_render_system(self.world, self.renderer)

        # Beam visual (rendered live each frame the beam is active)
        self._render_beam()

        # Sniper aim lines and beams
        render_sniper_beams(
            self.world, self.renderer,
            self.renderer.width - 1, self.renderer.game_height - 1
        )

        # Intro text overlay
        if self.intro_text_active and self.intro_text:
            render_intro_text(self.renderer, self.intro_text,
                              self.intro_timer, 120)

        # Wave announcement
        render_wave_announcement(self.renderer, self.room.waves)

        # Verb pickup flash
        if self.verb_flash_timer > 0:
            render_verb_pickup_flash(
                self.renderer, self.verb_flash_text,
                self.verb_flash_x, self.verb_flash_y,
                self.verb_flash_timer
            )

        # Room cleared message
        if self.room.cleared and self.room_clear_delay > 0:
            msg = '[ ROOM CLEARED ]'
            cx = self.renderer.width // 2 - len(msg) // 2
            cy = self.renderer.game_height // 2 - 1
            self.renderer.put_string(cx, cy, msg, NEON_GREEN, with_shake=False)
            sub = f'DEPTH {self.room.depth} >> {self.room.depth + 1}'
            sx = self.renderer.width // 2 - len(sub) // 2
            self.renderer.put_string(sx, cy + 1, sub, NEON_CYAN, with_shake=False)

        # Entity count debug display
        if self.show_entity_count:
            from .components import ParticleTag, EnemyProjectileTag
            enemies = sum(1 for _ in self.world.query(EnemyTag))
            particles = sum(1 for _ in self.world.query(ParticleTag))
            e_projs = sum(1 for _ in self.world.query(EnemyProjectileTag))
            total = self.world.entity_count() if hasattr(self.world, 'entity_count') else 0
            info = f'E:{enemies} P:{particles} EP:{e_projs} T:{total}'
            self.renderer.buffer.put_string(
                self.renderer.width - len(info) - 2, 1, info, GRAY_MED
            )

        # Kill streak indicator
        if self.kill_streak_count >= 3 and self.kill_streak_timer > 0:
            streak_text = f'x{self.kill_streak_count} KILL STREAK'
            if self.kill_streak_count >= 5:
                streak_text = f'x{self.kill_streak_count} MASSACRE'
            sx = self.renderer.width // 2 - len(streak_text) // 2
            sy = 2
            streak_color = NEON_YELLOW if self.kill_streak_count < 5 else NEON_RED
            if self.kill_streak_timer % 4 < 3:  # slight flicker
                self.renderer.put_string(sx, sy, streak_text, streak_color,
                                         with_shake=False)

        # UI (no shake)
        render_ui(self.world, self.renderer, self.room.depth,
                  self.enemies_killed)

        # Finalize and output
        output = self.renderer.end_frame()
        if output:
            print(output, end='', flush=True)

    def handle_input(self):
        """Drain all pending input from the terminal."""
        key = self.term.inkey(timeout=0)
        while key:
            if self.phase == PHASE_TITLE:
                if key:
                    key_str = str(key)
                    if key_str in '123456789':
                        self.start_game(starting_depth=int(key_str))
                        return
                    elif key.name or key:
                        self.start_game()
                        return
            elif self.phase == PHASE_UPGRADE_SELECT:
                key_str = key.lower() if not key.is_sequence else ''
                if key_str in ('1', '2', '3'):
                    idx = int(key_str) - 1
                    if idx < len(self.upgrade_choices):
                        self._apply_upgrade_choice(idx)
                        return
                elif key_str == 'q' or key.name == 'KEY_ESCAPE':
                    self.running = False
                    return
            elif self.phase == PHASE_WEAPON_SELECT:
                key_str = key.lower() if not key.is_sequence else ''
                player_id = get_player_entity(self.world)
                inv = self.world.get_component(player_id, WeaponInventory) if player_id is not None else None
                max_slot = len(inv.weapons) if inv else 0
                # Allow adding to empty slot 2 if only 1 weapon
                if max_slot < 2:
                    max_slot = max_slot + 1
                if key_str == '1' and max_slot >= 1:
                    self._apply_weapon_choice(0)
                    return
                elif key_str == '2' and max_slot >= 2:
                    self._apply_weapon_choice(1)
                    return
                elif key.name == 'KEY_ESCAPE':
                    self._discard_weapon_offer()
                    return
                elif key_str == 'q':
                    self.running = False
                    return
            elif self.phase == PHASE_MOD_SELECT:
                key_str = key.lower() if not key.is_sequence else ''
                player_id = get_player_entity(self.world)
                inv = self.world.get_component(player_id, WeaponInventory) if player_id is not None else None
                num_weapons = len(inv.weapons) if inv else 0
                if key_str == '1' and num_weapons >= 1:
                    self._apply_mod_choice(0)
                    return
                elif key_str == '2' and num_weapons >= 2:
                    self._apply_mod_choice(1)
                    return
                elif key.name == 'KEY_ESCAPE':
                    self._discard_mod_offer()
                    return
                elif key_str == 'q':
                    self.running = False
                    return
            elif self.phase == PHASE_EVOLUTION:
                if key.name == 'KEY_ENTER':
                    self._accept_evolution()
                    return
                elif key.name == 'KEY_ESCAPE':
                    self._decline_evolution()
                    return
                elif key.lower() == 'q' if not key.is_sequence else False:
                    self.running = False
                    return
            elif self.phase == PHASE_GAME_OVER:
                if key.lower() == 'r':
                    self.start_game()
                    return
                elif key.lower() == 'q' or key.name == 'KEY_ESCAPE':
                    self.running = False
                    return
            else:
                self.input_handler.process_key(key)

            key = self.term.inkey(timeout=0)

        # Global actions (only during gameplay)
        if self.phase == PHASE_PLAYING:
            if self.input_handler.consume_quit():
                self.running = False

            if self.input_handler.consume_toggle_fps():
                self.renderer.show_fps = not self.renderer.show_fps

            if self.input_handler.consume_toggle_entity_count():
                self.show_entity_count = not self.show_entity_count

            if self.input_handler.consume_debug_depth():
                self._cycle_debug_depth()

            if self.input_handler.consume_debug_weapon():
                self._cycle_debug_weapon()


# =============================================================================
# MAIN LOOP
# =============================================================================

def main():
    """Entry point. Sets up terminal and runs the 60 FPS game loop."""
    term = Terminal()

    if term.width < MIN_WIDTH or term.height < MIN_HEIGHT:
        print(
            f'Terminal too small: {term.width}x{term.height}. '
            f'Minimum: {MIN_WIDTH}x{MIN_HEIGHT}'
        )
        sys.exit(1)

    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        game = GameState(term)

        last_time = time.perf_counter()
        accumulator = 0.0
        fps_timer = 0.0
        fps_frame_count = 0

        # Initial clear (only time we clear the whole screen)
        print(term.home + term.clear, end='', flush=True)

        while game.running:
            now = time.perf_counter()
            delta = now - last_time
            last_time = now

            # Clamp delta to prevent spiral of death
            delta = min(delta, FRAME_TIME * 5)

            accumulator += delta
            fps_timer += delta

            # Drain input buffer
            game.handle_input()

            # Fixed-timestep updates
            ticks = 0
            while accumulator >= FRAME_TIME and ticks < 4:
                game.update(1.0)
                accumulator -= FRAME_TIME
                ticks += 1
                fps_frame_count += 1

            # Render at display rate
            game.render()

            # FPS calculation
            if fps_timer >= 0.5:
                game.renderer.current_fps = fps_frame_count / fps_timer
                fps_frame_count = 0
                fps_timer = 0.0

            # Sleep for remaining frame time
            elapsed = time.perf_counter() - now
            sleep_time = FRAME_TIME - elapsed
            if sleep_time > 0.001:
                time.sleep(sleep_time * 0.9)

        # Restore terminal
        print(term.normal, end='', flush=True)


if __name__ == '__main__':
    main()
