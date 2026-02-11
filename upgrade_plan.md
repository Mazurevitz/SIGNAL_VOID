Act as Lead Game Developer. You are extending SIGNAL_VOID, a terminal hack-and-slash built with `blessed` in Python. The core engine (ECS, double-buffer renderer, momentum physics, Braille particle system, Syntax Chain, enemies, bosses, arena mechanics, and Syscall upgrades) already exists. Your task is to implement **a multi-layered progression system: Weapons, Weapon Mods, Micro-Upgrades, and Weapon Evolution**.

Follow all existing conventions: data-driven ECS with dataclass components, non-blocking input via `blessed.inkey()`, double-buffer rendering, Braille particles (U+2800–U+28FF), ANSI TrueColor gradients. No `curses`, no `os.system('clear')`, no blocking `input()`.

---

### DESIGN PHILOSOPHY

The goal is **multiplicative synergy between progression layers**. No single upgrade should feel game-changing alone. Instead, upgrades interact — stacking attack speed + projectile count + verb drop rate + a multi-hit weapon creates emergent power that the player *discovers* through play. Every room clear should offer a small reward. Every 3 rooms, a meaningful choice. Every boss, a transformative one.

**The three layers:**
1. **Micro-Upgrades** (every room clear) — Small stat bumps. Pick 1 of 3. Individually minor, cumulatively powerful.
2. **Weapons** (every 3 rooms + boss drops) — Distinct attack archetypes with unique hit patterns. Player carries 2, swaps with `TAB`.
3. **Mods** (every 3 rooms, offset from weapons + boss drops) — Attach to a weapon to change its behavior. Same mod on different weapons produces different results.

Additionally:
4. **Weapon Evolution** (boss kills) — If a weapon + specific micro-upgrade thresholds are met, the weapon evolves into a stronger variant.

---

### 1. WEAPONS

The player starts with `Slash /` and carries up to 2 weapons. Swap active weapon with `TAB`. Weapons are offered every 3 room clears (rooms 3, 6, 9...) and as guaranteed boss drops.

#### WEAPON SELECTION SCREEN

```
┌─── ARMORY CACHE ───────────────────────────┐
│                                             │
│  Current: [1] Slash /   [2] Ping •          │
│                                             │
│  Found:                                     │
│  [R] Fork()  ⑂   "3-spread projectile"      │
│                                             │
│  [1] Replace Slash /                        │
│  [2] Replace Ping •                         │
│  [ESC] Discard                              │
│                                             │
└─────────────────────────────────────────────┘
```

When replacing a weapon, all mods attached to the discarded weapon are lost. Show a warning if discarding a modded weapon.

#### WEAPON DEFINITIONS

Store all weapons in a data dict. Each weapon defines its own `attack_system` function that creates attack entities with appropriate components.

```python
WEAPONS = {
    "slash": {
        "symbol": "/",
        "name": "Slash",
        "color": (255, 255, 255),  # White
        "description": "Fast melee arc",
        "damage": 2,
        "attack_speed": 0.25,       # seconds between attacks (lower = faster)
        "pattern": "melee_arc",      # 90° arc in facing direction, range 2 tiles
        "projectile_count": 0,       # 0 = melee, no projectiles
        "knockback": 0.5,
        "hit_particles": "white_sparks",
        "mod_slots": 2,
    },
    "ping": {
        "symbol": "•",
        "name": "Ping",
        "color": (0, 200, 255),  # Cyan
        "description": "Ranged single shot",
        "damage": 3,
        "attack_speed": 0.6,
        "pattern": "projectile_single",  # single projectile in facing direction
        "projectile_count": 1,
        "projectile_speed": 1.5,         # cells/frame
        "projectile_range": 30,          # max travel distance in cells
        "knockback": 0.3,
        "hit_particles": "cyan_sparks",
        "mod_slots": 2,
    },
    "fork": {
        "symbol": "⑂",
        "name": "Fork()",
        "color": (0, 255, 100),  # Green
        "description": "3-way projectile spread",
        "damage": 1,
        "attack_speed": 0.5,
        "pattern": "projectile_spread",  # fires projectile_count projectiles in a spread
        "projectile_count": 3,
        "spread_angle": 30,              # degrees total spread
        "projectile_speed": 1.2,
        "projectile_range": 20,
        "knockback": 0.2,
        "hit_particles": "green_sparks",
        "mod_slots": 2,
    },
    "kill9": {
        "symbol": "█",
        "name": "Kill -9",
        "color": (255, 50, 50),  # Red
        "description": "Massive overhead slam",
        "damage": 8,
        "attack_speed": 1.2,            # very slow
        "pattern": "melee_slam",         # small 1-tile radius slam at range 1
        "projectile_count": 0,
        "knockback": 2.0,               # huge knockback
        "hit_particles": "red_debris_heavy",
        "screen_shake_on_hit": True,     # always shakes screen on hit
        "hit_stop_frames": 4,           # extra hit-stop beyond default
        "mod_slots": 2,
    },
    "rmrf": {
        "symbol": "///",
        "name": "Rm -rf",
        "color": (255, 165, 0),  # Orange
        "description": "Wide 180° sweep",
        "damage": 2,
        "attack_speed": 0.9,
        "pattern": "melee_sweep",        # 180° arc in facing direction, range 3
        "projectile_count": 0,
        "knockback": 1.0,
        "hit_particles": "orange_wave",
        "cooldown_after_use": 1.5,       # additional cooldown after the sweep
        "mod_slots": 2,
    },
    "overflow": {
        "symbol": "∞",
        "name": "Overflow",
        "color": (200, 100, 255),  # Purple
        "description": "Continuous damage beam",
        "damage": 1,                     # damage per tick (every 0.15s while held)
        "attack_speed": 0.15,            # tick rate while held
        "pattern": "beam_continuous",     # line from player in facing direction
        "projectile_count": 0,
        "beam_range": 15,
        "beam_width": 1,
        "knockback": 0.0,
        "locks_movement": True,          # player cannot move while firing
        "hit_particles": "purple_stream",
        "mod_slots": 2,
    },
}
```

