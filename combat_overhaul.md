Act as Lead Game Developer. You are overhauling the combat feel of SIGNAL_VOID, a terminal hack-and-slash built with `blessed` in Python. The game currently has a core engine, ECS, weapons, progression systems, and enemy types — but **combat feels empty and passive**. The problem: too few enemies, enemies that only engage at close range, no ranged threats, and no wave pressure.

The goal is to make SIGNAL_VOID feel like **Hades in a terminal** — constant action, enemies aggressively pursuing and attacking from the moment they spawn, projectiles flying across the screen, and the player always moving, always dodging, always fighting.

Follow all existing conventions: data-driven ECS with dataclass components, non-blocking input via `blessed.inkey()`, double-buffer rendering, Braille particles (U+2800–U+28FF), ANSI TrueColor gradients. No `curses`, no `os.system('clear')`, no blocking `input()`.

---

### 1. THE PROBLEM (what to fix)

Current state:
- Rooms spawn 3–5 enemies total.
- Enemies use simple "chase player" AI and only attack on contact.
- If the player stands far away, nothing happens — zero pressure.
- Fights feel like slowly walking up to targets and poking them.

Target state:
- Rooms spawn 12–25+ enemies across 2–4 waves.
- Enemies attack aggressively from the moment they spawn — ranged enemies shoot immediately, melee enemies sprint toward the player.
- There should ALWAYS be something on screen flying toward the player — a projectile, a charging enemy, a closing swarm.
- The player should never be able to stand still safely for more than ~1 second.
- Fights should last 20–40 seconds per room, not 5–10.

---

### 2. WAVE SPAWNING SYSTEM

Rooms no longer spawn all enemies at once. Instead, rooms have **waves** that deploy enemies in choreographed patterns.

#### WAVE STRUCTURE

```python
@dataclass
class RoomWaves:
    waves: list          # list of Wave objects
    current_wave: int = 0
    enemies_alive: int = 0
    wave_triggered: bool = False

@dataclass
class Wave:
    spawn_groups: list   # list of SpawnGroup objects
    trigger: str         # "on_start", "on_kill_percent", "on_timer"
    trigger_value: float # kill% threshold or seconds delay
    announcement: str    # text flash, e.g. ">>> WAVE 2 <<<" or None

@dataclass
class SpawnGroup:
    enemy_type: str
    count: int
    spawn_pattern: str   # "surround", "line_top", "line_bottom", "corners", "behind_player", "random", "ring", "pincer"
    delay: float         # seconds after wave trigger before this group spawns (for staggering)
```

#### WAVE TRIGGER TYPES

- **`on_start`**: Spawns immediately when the room begins. Always used for Wave 1.
- **`on_kill_percent`**: Triggers when a percentage of total wave enemies are dead. Example: Wave 2 triggers when 60% of Wave 1 is killed — the player never gets a breather.
- **`on_timer`**: Triggers after N seconds regardless of kills. Creates urgency — if you're too slow, more enemies pile on.

#### SPAWN PATTERNS

Enemies should NOT just appear at random positions. Spawn patterns create **tactical pressure**:

- **`surround`**: Enemies spawn in a ring around the player at radius 8–12 tiles. Immediately closes in. The most aggressive pattern.
- **`line_top`**: Enemies spawn in a line across the top of the arena, then advance downward. Wall of enemies.
- **`line_bottom`**: Same but from the bottom.
- **`corners`**: Enemies spawn in all 4 corners and converge on center. Forces the player to pick a direction.
- **`behind_player`**: Enemies spawn 6–10 tiles directly behind the player's current facing direction. Punishes tunnel vision.
- **`random`**: Classic random positions, but guaranteed minimum 6 tiles from player (no unfair spawns on top of player).
- **`ring`**: Enemies spawn in a tight ring at radius 4–5. Immediate threat. Used for elite/dangerous enemies.
- **`pincer`**: Half spawn to the left of the player, half to the right. Forces a choice of which side to engage first.

