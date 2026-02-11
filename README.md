```
  ___ ___ ___ _  _   _   _       __   _____  ___ ___
 / __|_ _/ __| \| | /_\ | |      \ \ / / _ \|_ _|   \
 \__ \| | (_ | .` |/ _ \| |__     \ V / (_) || || |) |
 |___/___\___|_|\_/_/ \_\____|     \_/ \___/|___|___/
```

**A hack-and-slash roguelike that runs in your terminal.**

![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)
![Terminal](https://img.shields.io/badge/platform-terminal-black.svg)
![Dependencies](https://img.shields.io/badge/dependencies-1-brightgreen.svg)

---

Neon-drenched combat at 60 FPS. Momentum-based movement, directional melee, dash i-frames, enemy projectiles cutting across the screen, and wave after wave of hostiles spawning around you. Kill fast or get overwhelmed.

Built entirely in Python with a single dependency. No curses. No pygame. Just raw terminal output, Unicode rendering, and ANSI color.

## Features

- **60 FPS combat** with fixed timestep, screen shake, hit-stop, and knockback
- **5 enemy types** with distinct AI: swarmers, shields, chargers, ranged fodder, snipers
- **Wave spawning system** with choreographed spawn patterns and telegraph warnings
- **12 weapons** across 6 base types with evolution paths
- **9 weapon mods** that alter attack behavior
- **15 micro-upgrades** for stat progression between rooms
- **Braille sub-pixel particles** (U+2800 block) for high-resolution visual effects
- **Double-buffered rendering** with dirty-cell diffing for flicker-free output
- **ECS architecture** -- entities are ints, components are dataclasses, systems are functions

## Quick Start

```bash
pip install blessed
git clone https://github.com/Mazurevitz/SIGNAL_VOID.git
cd SIGNAL_VOID
python3 run.py
```

## Controls

| Action | Key |
|--------|-----|
| Move | `W` `A` `S` `D` |
| Attack | `I` `J` `K` `L` (up/left/down/right) |
| Dash | `Space` |
| Execute Syntax Chain | `H` (when buffer is full) |
| Swap Weapon | `Tab` |
| Toggle FPS | `F` |
| Quit | `Q` / `Esc` |

## How It Works

You descend through rooms. Each room spawns enemies in waves. Kill everything to advance.

### Enemies

| Type | Char | Behavior |
|------|------|----------|
| Buffer-Leak | `&` | Fast swarm. Lunges when close. Dies in one hit. |
| Firewall | `H` | Frontal shield blocks damage. Intercepts your path. Backstab to kill. |
| Overclocker | `>` | Orbits at range, then charges with a red telegraph. |
| Spammer | `!` | Maintains distance. Fires yellow `·` projectiles every 2s. Flees when rushed. |
| Sniper | `¦` | Charges a visible aim line that tracks you, locks, then fires a hitscan beam. |

### The Syntax Chain

Enemies drop **verbs** on death: `RECURSIVE`, `SUDO`, `DASH`. Collect three to fill your buffer, then press `H` to execute a Logic Blast -- a screen-clearing chain attack whose effect depends on the verbs collected.

### Weapons & Upgrades

Between rooms, you're offered upgrades: stat boosts, new weapons, weapon mods, or evolution paths that transform base weapons into specialized variants. The build you choose determines how you handle the escalating waves.

### Waves

Rooms spawn enemies across 2-4 waves using choreographed patterns -- surround, pincer, behind-player, ring. Later waves trigger before earlier ones are fully cleared. Timer-based waves in deep rooms punish hesitation. Spawn telegraphs (flickering red `×`) give you a split-second to read the incoming threat pattern.

## Architecture

```
signal_void/
├── main.py              # Game loop, state machine, UI rendering
├── engine.py            # DoubleBuffer, BrailleCanvas, GameRenderer
├── ecs.py               # Entity-Component-System core
├── components.py        # All component dataclasses
├── systems.py           # Movement, collision, AI, combat systems
├── player.py            # Player entity, input handling
├── enemies.py           # Enemy archetypes and factories
├── weapons.py           # 12 weapons with unique attack patterns
├── weapon_mods.py       # 9 mods that alter weapon behavior
├── micro_upgrades.py    # 15 stat upgrades
├── evolution.py         # Weapon evolution system
├── wave_spawner.py      # Wave system, spawn patterns, room templates
├── enemy_projectiles.py # Enemy projectile system
├── projectiles.py       # Player projectile system
├── particles.py         # Braille particle effects
├── syntax_chain.py      # Verb collection and Logic Blast
├── rooms.py             # Room state and transitions
└── spawner.py           # Enemy spawn orchestration
```

The game uses a data-driven **Entity-Component-System**. Entities are integer IDs. Components are plain Python dataclasses with no behavior. Systems are functions that query the world for entities matching component signatures and update them.

Rendering uses a custom **double-buffered** system: each frame writes to a back buffer, diffs against the front buffer, and emits only the changed cells as ANSI escape sequences. Sub-pixel effects use **Unicode Braille characters** (U+2800-U+28FF) which encode a 2x4 dot grid per character cell.

## Requirements

- **Python 3.8+**
- **blessed** (`pip install blessed`)
- A terminal emulator with:
  - Unicode support (for Braille particles and box-drawing)
  - 256-color mode (for neon color palette)
  - Minimum 80x24 characters

**Recommended terminals:** iTerm2, Alacritty, WezTerm, kitty, Windows Terminal, or any modern terminal with TrueColor support.

## Troubleshooting

**Game looks garbled or flickers:**
Your terminal may not support the required Unicode characters. Try a different terminal emulator.

**Colors look wrong:**
Ensure your terminal supports 256-color mode. Most modern terminals do by default.

**Input feels laggy:**
Terminal key repeat rate affects movement responsiveness. The game uses frame-based key hold detection to compensate, but lowering your OS key repeat delay can help.

**Terminal too small:**
The game requires at minimum 80 columns and 24 rows. Resize your terminal or reduce font size.

## License

MIT