#### ATTACK PATTERN IMPLEMENTATIONS

Each `pattern` type needs its own system logic:

- **`melee_arc`**: Create a temporary hitbox entity — an arc shape (90°) extending `range` tiles from the player in the facing direction. Lasts 1-2 frames. Check collision with all enemies in the arc. Render as a brief flash of `/` or `\` characters along the arc.

- **`melee_slam`**: Create a temporary hitbox entity — a single tile directly in front of the player. Lasts 3-4 frames (longer active window). Render as `█` appearing in front of player with heavy screen shake. The wind-up before the hit should be visible: player character blinks for 0.3s before the slam lands.

- **`melee_sweep`**: Create a temporary hitbox entity — a 180° arc extending `range` tiles. Lasts 2-3 frames. Render as a cascade of `─` characters sweeping across the arc. 

- **`projectile_single`**: Spawn a projectile entity with `Position`, `Velocity`, `CollisionBox`, `Renderable`, `Damage`, `Lifetime(range)`. The projectile travels in the facing direction at `projectile_speed`. On collision with an enemy, deal damage and destroy the projectile. Render as `•` with a fading TrueColor trail.

- **`projectile_spread`**: Spawn `projectile_count` projectiles. Calculate angles evenly distributed across `spread_angle`, centered on the facing direction. Each projectile behaves like `projectile_single`.

- **`beam_continuous`**: While the attack key is held, render a line of `─` (horizontal) or `│` (vertical) or `╲` `╱` (diagonal) characters from the player in the facing direction, up to `beam_range`. Every `attack_speed` seconds, deal `damage` to all enemies touching the beam. While active, the player's `Velocity` is set to zero and input is ignored for movement (but dash still works to cancel the beam). Render the beam with pulsing purple TrueColor intensity.

#### WEAPON HUD

Display current weapons in the HUD area:

```
WEAPONS: [/] Slash  ←active    [•] Ping
```

The active weapon name pulses slightly brighter. The inactive weapon is dimmed. TAB indicator shows between them.

---

### 2. WEAPON MODS

Mods attach to weapons and alter their behavior. Each weapon has `mod_slots` (default 2). Mods are offered every 3 rooms, offset from weapons (rooms 2, 5, 8...) and as boss drops.

#### MOD SELECTION SCREEN

```
┌─── PATCH AVAILABLE ────────────────────────┐
│                                             │
│  Found:  --recursive                        │
│  "Hits echo once at 50% damage"             │
│                                             │
│  Attach to:                                 │
│  [1] Slash /        (0/2 mods)              │
│  [2] Fork() ⑂      (1/2 mods: --force)     │
│  [ESC] Discard                              │
│                                             │
└─────────────────────────────────────────────┘
```

If the chosen weapon already has max mods, show the existing mods and let the player choose which to replace.

#### MOD DEFINITIONS

Mods are implemented as callbacks/modifiers that hook into the weapon's attack system. Each mod defines `on_attack`, `on_hit`, `on_kill`, or `modify_attack_params` hooks.

```python
WEAPON_MODS = {
    "recursive": {
        "name": "--recursive",
        "description": "Hits echo once at 50% damage after 0.3s",
        "rarity": "common",
        "hooks": {
            "on_hit": "echo_attack",
            # After the weapon deals damage, schedule a second identical attack
            # at the same position with 50% damage after 0.3 seconds.
            # The echo does NOT trigger further echoes (prevent infinite loops).
            # Visual: the echo attack renders in a dimmer version of the weapon's color.
        },
    },
    "verbose": {
        "name": "--verbose",
        "description": "Attacks leave a damaging ground trail for 2s",
        "rarity": "common",
        "hooks": {
            "on_attack": "create_trail",
            # Every tile the attack hitbox or projectile passes through
            # spawns a small ground-hazard entity that persists for 2 seconds.
            # Ground hazard deals 1 damage per second to enemies standing on it.
            # Render as dim version of weapon color using Braille dots on the ground.
            # Melee weapons: trail follows the arc/sweep shape.
            # Projectile weapons: trail follows the projectile path.
            # Beam weapons: the entire beam leaves a lingering trail after release.
        },
    },
    "force": {
        "name": "--force",
        "description": "Attacks deal 3× knockback",
        "rarity": "common",
        "hooks": {
            "modify_attack_params": "triple_knockback",
            # Multiply the weapon's knockback value by 3.
            # This makes Kill -9 send enemies flying across the room.
            # Enemies knocked into walls take 1 bonus damage.
            # Enemies knocked into other enemies deal 1 damage to both.
        },
    },
    "async": {
        "name": "--async",
        "description": "Weapon auto-fires every 1.5s while moving",
        "rarity": "rare",
        "hooks": {
            "passive_tick": "auto_fire",
            # Every 1.5 seconds (90 frames), automatically trigger the weapon's
            # attack in the player's current facing direction.
            # This happens even during dash or movement.
            # The auto-fire attack has 70% of normal damage (slight penalty for being free).
            # Visual: brief flash of the weapon symbol at the player's position.
            # On Slash: auto-slash nearby enemies while dodging.
            # On Fork(): passive projectile spam.
            # On Kill -9: timed slam every 1.5s — becomes a rhythm game.
            # On Overflow: does NOT work (continuous beam can't auto-fire, skip).
        },
    },
    "grep_mod": {
        "name": "--grep",
        "description": "Projectiles home slightly toward nearest enemy",
        "rarity": "common",
        "hooks": {
            "modify_projectile_velocity": "add_homing",
            # Each frame, adjust the projectile's velocity vector by up to 3°
            # toward the nearest enemy within 10 tiles.
            # On Ping: becomes a seeking missile.
            # On Fork(): three seeking missiles.
            # On melee weapons: NO EFFECT (melee has no projectiles — inform player).
            # On Overflow beam: beam bends slightly toward nearest enemy (max 15° bend).
        },
    },
    "tee": {
        "name": "| tee",
        "description": "On kill, fires a copy of the attack in a random direction",
        "rarity": "rare",
        "hooks": {
            "on_kill": "copy_attack",
            # When this weapon kills an enemy, trigger a new attack from the
            # dead enemy's position in a random direction.
            # The copy attack has 50% damage.
            # Copies CAN trigger further copies (chain kills possible!) but
            # cap at max 3 chain depth to prevent infinite loops.
            # On Fork(): kill chains can cascade through crowds.
            # On Kill -9: random death slams chain across the room.
            # Visual: brief line connecting the chain kills, rendered as dim `·` characters.
        },
    },
    "parallel": {
        "name": "--parallel",
        "description": "+1 projectile count or +30° melee arc",
        "rarity": "common",
        "hooks": {
            "modify_attack_params": "add_projectile_or_arc",
            # Projectile weapons: +1 to projectile_count.
            # Melee weapons: increase arc angle by 30° (Slash goes from 90° to 120°,
            #   Sweep goes from 180° to 210°).
            # Stacks with micro-upgrade "+1 projectile count".
            # This is the bread-and-butter DPS mod.
        },
    },
    "cron_mod": {
        "name": "--cron",
        "description": "Every 5th hit deals 3× damage",
        "rarity": "rare",
        "hooks": {
            "on_hit": "count_and_burst",
            # Track hit counter per weapon. Every 5th hit, multiply damage by 3.
            # Visual: the 5th hit flashes bright white and has extra screen shake.
            # On fast weapons (Slash, Fork, Overflow): triggers frequently.
            # On slow weapons (Kill -9): rarely triggers but 3× of 8 damage = 24 is devastating.
            # Display current hit counter near weapon HUD: small dots ●●●●○
        },
    },
    "sudo_mod": {
        "name": "--sudo",
        "description": "Attacks bypass shields and armor",
        "rarity": "rare",
        "hooks": {
            "modify_attack_params": "ignore_shield",
            # When resolving collision with a Shielded entity (e.g., Firewall front),
            # ignore the Shield component entirely. The hit registers as unshielded.
            # Also ignores any future armor/damage reduction components.
            # Replaces the 'chmod' syscall function for the attached weapon.
        },
    },
}
```

#### MOD INTERACTION MATRIX (key synergies to implement correctly)

| Weapon | --recursive | --verbose | --force | --async | | tee |
|--------|-------------|-----------|---------|---------|---------|
| Slash / | Ghost slash echo | Arc leaves ground trail | Enemies fly on hit | Auto-slash while moving | Kill chains melee |
| Ping • | Double-tap shot | Bullet trail on ground | Sniper knockback pin | Auto-snipe every 1.5s | Ricochet on kill |
| Fork() ⑂ | 3 → 6 projectiles effective | Spread trails cover area | Scatter crowd control | Passive bullet hell | Chain kills cascade |
| Kill -9 █ | Echo slam (16 total dmg) | Slam zone lingers | Enemy pinball across room | Rhythmic auto-slam | Death slams bounce |
| Rm -rf /// | Ghost sweep follows | Sweep zone stays lethal | Mass knockback wave | Auto-sweep (very strong) | Sweep chain kills |
| Overflow ∞ | Beam ticks echo (2× DPS) | Beam leaves permanent line | No knockback (beam) | N/A (skip) | Kill during beam chains |

#### MOD HUD

Display attached mods below the weapon in the HUD:

```
WEAPONS: [/] Slash  ←active    [•] Ping
          --recursive --force    --grep