#### SPAWN ANIMATION

Enemies do NOT just pop into existence. Spawn sequence (0.5 seconds):
1. A dim red `×` appears at the spawn position, flickering for 0.3 seconds (telegraph).
2. Brief flash of bright red at the position.
3. Enemy entity appears with a small outward burst of Braille particles in the enemy's color.
4. Enemy is invulnerable for 0.2 seconds after spawning (prevents spawn-killing with area attacks).

This telegraph gives the player a split-second to read where threats are coming from.

#### ROOM TEMPLATES BY DEPTH

```python
ROOM_TEMPLATES = {
    # Depth 1-2: Tutorial rooms. Low enemy count, single wave, gentle.
    "tutorial_easy": {
        "depth_range": (1, 2),
        "waves": [
            Wave(
                spawn_groups=[
                    SpawnGroup("buffer_leak", count=4, spawn_pattern="random", delay=0.0),
                ],
                trigger="on_start",
                trigger_value=0,
                announcement=None,
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("buffer_leak", count=3, spawn_pattern="behind_player", delay=0.0),
                ],
                trigger="on_kill_percent",
                trigger_value=0.75,  # spawns when 75% of wave 1 is dead
                announcement=None,
            ),
        ],
        # Total: 7 enemies across 2 waves
    },

    # Depth 3-4: Introduce wave pressure and mixed types.
    "early_mixed": {
        "depth_range": (3, 4),
        "waves": [
            Wave(
                spawn_groups=[
                    SpawnGroup("buffer_leak", count=4, spawn_pattern="surround", delay=0.0),
                    SpawnGroup("firewall", count=1, spawn_pattern="line_top", delay=0.5),
                ],
                trigger="on_start",
                trigger_value=0,
                announcement=None,
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("buffer_leak", count=3, spawn_pattern="behind_player", delay=0.0),
                    SpawnGroup("spammer", count=2, spawn_pattern="corners", delay=0.3),
                ],
                trigger="on_kill_percent",
                trigger_value=0.60,
                announcement=">>> INCOMING <<<",
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("firewall", count=2, spawn_pattern="pincer", delay=0.0),
                ],
                trigger="on_kill_percent",
                trigger_value=0.50,
                announcement=None,
            ),
        ],
        # Total: 12 enemies across 3 waves
    },

    # Depth 5-7: Full pressure. Ranged enemies force constant movement.
    "mid_pressure": {
        "depth_range": (5, 7),
        "waves": [
            Wave(
                spawn_groups=[
                    SpawnGroup("buffer_leak", count=5, spawn_pattern="surround", delay=0.0),
                    SpawnGroup("spammer", count=3, spawn_pattern="corners", delay=0.3),
                ],
                trigger="on_start",
                trigger_value=0,
                announcement=None,
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("overclocker", count=2, spawn_pattern="line_top", delay=0.0),
                    SpawnGroup("buffer_leak", count=4, spawn_pattern="behind_player", delay=0.5),
                ],
                trigger="on_kill_percent",
                trigger_value=0.50,
                announcement=">>> WAVE 2 <<<",
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("sniper", count=2, spawn_pattern="corners", delay=0.0),
                    SpawnGroup("spammer", count=2, spawn_pattern="random", delay=0.3),
                    SpawnGroup("buffer_leak", count=3, spawn_pattern="surround", delay=0.6),
                ],
                trigger="on_kill_percent",
                trigger_value=0.50,
                announcement=">>> WAVE 3 <<<",
            ),
        ],
        # Total: 21 enemies across 3 waves
    },

    # Depth 8-10: Intense. Timer-based waves create piling pressure.
    "late_intense": {
        "depth_range": (8, 10),
        "waves": [
            Wave(
                spawn_groups=[
                    SpawnGroup("buffer_leak", count=4, spawn_pattern="surround", delay=0.0),
                    SpawnGroup("spammer", count=3, spawn_pattern="line_top", delay=0.2),
                    SpawnGroup("sniper", count=2, spawn_pattern="corners", delay=0.5),
                ],
                trigger="on_start",
                trigger_value=0,
                announcement=None,
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("overclocker", count=3, spawn_pattern="pincer", delay=0.0),
                    SpawnGroup("worm", count=2, spawn_pattern="random", delay=0.3),
                ],
                trigger="on_timer",
                trigger_value=8.0,  # 8 seconds — wave comes regardless of kills
                announcement=">>> REINFORCEMENTS <<<",
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("daemon", count=3, spawn_pattern="surround", delay=0.0),
                    SpawnGroup("spammer", count=3, spawn_pattern="behind_player", delay=0.3),
                    SpawnGroup("buffer_leak", count=4, spawn_pattern="ring", delay=0.5),
                ],
                trigger="on_kill_percent",
                trigger_value=0.40,
                announcement=">>> FINAL WAVE <<<",
            ),
        ],
        # Total: 24 enemies across 3 waves
    },

    # Depth 11+: Chaos. 4 waves, timer pressure, elite enemies.
    "endgame_chaos": {
        "depth_range": (11, 99),
        "waves": [
            Wave(
                spawn_groups=[
                    SpawnGroup("spammer", count=4, spawn_pattern="corners", delay=0.0),
                    SpawnGroup("sniper", count=3, spawn_pattern="line_top", delay=0.2),
                    SpawnGroup("buffer_leak", count=5, spawn_pattern="surround", delay=0.3),
                ],
                trigger="on_start",
                trigger_value=0,
                announcement=None,
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("overclocker", count=3, spawn_pattern="pincer", delay=0.0),
                    SpawnGroup("trojan", count=2, spawn_pattern="random", delay=0.5),
                ],
                trigger="on_timer",
                trigger_value=6.0,
                announcement=">>> WAVE 2 <<<",
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("daemon", count=3, spawn_pattern="behind_player", delay=0.0),
                    SpawnGroup("worm", count=3, spawn_pattern="surround", delay=0.3),
                    SpawnGroup("spammer", count=3, spawn_pattern="line_bottom", delay=0.5),
                ],
                trigger="on_kill_percent",
                trigger_value=0.40,
                announcement=">>> WAVE 3 <<<",
            ),
            Wave(
                spawn_groups=[
                    SpawnGroup("firewall", count=2, spawn_pattern="pincer", delay=0.0),
                    SpawnGroup("sniper", count=2, spawn_pattern="corners", delay=0.0),
                    SpawnGroup("buffer_leak", count=6, spawn_pattern="ring", delay=0.3),
                ],
                trigger="on_timer",
                trigger_value=5.0,
                announcement=">>> FINAL WAVE <<<",
            ),
        ],
        # Total: 36 enemies across 4 waves
    },
}
```

