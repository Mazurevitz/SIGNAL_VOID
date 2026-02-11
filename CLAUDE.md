# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SIGNAL_VOID is a terminal-based hack-and-slash game built with Python and the `blessed` library. It features neon aesthetics, kinetic combat with "game juice" effects, and runs at 60 FPS in the terminal.

## Commands

```bash
# Install dependency
pip install blessed

# Run the game (ECS version)
python3 run.py

# Run legacy POC (single-file)
python3 signal_void_poc.py
```

## Project Structure

```
signal_void/
├── main.py           # Entry point, game loop, UI rendering
├── engine.py         # DoubleBuffer, BrailleCanvas, GameRenderer
├── ecs.py            # Entity-Component-System core (World class)
├── components.py     # All component dataclasses
├── systems.py        # System functions (movement, collision, AI, combat, render)
├── player.py         # Player entity creation, InputHandler
├── enemies.py        # Enemy archetypes (BufferLeak, Firewall, Overclocker)
├── particles.py      # Particle spawning and effects
├── syntax_chain.py   # Verb collection and Logic Blast execution
└── rooms.py          # Room generation and transitions
```

## Architecture

### Entity-Component-System (ECS)

Data-driven architecture where:
- **Entities** are integer IDs
- **Components** are plain dataclasses with no behavior (in `components.py`)
- **Systems** are functions that query and process entities (in `systems.py`)

```python
# Query pattern
for entity_id, pos, vel in world.query(Position, Velocity):
    pos.x += vel.x
```

### Core Engine (`engine.py`)

- **DoubleBuffer**: Dirty-cell rendering to prevent flicker
- **BrailleCanvas**: Sub-pixel rendering using Unicode Braille (U+2800) for 2x4 resolution
- **GameRenderer**: High-level API with screen shake and hit-stop effects

### Game Loop (`main.py`)

- Fixed 60 FPS with accumulator pattern
- Non-blocking input via `blessed.inkey(timeout=0)`
- Key hold detection using frame-based timers

### Component Categories

| Category | Components |
|----------|------------|
| Physics | Position, Velocity, Friction, MaxSpeed, Knockback, CollisionBox |
| Rendering | Renderable, GhostTrail, AnimationState, HitFlash |
| Combat | Health, Shield, Damage, Invulnerable, AttackState |
| Player | PlayerControlled, DashState, SyntaxBuffer |
| AI | AIBehavior, AIState, ChargeAttack |
| Effects | ScreenShake, HitStop, Lifetime, Gravity, ParticleTag |

### Enemy Archetypes

| Enemy | Char | Behavior | Special Mechanic | Verb Drop |
|-------|------|----------|------------------|-----------|
| Buffer-Leak | `&` | Fast chase with lunges | Removes verbs on hit | RECURSIVE (on kill) |
| Firewall | `H` | Slow guard, tracks player | Frontal shield blocks damage | SUDO (on backstab) |
| Overclocker | `>` | Charge then dash | Red telegraph, damage trail | DASH (on dodge) |

### AI System (`systems.py`)

- **Chase behavior** (Buffer-Leak): IDLE → DETECT → CHASE → ATTACK → RECOVER
- **Guard behavior** (Firewall): Slow approach, always faces player, shield active
- **Charge behavior** (Overclocker): Chase → CHARGE (red telegraph) → ATTACK (dash) → RECOVER

### Combat System (`systems.py`)

- **Player slash vs enemy**: Cone-based hit detection, 25 damage, knockback, hit-stop, directional sparks
- **Shield blocking** (Firewall): Frontal hits blocked (dot product check), player knocked back. Backstabs bypass shield.
- **Enemy contact vs player**: AABB collision, damage, 45 i-frames, knockback away from enemy
- **Dash i-frames**: Player is invulnerable while dashing

### Verb Collection Flow

- Enemy dies → `death_system` emits verb drop event based on condition:
  - Buffer-Leak: `kill` → RECURSIVE
  - Firewall: `backstab` → SUDO
  - Overclocker: `dodge` → DASH
- Game loop calls `add_verb()` → added to player's 3-slot `SyntaxBuffer`
- UI shows verb in buffer, `+[VERB]` pickup indicator floats at kill location
- Press `H` when buffer is full to execute Logic Blast

## Controls

| Action | Key |
|--------|-----|
| Move | WASD |
| Slash | IJKL (I=up, K=down, J=left, L=right) |
| Dash | Spacebar |
| Execute Chain | H |
| Toggle FPS | F |
| Quit | Q/Escape |

## Build Phases

1. **Phase 1** ✅ Core loop + double-buffer + momentum movement
2. **Phase 2** ✅ Braille particles + dash trails + screen shake + hit-stop
3. **Phase 3** ✅ Buffer-Leak enemy with collision and death particles
4. **Phase 4** ✅ Firewall + Overclocker with unique AI
5. **Phase 5** ✅ Syntax Chain UI + verb collection + Logic Blast
6. **Phase 6** ✅ Room progression + compile transition animation