```

---

### 3. MICRO-UPGRADES

Offered after every room clear. Pick 1 of 3 randomly selected upgrades. These are permanent stat modifications for the current run.

#### MICRO-UPGRADE SELECTION SCREEN

Quick, minimal UI — this should take <3 seconds to decide:

```
┌─── RUNTIME PATCH ───┐
│                      │
│  [1] +15% ATK SPD   │
│  [2] +15 MAX HP     │
│  [3] +10% CRIT      │
│                      │
└──────────────────────┘
```

No descriptions needed — the stat name IS the description. Keep it fast.

#### MICRO-UPGRADE DEFINITIONS

```python
MICRO_UPGRADES = {
    # === OFFENSE ===
    "atk_speed": {
        "name": "+15% ATK SPD",
        "category": "offense",
        "stat": "attack_speed_multiplier",
        "value": 0.85,  # multiplied into attack_speed (lower = faster), stacks multiplicatively
        "max_stacks": 6,
        "icon": "⚡",
    },
    "projectile_count": {
        "name": "+1 PROJECTILE",
        "category": "offense",
        "stat": "bonus_projectile_count",
        "value": 1,  # added to weapon projectile_count, stacks additively
        "max_stacks": 4,
        "icon": "•",
        # Only affects projectile weapons. For melee, converts to +15° arc instead.
    },
    "damage": {
        "name": "+15% DAMAGE",
        "category": "offense",
        "stat": "damage_multiplier",
        "value": 1.15,  # multiplied into damage, stacks multiplicatively
        "max_stacks": 6,
        "icon": "⚔",
    },
    "crit_chance": {
        "name": "+10% CRIT",
        "category": "offense",
        "stat": "crit_chance",
        "value": 0.10,  # added to crit_chance (base 0.05), stacks additively
        "max_stacks": 5,
        "icon": "★",
        # Critical hits deal 2× damage. Visual: crit hits flash bright yellow.
    },
    "crit_damage": {
        "name": "+25% CRIT DMG",
        "category": "offense",
        "stat": "crit_damage_multiplier",
        "value": 0.25,  # added to crit multiplier (base 2.0), stacks additively
        "max_stacks": 4,
        "icon": "✦",
    },
    "attack_size": {
        "name": "+15% ATK SIZE",
        "category": "offense",
        "stat": "attack_size_multiplier",
        "value": 1.15,  # multiplied into hitbox/projectile collision size
        "max_stacks": 5,
        "icon": "◇",
    },

    # === DEFENSE ===
    "max_hp": {
        "name": "+15 MAX HP",
        "category": "defense",
        "stat": "bonus_max_hp",
        "value": 15,  # added to max HP, stacks additively. Also heals 15 HP on pickup.
        "max_stacks": 8,
        "icon": "♥",
    },
    "damage_reduction": {
        "name": "+5% ARMOR",
        "category": "defense",
        "stat": "damage_reduction",
        "value": 0.05,  # percentage damage reduction, stacks additively, cap at 0.50
        "max_stacks": 6,  # hard cap 30%
        "icon": "◈",
    },
    "iframes": {
        "name": "+0.3s I-FRAMES",
        "category": "defense",
        "stat": "invincibility_duration",
        "value": 0.3,  # added to post-hit invincibility (base 0.5s)
        "max_stacks": 3,
        "icon": "◎",
    },
    "dash_cooldown": {
        "name": "-12% DASH CD",
        "category": "defense",
        "stat": "dash_cooldown_multiplier",
        "value": 0.88,  # multiplied into dash cooldown
        "max_stacks": 4,
        "icon": "»",
    },

    # === UTILITY ===
    "move_speed": {
        "name": "+10% SPEED",
        "category": "utility",
        "stat": "move_speed_multiplier",
        "value": 1.10,  # multiplied into max move speed
        "max_stacks": 5,
        "icon": "→",
    },
    "verb_drop_rate": {
        "name": "+10% VERB DROP",
        "category": "utility",
        "stat": "verb_drop_rate",
        "value": 0.10,  # added to verb drop chance on kill (base 0%)
        "max_stacks": 5,
        "icon": "{}",
        # Each kill has this % chance to add a random Verb to the Syntax Chain.
        # This is THE synergy stat — it makes everything else pay off faster.
    },
    "blast_radius": {
        "name": "+20% BLAST SIZE",
        "category": "utility",
        "stat": "logic_blast_radius_multiplier",
        "value": 1.20,  # multiplied into Logic Blast radius
        "max_stacks": 4,
        "icon": "⊕",
    },
    "buffer_slot": {
        "name": "+1 BUFFER SLOT",
        "category": "utility",
        "stat": "bonus_buffer_slots",
        "value": 1,  # adds one slot to the Syntax Chain buffer (base 3)
        "max_stacks": 2,  # max buffer size: 5
        "icon": "▣",
        "rarity": "legendary",  # appears very rarely in the pool
        # More buffer slots = more verbs needed but more powerful Logic Blasts.
        # Also makes Buffer Overflow (3 identical) harder to achieve but allows
        # new 4× and 5× identical overflow combos if defined.
    },
}
```

#### SELECTION LOGIC

- Offer 3 upgrades per room clear, randomly selected.
- No duplicates in a single offer.
- Upgrades at max stacks are excluded from the pool.
- Guarantee at least 1 offense, 1 defense OR 1 utility in every offer (prevent all-offense or all-defense rolls).
- `"legendary"` rarity upgrades have 5% chance to appear in any given offer.

#### MICRO-UPGRADE TRACKING

Track all acquired upgrades in a `PlayerStats` component:

```python
@dataclass
class PlayerStats:
    # Multiplicative stats (multiply together)
    attack_speed_multiplier: float = 1.0
    damage_multiplier: float = 1.0
    attack_size_multiplier: float = 1.0
    move_speed_multiplier: float = 1.0
    dash_cooldown_multiplier: float = 1.0
    logic_blast_radius_multiplier: float = 1.0
    crit_damage_multiplier: float = 2.0  # base crit multiplier
    
    # Additive stats (add together)
    bonus_max_hp: int = 0
    bonus_projectile_count: int = 0
    bonus_buffer_slots: int = 0
    crit_chance: float = 0.05  # base 5% crit
    damage_reduction: float = 0.0
    invincibility_duration: float = 0.5  # base i-frames
    verb_drop_rate: float = 0.0
    
    # Stack tracking (for evolution thresholds)
    upgrade_counts: dict = field(default_factory=dict)  # {"atk_speed": 3, "damage": 2, ...}