#### ROOM TEMPLATE SELECTION

- At each depth, pick a random template from those matching the depth range.
- Create multiple templates per depth range (at least 3 each) for variety. The above are starter templates — duplicate and vary enemy compositions.
- Scale enemy HP by `1.05×` per depth past 10 (compounding). Do NOT scale enemy count infinitely — cap at ~36 per room. Instead, scale difficulty through enemy types and HP.

---

### 3. NEW RANGED ENEMY TYPES

The game currently has no enemies that attack from distance. This is the #1 reason combat feels passive. Add two dedicated ranged enemies:

#### THE SPAMMER (`!`) — Ranged Fodder

**Concept:** Fires slow projectiles at the player at regular intervals. Low threat individually, but in groups of 3-5, the overlapping projectile patterns create a "bullet curtain" the player must weave through.

**Visual:** `!` in bright yellow. Pulses brighter for 0.3s before each shot (telegraph). Projectiles are `·` in yellow, moving at 0.5 cells/frame.

**Components:** `Position`, `Velocity`, `Health(hp=2)`, `Renderable`, `AIBehavior(type='spammer')`, `CollisionBox`, `SyntaxDrop(verb='RECURSIVE')`, `RangedAttack(cooldown=2.0, projectile_speed=0.5, projectile_damage=1, telegraph_time=0.3)`