```

Every system that reads player stats must apply these modifiers. For example, the attack system calculates final damage as:
`final_damage = weapon.damage × player_stats.damage_multiplier × (crit_multiplier if crit)`

---

### 4. WEAPON EVOLUTION

Weapons evolve when the player meets specific micro-upgrade thresholds. Evolution is checked after every boss kill. If conditions are met, the evolution is offered automatically.

#### EVOLUTION SCREEN

```
┌─── COMPILATION COMPLETE ──────────────────────────┐
│                                                    │
│        /  ──────►  ⚡/                              │
│      Slash       Quicksort                         │
│                                                    │
│  "Attack speed threshold reached."                 │
│  "Slash has evolved into Quicksort."               │
│                                                    │
│  ⚡/ Quicksort: 2× attack speed, attacks generate  │
│     afterimages that deal 30% damage               │
│                                                    │
│  [ENTER] Accept    [ESC] Decline                   │
│                                                    │
└────────────────────────────────────────────────────┘
```

The player can decline an evolution (they might prefer the base weapon's simpler behavior). Declined evolutions can be accepted later at the next boss.

#### EVOLUTION DEFINITIONS

```python
WEAPON_EVOLUTIONS = {
    "slash": {
        "required_upgrade": "atk_speed",
        "required_stacks": 4,
        "evolves_to": "quicksort",
        "evolution_data": {
            "symbol": "⚡/",
            "name": "Quicksort",
            "color": (255, 255, 100),  # Bright yellow
            "description": "Blazing melee with afterimages",
            "damage": 2,
            "attack_speed": 0.12,           # twice as fast as base Slash
            "pattern": "melee_arc",
            "projectile_count": 0,
            "knockback": 0.5,
            "hit_particles": "yellow_sparks",
            "mod_slots": 3,                 # gains an extra mod slot
            "special": "afterimage",
            # Every 3rd attack spawns an afterimage at the player's position
            # that performs the same attack 0.2s later at 30% damage.
            # Afterimage renders as a dim, fading copy of the player character.
        },
    },
    "ping": {
        "required_upgrade": "damage",
        "required_stacks": 4,
        "evolves_to": "segfault",
        "evolution_data": {
            "symbol": "◉",
            "name": "Segfault",
            "color": (255, 0, 0),  # Red
            "description": "Piercing shot that stuns",
            "damage": 6,
            "attack_speed": 0.8,
            "pattern": "projectile_single",
            "projectile_count": 1,
            "projectile_speed": 2.5,        # very fast
            "projectile_range": 50,         # crosses entire arena
            "knockback": 1.5,
            "hit_particles": "red_flash_heavy",
            "mod_slots": 3,
            "special": "pierce_and_stun",
            # Projectile pierces through all enemies (doesn't stop on first hit).
            # Each enemy hit is stunned for 0.8 seconds.
            # Visual: the projectile is a bright red `◉` with a long trailing line.
        },
    },
    "fork": {
        "required_upgrade": "projectile_count",
        "required_stacks": 3,
        "evolves_to": "ddos",
        "evolution_data": {
            "symbol": "⑂⑂",
            "name": "DDoS",
            "color": (0, 255, 50),  # Bright green
            "description": "8-projectile omnidirectional burst",
            "damage": 1,
            "attack_speed": 0.6,
            "pattern": "projectile_radial",  # fires in all directions
            "projectile_count": 8,
            "spread_angle": 360,             # full circle
            "projectile_speed": 1.0,
            "projectile_range": 15,
            "knockback": 0.3,
            "hit_particles": "green_scatter",
            "mod_slots": 3,
            "special": "wave_pattern",
            # Every other shot alternates the angle offset by 22.5°,
            # creating an alternating wave pattern of projectiles.
            # Combined with attack speed upgrades, this fills the screen.
        },
    },
    "kill9": {
        "required_upgrade": "crit_chance",
        "required_stacks": 3,
        "evolves_to": "kernel_panic_weapon",
        "evolution_data": {
            "symbol": "▓█▓",
            "name": "Kernel Panic",
            "color": (255, 0, 0),  # Red
            "description": "Slam creates shockwave ring",
            "damage": 10,
            "attack_speed": 1.0,            # slightly faster than base
            "pattern": "melee_slam_shockwave",
            "projectile_count": 0,
            "knockback": 2.5,
            "hit_particles": "red_debris_massive",
            "screen_shake_on_hit": True,
            "hit_stop_frames": 6,
            "mod_slots": 3,
            "special": "shockwave",
            # After the slam lands, a ring of `░` characters expands outward
            # from the impact point at 1 cell/frame for 5 frames (radius 5).
            # The ring deals 3 damage to any enemy it passes through.
            # Every hit is automatically a critical hit (100% crit chance for this weapon).
        },
    },
    "rmrf": {
        "required_upgrade": "attack_size",
        "required_stacks": 4,
        "evolves_to": "format",
        "evolution_data": {
            "symbol": "///*",
            "name": "Format C:",
            "color": (255, 200, 0),  # Gold
            "description": "Full 360° sweep, double range",
            "damage": 3,
            "attack_speed": 1.0,
            "pattern": "melee_sweep",
            "sweep_angle": 360,             # full circle
            "sweep_range": 5,               # double the base range
            "projectile_count": 0,
            "knockback": 1.5,
            "hit_particles": "gold_wave_ring",
            "cooldown_after_use": 1.8,
            "mod_slots": 3,
            "special": "vacuum",
            # Before the sweep, enemies within range 8 are pulled TOWARD
            # the player over 0.5 seconds (reverse knockback).
            # Then the 360° sweep hits everything that was pulled in.
            # Visual: brief inward-pulling particle lines before the sweep.
        },
    },
    "overflow": {
        "required_upgrade": "max_hp",
        "required_stacks": 4,
        "evolves_to": "stack_overflow",
        "evolution_data": {
            "symbol": "∞∞",
            "name": "Stack Overflow",
            "color": (255, 50, 255),  # Bright magenta
            "description": "Beam splits into 3 directions",
            "damage": 1,
            "attack_speed": 0.12,           # faster tick rate
            "pattern": "beam_triple",
            "beam_count": 3,                # fires 3 beams at 0°, +30°, -30° from facing
            "beam_range": 18,
            "beam_width": 1,
            "knockback": 0.1,
            "locks_movement": True,
            "hit_particles": "magenta_stream_triple",
            "mod_slots": 3,
            "special": "overcharge",
            # After firing continuously for 3 seconds, the beams double in width
            # and damage for as long as you keep holding. The overcharge state
            # renders the beams as bright white instead of magenta.
            # Risk/reward: standing still for 3s is dangerous, but the payoff is huge.
        },
    },
}
```

#### EVOLUTION CHECK LOGIC

```python
def check_evolution(player_weapon, player_stats):
    """Called after each boss kill. Returns evolution data or None."""
    weapon_key = player_weapon.base_type  # original weapon type, not evolved
    if weapon_key not in WEAPON_EVOLUTIONS:
        return None
    if player_weapon.is_evolved:
        return None  # already evolved
    
    evo = WEAPON_EVOLUTIONS[weapon_key]
    required = evo["required_upgrade"]
    stacks = player_stats.upgrade_counts.get(required, 0)
    
    if stacks >= evo["required_stacks"]:
        return evo
    return None
```

---

### 5. REWARD SCHEDULE

Codify exactly when each reward type appears:

```python
REWARD_SCHEDULE = {
    # Every room clear
    "micro_upgrade": "every_room",
    
    # Alternating every 3 rooms (weapons on 3,6,9...; mods on 2,5,8...)
    "weapon": lambda depth: depth % 3 == 0 and depth > 0,
    "mod": lambda depth: depth % 3 == 2,
    
    # Boss rewards (depths 5, 10, 15...)
    "boss_reward": "boss_kill",
    # Boss rewards give ALL of: 1 weapon choice, 1 mod choice, AND evolution check.
    # This makes boss kills feel like jackpots.
    
    # Syscall upgrades (from existing system) continue on their existing schedule.
}
```

**Room clear sequence:**
1. All enemies dead → "ROOM CLEARED" flash
2. Micro-upgrade selection (fast, <3 seconds)
3. If weapon room: weapon selection
4. If mod room: mod selection
5. If boss: weapon + mod + evolution check + Syscall
6. Compile transition animation → next room

---

### 6. SYNERGY EXAMPLES (for testing and balancing)

Implement these specific synergy paths and verify they work:

**Build 1: "Bullet Hell"**
- Weapon: Fork() + evolution to DDoS (8 projectiles)
- Upgrades: +1 projectile ×3, +15% atk speed ×3
- Mods: --recursive (echoes double effective hits), --grep (homing)
- Result: 11 homing projectiles per attack, each echoing → 22 effective hits per attack, firing very fast. Screen filled with green dots. Verb drop rate at +30% means ~6 verbs per attack. Logic Blast every fight.
- **Verify:** Game must not lag. Particle system must handle this volume.

**Build 2: "One Punch"**
- Weapon: Kill -9 + evolution to Kernel Panic
- Upgrades: +15% damage ×5, +25% crit damage ×3, +10% crit ×4
- Mods: --cron (every 5th hit 3×), --recursive (echo at 50%)
- Result: Base 10 damage × 2.01 damage multiplier = ~20. Crit: 20 × 3.75 crit multiplier = 75. On 5th hit with --cron: 75 × 3 = 225. Plus echo at 50% = 337 total. One-shots everything except bosses.
- **Verify:** Damage numbers display correctly, screen shake is appropriately violent.

**Build 3: "Immortal Turret"**
- Weapon: Overflow + evolution to Stack Overflow (triple beam)
- Upgrades: +15 max HP ×5, +5% armor ×4, +0.3s i-frames ×2
- Mods: --verbose (beam leaves trail), | tee (kills fire copies)
- Result: Player is tanky enough to stand still and beam. Triple beam covers wide area. Trails linger, creating kill zones. Chain kills from | tee spread damage to off-screen enemies.
- **Verify:** Beam rendering performs well, trails don't consume excessive memory.

---

### 7. IMPLEMENTATION DETAILS

#### New Components (add to `components.py`)

```python
@dataclass
class WeaponComponent:
    weapon_type: str            # key from WEAPONS dict
    base_type: str              # original type (for evolution tracking)
    is_evolved: bool = False
    mods: list = field(default_factory=list)  # list of mod keys
    mod_slots: int = 2
    attack_timer: float = 0.0   # time until next attack allowed
    hit_counter: int = 0        # for --cron mod tracking