**AI State Machine:**
- `reposition` → Moves to maintain distance of 10–15 tiles from the player. Strafes laterally (perpendicular to player direction) to avoid being easy to rush. Movement speed: 0.3 cells/frame (slow).
- `fire` (every 2.0 seconds) → Stops moving. Pulses bright for 0.3s (telegraph). Fires a single `·` projectile aimed at the player's CURRENT position (not predictive — player can dodge after the telegraph).
- `flee` (player within 5 tiles) → Turns and runs directly away from player at 0.5 cells/frame. Prioritizes opening distance over shooting. This makes them annoying — you have to chase them.

**Projectile behavior:** Yellow `·` travels in a straight line at 0.5 cells/frame. Deals 1 damage on contact with player. Destroyed on contact with walls. Fades out after traveling 25 tiles. Leaves a very brief yellow Braille trail (2 frames).

**Death Animation:** `!` splits into 3 yellow Braille sparks that scatter outward.

**Why this enemy matters:** 3 Spammers at different positions create crossing projectile patterns. The player can't stand still — they must weave between shots OR rush a Spammer to kill it and reduce pressure. This is the exact dynamic Hades creates with its ranged enemies.

---

#### THE SNIPER (`¦`) — Ranged Elite

**Concept:** Fires a fast, high-damage beam after a long, visible charge-up. The threat isn't the fire rate — it's the laser-like precision and the fact that you MUST react to the telegraph or take heavy damage.

**Visual:** `¦` in bright red. During charge-up, a dim red dotted line (`· · · ·`) extends from the Sniper to the player's current position, showing exactly where the shot will go. The line brightens over 1.5 seconds. When it fires, the dotted line becomes a solid bright red beam for 2 frames.

**Components:** `Position`, `Velocity`, `Health(hp=3)`, `Renderable`, `AIBehavior(type='sniper')`, `CollisionBox`, `SyntaxDrop(verb='DASH')`, `RangedAttack(cooldown=4.0, charge_time=1.5, projectile_speed=999, projectile_damage=3, telegraph_time=1.5)`