@dataclass
class WeaponInventory:
    weapons: list = field(default_factory=list)  # list of WeaponComponent, max 2
    active_index: int = 0       # 0 or 1

@dataclass
class Projectile:
    damage: float
    owner_id: int               # entity ID of the attacker
    speed: float
    max_range: float
    distance_traveled: float = 0.0
    piercing: bool = False
    homing_strength: float = 0.0  # degrees per frame of homing
    echo_depth: int = 0          # for --recursive, prevents infinite echoes
    chain_depth: int = 0         # for | tee, caps at 3

@dataclass
class GroundHazard:
    damage_per_second: float
    duration: float              # seconds remaining
    color: tuple = (100, 100, 100)

@dataclass
class PlayerStats:
    attack_speed_multiplier: float = 1.0
    damage_multiplier: float = 1.0
    attack_size_multiplier: float = 1.0
    move_speed_multiplier: float = 1.0
    dash_cooldown_multiplier: float = 1.0
    logic_blast_radius_multiplier: float = 1.0
    crit_damage_multiplier: float = 2.0
    bonus_max_hp: int = 0
    bonus_projectile_count: int = 0
    bonus_buffer_slots: int = 0
    crit_chance: float = 0.05
    damage_reduction: float = 0.0
    invincibility_duration: float = 0.5
    verb_drop_rate: float = 0.0
    upgrade_counts: dict = field(default_factory=dict)