**AI State Machine:**
- `reposition` → Moves to the farthest open position from the player, preferring corners and edges. Movement speed: 0.25 cells/frame (very slow). Tries to maintain 15+ tile distance.
- `charge` (every 4.0 seconds) → Stops moving. Begins rendering the aim line from itself to the player. The aim line TRACKS the player for the first 1.0 seconds of the 1.5s charge. During the final 0.5 seconds, the aim line LOCKS to a fixed direction (the player's position at the lock moment). This is the dodge window.
- `fire` → Instant hitscan beam along the locked direction. Deals 3 damage to anything in the line. The beam renders as a full-width line of bright red `─` or `│` or `╱` `╲` characters (depending on angle) for 3 frames. Heavy screen shake on the Sniper's position.
- `cooldown` → 1.0 second of vulnerability after firing where the Sniper doesn't move or attack. Ideal rush window for the player.

**Why this enemy matters:** The 1.5-second telegraph with the visible aim line creates "oh shit" moments. The player sees the red line tracking them and must dash perpendicular to it in the final 0.5s. Meanwhile, melee enemies are still chasing. The Sniper forces the player to split attention between immediate melee threats and the incoming beam. This is exactly how Hades' Exalted enemies work — high-damage telegraphed attacks that you dodge while dealing with the crowd.

---

### 4. ENEMY AGGRESSION OVERHAUL

ALL existing enemies need their AI updated to be more aggressive. The current "chase player slowly" behavior is not enough.

#### UNIVERSAL AI CHANGES

**Activation range: INFINITE.** Remove any activation radius. Every enemy is active from the moment it spawns. No more "standing far away = safe." Enemies always know where the player is and always act on it.

**Engagement speed tiers:**

```python
ENEMY_AGGRESSION = {
    "buffer_leak": {
        "chase_speed": 0.5,        # cells/frame (was ~0.3, increase significantly)
        "chase_behavior": "direct",  # beelines toward player
        "attack_on_contact": True,
        "attacks_per_contact": 1,
        "contact_damage": 1,
        "lunge_on_close": True,     # NEW: when within 4 tiles, burst to 0.8 speed for 0.5s
    },
    "firewall": {
        "chase_speed": 0.25,
        "chase_behavior": "intercept",  # moves to cut off player's path, not just chase
        "attack_on_contact": True,
        "contact_damage": 2,
        "shield_bash_range": 3,     # NEW: when player is within 3 tiles of FRONT, charge forward 0.6 speed for 0.3s
        "shield_bash_knockback": 2.0,
        "shield_bash_cooldown": 3.0,
    },
    "overclocker": {
        "chase_speed": 0.3,
        "chase_behavior": "orbit",   # circles at range 6-8, looking for charge angle
        "charge_speed": 2.0,
        "charge_telegraph": 0.8,     # seconds of red glow before charge (was 1.0, shorten)
        "charge_cooldown": 3.0,      # was longer, shorten for more aggression
        "charge_damage": 2,
    },
    "worm": {
        "chase_speed": 0.4,
        "chase_behavior": "sine_toward_player",  # sine wave but TOWARD player, not random wander
        "trail_drop_interval": 3,    # frames (was 4, more frequent trail)
        "trail_max_length": 20,      # was 15, longer trails
    },
    "daemon": {
        "stalk_speed": 0.35,         # was 0.3, slightly faster
        "reveal_speed": 0.7,         # was 0.6, faster lunge
        "reveal_range": 5,           # was 4, reveals slightly earlier
        "re_stalk_distance": 10,     # was 12, re-engages sooner
    },
    "trojan": {
        "assault_speed": 0.8,        # was 0.7, faster
        "assault_damage": 3,
        "trigger_range": 4,          # was 3, triggers slightly earlier
    },
    "spammer": {
        "fire_cooldown": 2.0,
        "flee_speed": 0.5,
        "strafe_speed": 0.3,
        "preferred_range": 12,
    },
    "sniper": {
        "fire_cooldown": 4.0,
        "charge_time": 1.5,
        "lock_time": 0.5,           # last 0.5s of charge is locked (dodge window)
        "preferred_range": 18,
        "beam_damage": 3,
    },
}
```

#### SPECIFIC AI IMPROVEMENTS

**Buffer-Leak `&` — Add lunge attack:**
- When within 4 tiles of the player, the Buffer-Leak performs a quick lunge — burst speed to 0.8 cells/frame for 0.5 seconds directly at the player.
- After lunging (hit or miss), the Buffer-Leak pauses for 0.3 seconds before resuming normal chase.
- Visual: during lunge, the `&` character trails 2 dim afterimages (like a mini-dash).

**Firewall `[H]` — Add shield bash:**
- When the player is within 3 tiles of the Firewall's FRONT face, the Firewall charges forward at 0.6 cells/frame for 0.3 seconds.
- Shield bash deals 2 damage and heavy knockback (2.0 force).
- 3-second cooldown between bashes.
- Visual: the `[H]` flashes bright white during the bash, with a forward-pushing Braille particle burst.
- The Firewall now also uses **intercept pathfinding**: instead of moving directly toward the player, it calculates where the player is HEADING (based on velocity) and moves to cut them off. This makes Firewalls feel intelligent and threatening rather than lumbering obstacles you run circles around.

**Overclocker `>>` — Shorter telegraph, orbit behavior:**
- Reduce charge telegraph from 1.0s to 0.8s. Still dodgeable but more threatening.
- Change idle behavior from "chase" to "orbit": the Overclocker circles the player at 6–8 tile radius, looking for a clear charge line. This means it's always nearby, always threatening, rather than slowly walking toward you.
- After a charge (hit or miss), the Overclocker immediately repositions to orbiting distance rather than stopping.
- Reduce charge cooldown to 3.0 seconds.

**Worm `~` — Move toward player:**
- Change wander behavior: the sine wave should be TOWARD the player, not random. The worm takes a sine-wave path in the general direction of the player, so it's unpredictable but still pursuing.
- Increase trail drop frequency and length. The arena should get dangerous FAST.

---

### 5. ENEMY PROJECTILE SYSTEM

Enemy projectiles need to be proper ECS entities, just like player projectiles. They share the same collision and rendering systems but are tagged as hostile.

```python
@dataclass
class EnemyProjectile:
    damage: float
    owner_id: int        # entity ID of the enemy that fired it
    speed: float
    lifetime: float      # seconds before auto-destroy
    visual: str          # character to render
    color: tuple         # TrueColor RGB
    trail_length: int    # number of fading trail frames (0 = no trail)
```

**Collision rules:**
- Enemy projectiles damage the player but NOT other enemies.
- Enemy projectiles are destroyed on contact with the player or walls.
- Player dash grants i-frames that also apply to projectile collision — dashing THROUGH a projectile is a valid dodge.
- Enemy projectiles should be destroyable by player attacks (slash/projectile hitting an enemy projectile destroys it). This adds a skill ceiling — skilled players can cut through bullet patterns.

**Projectile rendering:**
- Enemy projectiles render in their designated color with a brief Braille trail.
- When destroyed by a player attack, they pop into 3–4 tiny Braille sparks.
- When hitting the player, brief red flash at impact point.

---

### 6. ENCOUNTER PACING

The "rhythm" of a Hades room:

```
0.0s  - Room starts. Spawn telegraphs appear. Player sees where enemies are coming from.
0.5s  - Wave 1 spawns. Immediate pressure — ranged enemies start shooting, melee enemies charge.
1-5s  - Player is fighting Wave 1. Dodging Spammer projectiles while slashing Buffer-Leaks.
~6s   - 50-60% of Wave 1 dead. Wave 2 triggers. New spawn telegraphs appear.
6.5s  - Wave 2 spawns BEHIND the player and from SIDES. Player must reposition.
7-15s - Peak chaos. Wave 1 survivors + Wave 2 all active. Sniper aim lines appear. Overclocker charges.
~16s  - 40% of total enemies remain. Wave 3 triggers (if applicable). Final push.
16-25s - Cleanup. Player hunts remaining enemies. Tension decreases.
25-30s - Room cleared. Reward screen.
```

**Key timing principles:**
- Wave 2 should trigger BEFORE Wave 1 is fully cleared. Overlap is essential.
- Timer-based waves (late game) create urgency — if the player is too cautious, more enemies pile on.
- The "behind_player" spawn pattern should be used in at least one wave per room after Depth 3. Never let the player feel safe facing one direction.

---

### 7. SCREEN DENSITY TARGETS

At any given moment during peak combat, the screen should contain:

- **8–15 active enemies** (across current wave survivors + new wave)
- **3–8 enemy projectiles** in flight (from Spammers and Snipers)
- **10–20 particles** (hit sparks, dash trails, death bursts)
- **1–3 telegraphs** active (Sniper aim lines, Overclocker charge glow, spawn location markers)

This is the "visual noise" level that makes combat feel alive. Test by pausing mid-fight and counting entities. If you see fewer than 8 enemies + 3 projectiles, the room is too empty.

#### PERFORMANCE BUDGET

With 15 enemies + 8 projectiles + 20 particles + 3 telegraphs = ~46 entities needing position updates and rendering per frame at 60 FPS. This is achievable but requires:

- **Spatial hashing** for collision detection (do NOT check all entity pairs — only nearby ones).
- **Object pooling** for projectiles and particles (do NOT allocate/deallocate every frame).
- **Dirty-rect rendering** in the double buffer (only update cells that changed).

Add an FPS counter (toggle `F1`) and a live entity count display (toggle `F6`) for performance monitoring.

---

### 8. ENEMY HEALTH SCALING FOR HACK-AND-SLASH FEEL

Enemies should die FAST. The satisfaction of hack-and-slash comes from cleaving through hordes, not chipping away at health bars. Reduce HP across the board for fodder enemies:

```python
ENEMY_HP_REVISED = {
    "buffer_leak": 1,    # dies in one hit from anything. Pure fodder. Satisfying to mow down.
    "spammer": 2,        # two hits. Fragile but requires closing distance.
    "overclocker": 2,    # glass cannon. Dangerous charge but shatters fast.
    "worm": 3,           # slightly tanky because of area denial value.
    "daemon": 2,         # squishy but hard to find/hit.
    "sniper": 3,         # needs to survive long enough to fire at least once.
    "firewall": 6,       # the tank. Takes sustained effort. Compensated by being slow.
    "trojan": 5,         # tanky reward enemy. High risk to engage.
}
```

**The math of satisfaction:** If the player has a weapon that deals 2 damage and attacks every 0.25 seconds, they kill a Buffer-Leak every 0.25 seconds. In a swarm of 6 Buffer-Leaks, that's 1.5 seconds of continuous slashing to clear them all. Each kill has a particle burst. Six bursts in 1.5 seconds = the screen EXPLODES. That's the feeling.

**Depth scaling:** After Depth 10, enemy HP scales by `1.08×` per depth (compounding). This is slow enough that the player's damage upgrades outpace it until Depth 15+, where it starts to bite. Never let fodder enemies become spongy — if Buffer-Leaks take 3+ hits at any point, something is wrong.

---

### 9. SCREEN SHAKE & HIT FEEDBACK SCALING

More enemies = more kills = more feedback. Scale the "juice" to match the density:

- **Single kill:** Small particle burst (5 particles). No screen shake.
- **2 kills within 0.5s:** Medium burst (8 particles). Tiny screen shake (±0.5 cells, 1 frame).
- **3+ kills within 0.5s:** Large burst (12 particles per kill). Screen shake (±1 cell, 2 frames). Brief white flash on entire screen border (1 frame).
- **5+ kills within 0.5s (Logic Blast or area weapon):** Massive burst. Heavy screen shake (±2 cells, 4 frames). Screen border flashes white. All text on screen jitters for 2 frames. The terminal itself feels like it's struggling to contain the carnage.

Track a `kill_streak_timer` that resets 0.5 seconds after the last kill. Use the count to scale feedback.

---

### 10. IMPLEMENTATION DETAILS

#### New Components

```python
@dataclass
class RangedAttack:
    cooldown: float              # seconds between attacks
    cooldown_timer: float = 0.0  # current timer
    charge_time: float = 0.0     # seconds of visible charge-up before firing
    charge_timer: float = 0.0
    is_charging: bool = False
    projectile_speed: float = 0.5
    projectile_damage: float = 1
    projectile_visual: str = "·"
    projectile_color: tuple = (255, 255, 0)
    telegraph_time: float = 0.3  # visual warning before shot
    aim_lock_time: float = 0.0   # for Sniper: last N seconds of charge lock direction

@dataclass
class LungeAttack:
    lunge_range: float = 4.0     # distance at which lunge triggers
    lunge_speed: float = 0.8     # cells/frame during lunge
    lunge_duration: float = 0.5  # seconds
    lunge_cooldown: float = 1.5  # seconds between lunges
    lunge_timer: float = 0.0
    is_lunging: bool = False
    recovery_time: float = 0.3   # pause after lunge

@dataclass
class ShieldBash:
    bash_range: float = 3.0
    bash_speed: float = 0.6
    bash_duration: float = 0.3
    bash_knockback: float = 2.0
    bash_damage: float = 2
    bash_cooldown: float = 3.0
    bash_timer: float = 0.0

@dataclass
class EnemyProjectile:
    damage: float
    owner_id: int
    speed: float
    lifetime: float
    visual: str
    color: tuple
    trail_length: int = 2

@dataclass
class KillStreak:
    count: int = 0
    timer: float = 0.0          # resets on each kill, expires after 0.5s
```

#### New/Modified Files

```
signal_void/
├── wave_spawner.py       # NEW — Wave system, spawn patterns, room templates, spawn animations
├── enemy_projectiles.py  # NEW — Enemy projectile system (spawn, move, collide, render)
├── enemies.py            # MODIFY — Add Spammer and Sniper. Update all enemy AI for aggression.
├── components.py         # MODIFY — Add RangedAttack, LungeAttack, ShieldBash, EnemyProjectile, KillStreak
├── systems.py            # MODIFY — Add ranged_attack_system, lunge_system, shield_bash_system, kill_streak_system
├── collision.py          # MODIFY — Add spatial hashing. Add enemy projectile vs player collision.
├── engine.py             # MODIFY — Add object pooling for projectiles and particles.
├── particles.py          # MODIFY — Scale particle bursts based on kill streak count.
├── rooms.py              # MODIFY — Replace flat enemy spawn with wave_spawner integration.
└── spawner.py            # MODIFY — Integrate with wave system instead of flat spawn counts.
```

---

### 11. BUILD ORDER

- ~~**Phase A:** Wave spawning system — RoomWaves, Wave, SpawnGroup dataclasses. Spawn pattern implementations (surround, corners, behind_player, etc.). Spawn telegraph animation. Replace existing flat spawn logic.~~ ✅ DONE

- ~~**Phase B:** Enemy aggression overhaul — Update ALL existing enemy AI. Buffer-Leak lunge, Firewall intercept pathfinding + shield bash, Overclocker orbit + shorter telegraph. Infinite activation range.~~ ✅ DONE

- ~~**Phase C:** Spammer enemy — `!` ranged fodder with projectile firing, telegraph pulse, strafe/flee behavior. Enemy projectile entity system.~~ ✅ DONE

- ~~**Phase D:** Sniper enemy — `¦` with charge-up aim line, tracking phase, lock phase, hitscan beam.~~ ✅ DONE

- ~~**Phase E:** Room templates — All 5 template tiers with spammers and snipers integrated. 3 templates per tier (15 total).~~ ✅ DONE

- ~~**Phase F:** Kill streak feedback scaling — Track multi-kills within 0.5s window. Scale particle bursts and screen shake based on streak count. Streak indicator text.~~ ✅ DONE

- ~~**Phase G:** Performance optimization — Entity count display (F6 toggle). Dirty-rect rendering already in double buffer.~~ ✅ DONE

---

### 12. CONSTRAINTS REMINDER

- All enemies must be aggressive from spawn. No activation radius. No "idle until player approaches."
- Enemy projectiles are ECS entities — same rendering and collision pipeline as player projectiles.
- Spawn telegraphs (red `×` markers) are mandatory — no enemies appearing without warning.
- 0.2s spawn invulnerability prevents area-attack spawn killing.
- Player attacks can destroy enemy projectiles (adds skill ceiling).
- Player dash i-frames protect against enemy projectiles (dash THROUGH bullets).
- Minimum 2 waves per room. Waves overlap — Wave 2 triggers before Wave 1 is fully cleared.
- At least one "behind_player" spawn pattern per room after Depth 3.
- Buffer-Leaks must die in 1 hit at base damage. Fodder should feel like fodder.
- Debug key (`F7`): spawn a full endgame_chaos room instantly for stress testing.
- Clean terminal restoration on exit regardless of game state.

**Begin with Phase A: Wave Spawning System.**