```

#### New/Modified Files

```
signal_void/
├── main.py
├── engine.py
├── ecs.py
├── components.py       # Add WeaponComponent, WeaponInventory, Projectile, GroundHazard, PlayerStats
├── systems.py          # Modify — integrate PlayerStats into all combat calculations
├── player.py           # Modify — weapon swap (TAB), attack dispatches to active weapon
├── weapons.py          # NEW — Weapon definitions, attack pattern implementations, weapon swap logic
├── weapon_mods.py      # NEW — Mod definitions, hook system, mod application logic
├── micro_upgrades.py   # NEW — Upgrade definitions, selection screen, stat application
├── evolution.py        # NEW — Evolution definitions, threshold checking, evolution screen
├── projectiles.py      # NEW — Projectile system (movement, collision, homing, piercing, lifetime)
├── ground_hazards.py   # NEW — Ground hazard system (--verbose trails, timed damage zones)
├── rewards.py          # NEW — Reward schedule, room-clear sequence orchestration
├── enemies.py
├── spawner.py
├── bosses.py
├── arena.py
├── upgrades.py         # Existing syscall system (unchanged)
├── particles.py
├── syntax_chain.py     # Modify — integrate verb_drop_rate from PlayerStats
└── rooms.py            # Modify — integrate reward schedule into room transitions
```

---

### 8. BUILD ORDER

- **Phase A:** PlayerStats component and micro-upgrade system — stat tracking, selection screen, stat application to existing movement/combat systems. **Verify:** Picking "+10% SPEED" makes the player visibly faster; picking "+15 MAX HP" increases health bar; stacks accumulate correctly across rooms.

- **Phase B:** Weapon framework — WeaponComponent, WeaponInventory, weapon swap with TAB, `melee_arc` pattern for Slash (replacing existing attack). **Verify:** Player attacks with Slash, can swap weapons with TAB, attack speed and damage respond to PlayerStats multipliers.

- **Phase C:** Projectile system — implement `projectile_single` and `projectile_spread` patterns, projectile entity lifecycle (spawn, move, collide, die). Add Ping and Fork() weapons. **Verify:** Ping fires a single aimed projectile; Fork() fires 3-spread; projectiles collide with enemies and deal damage.

- **Phase D:** Remaining weapons — Kill -9 (`melee_slam`), Rm -rf (`melee_sweep`), Overflow (`beam_continuous`). **Verify:** Each weapon has a distinct feel and hit pattern; Kill -9 shakes the screen; Overflow locks movement.

- **Phase E:** Weapon selection screen — offer weapons every 3 rooms, handle weapon replacement with mod warning, boss weapon drops. **Verify:** Selection UI renders correctly, replacing a modded weapon shows warning, weapon appears in HUD.

- **Phase F:** Mod system — hook architecture (on_attack, on_hit, on_kill, modify_attack_params, passive_tick), implement --recursive and --force as first two mods. **Verify:** --recursive creates echo attacks at 50% damage; --force triples knockback. Echoes don't trigger further echoes.

- **Phase G:** Remaining mods — --verbose, --async, --grep, | tee, --parallel, --cron, --sudo. Test each mod on each weapon type. **Verify:** Mod interaction matrix works correctly; | tee chain depth caps at 3; --async doesn't fire Overflow.

- **Phase H:** Mod selection screen — offer mods every 3 rooms (offset from weapons), attach to chosen weapon, replacement flow for full mod slots. **Verify:** UI shows which weapons have which mods, can replace existing mods.

- **Phase I:** Weapon evolution — threshold checking after boss kills, evolution screen, all 6 evolved weapons with their special mechanics. **Verify:** Slash evolves to Quicksort after 4 atk_speed stacks; evolution is declinable; evolved weapons have 3 mod slots.

- **Phase J:** Reward orchestration — full room-clear → micro-upgrade → weapon/mod → evolution → compile transition flow. **Verify:** Complete gameplay loop from room 1 through boss with all progression layers active. Test synergy builds from Section 6.

- **Phase K:** Performance testing — stress test Build 1 ("Bullet Hell") with 22+ projectiles on screen. Ensure particle system and projectile system maintain 55+ FPS. Optimize if needed (spatial hashing for collision, object pooling for projectiles).

---

### 9. CONSTRAINTS REMINDER

- All weapon attacks create entities through the ECS — no special-case rendering outside the render system.
- Projectiles must be proper entities with Position, Velocity, CollisionBox, Renderable, Projectile components.
- Mod hooks must not mutate weapon definitions — they modify attack parameters at runtime only.
- PlayerStats multipliers are applied in systems, not baked into component values (so removing an upgrade would be possible if that feature is added later).
- All selection screens (micro-upgrade, weapon, mod, evolution) must use the double-buffer renderer.
- Debug key (`F4`): cycle through all weapons instantly for testing.
- Debug key (`F5`): grant all micro-upgrades at max stacks for testing evolution thresholds.
- Weapon and mod data dicts must be trivially extensible — adding a new weapon or mod should require only a new dict entry and (if needed) a new pattern/hook function.
- All visual feedback for attacks must use Braille particles and TrueColor.
- Clean terminal restoration on exit regardless of game state.

**Begin with Phase A: PlayerStats component and Micro-Upgrade system.**