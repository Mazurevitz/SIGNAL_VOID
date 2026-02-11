"""
Component Definitions
======================
All components are plain dataclasses with no behavior.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable
from enum import Enum, auto


# =============================================================================
# PHYSICS COMPONENTS
# =============================================================================

@dataclass
class Position:
    """World position with sub-cell precision."""
    x: float = 0.0
    y: float = 0.0


@dataclass
class Velocity:
    """Movement velocity in cells per frame."""
    x: float = 0.0
    y: float = 0.0


@dataclass
class Friction:
    """Friction multiplier applied to velocity each frame."""
    value: float = 0.85


@dataclass
class MaxSpeed:
    """Maximum speed cap in cells per frame."""
    value: float = 0.8


@dataclass
class Knockback:
    """Current knockback force being applied."""
    x: float = 0.0
    y: float = 0.0
    decay: float = 0.7  # Multiplier per frame


@dataclass
class CollisionBox:
    """Axis-aligned bounding box for collision detection."""
    width: float = 1.0
    height: float = 1.0
    offset_x: float = 0.0  # Offset from Position
    offset_y: float = 0.0
    solid: bool = True  # Blocks movement
    trigger: bool = False  # Triggers events but doesn't block


# =============================================================================
# RENDERING COMPONENTS
# =============================================================================

@dataclass
class Renderable:
    """Visual representation of an entity."""
    char: str = '?'
    color: int = 7  # ANSI 256 color
    bg_color: int = -1  # -1 = transparent
    layer: int = 0  # Higher layers render on top
    visible: bool = True


@dataclass
class GhostTrail:
    """Configuration for dash ghost trails."""
    enabled: bool = False
    positions: List[Tuple[float, float]] = field(default_factory=list)
    max_echoes: int = 5
    colors: List[int] = field(default_factory=lambda: [255, 252, 245, 238, 235])


@dataclass
class AnimationState:
    """Current animation state for animated entities."""
    frames: List[str] = field(default_factory=lambda: ['?'])
    current_frame: int = 0
    frame_duration: int = 10  # Frames per animation frame
    frame_timer: int = 0
    looping: bool = True


# =============================================================================
# COMBAT COMPONENTS
# =============================================================================

@dataclass
class Health:
    """Entity health pool."""
    current: int = 100
    maximum: int = 100


@dataclass
class Shield:
    """Directional shield that blocks damage from a direction."""
    direction: str = 'front'  # 'front', 'back', 'left', 'right', 'all'
    active: bool = True
    blocks_damage: bool = True
    causes_knockback: bool = True
    knockback_force: float = 1.2


@dataclass
class Damage:
    """Damage dealt on collision."""
    amount: int = 10
    knockback_force: float = 0.5


@dataclass
class Invulnerable:
    """Temporary invulnerability frames."""
    frames_remaining: int = 0


@dataclass
class HitFlash:
    """Visual flash when hit."""
    frames_remaining: int = 0
    flash_color: int = 255  # White


@dataclass
class Stunned:
    """Temporary stun — AI frozen."""
    frames_remaining: int = 0


# =============================================================================
# PLAYER COMPONENTS
# =============================================================================

@dataclass
class PlayerControlled:
    """Marks an entity as player-controlled."""
    acceleration: float = 0.15
    last_move_dir_x: float = 1.0
    last_move_dir_y: float = 0.0


@dataclass
class DashState:
    """Dash ability state."""
    speed: float = 2.5
    duration: int = 8  # Frames
    cooldown: int = 30  # Frames
    frames_remaining: int = 0
    cooldown_remaining: int = 0
    direction_x: float = 0.0
    direction_y: float = 0.0


@dataclass
class AttackState:
    """Melee attack state."""
    active: bool = False
    frames_remaining: int = 0
    direction_x: float = 0.0
    direction_y: float = 0.0
    radius: float = 3.0
    is_beam: bool = False
    beam_range: float = 0.0
    beam_continuous_frames: int = 0


@dataclass
class AttackMultiplier:
    """Temporary attack modifier from verb effects."""
    damage_multiplier: float = 1.0
    hits: int = 1  # Number of times damage is applied (RECURSIVE = 2)
    uses_remaining: int = 1  # Consumed after N attacks (0 = permanent until timer)
    frames_remaining: int = 0  # Time-based expiry (0 = use-based only)


# =============================================================================
# AI COMPONENTS
# =============================================================================

class AIState(Enum):
    """AI state machine states."""
    IDLE = auto()
    DETECT = auto()
    CHASE = auto()
    ATTACK = auto()
    CHARGE = auto()
    RECOVER = auto()
    FLEE = auto()


@dataclass
class AIBehavior:
    """AI behavior configuration and state."""
    state: AIState = AIState.IDLE
    detection_range: float = 15.0
    attack_range: float = 2.0
    move_speed: float = 0.3
    state_timer: int = 0
    target_entity: Optional[int] = None
    behavior_type: str = 'chase'  # 'chase', 'patrol', 'charge', 'guard'
    facing_x: float = 1.0  # Direction entity is facing (for shields, attacks)
    facing_y: float = 0.0
    turn_speed: float = 0.0  # 0 = instant, >0 = radians per frame


@dataclass
class ChargeAttack:
    """Charge attack behavior (for Overclocker)."""
    charge_time: int = 60  # Frames to charge
    charge_timer: int = 0
    charging: bool = False
    charge_speed: float = 2.0
    trail_damage: int = 5


# =============================================================================
# SYNTAX CHAIN COMPONENTS
# =============================================================================

@dataclass
class SyntaxDrop:
    """Verb dropped when this entity is killed."""
    verb: str = 'NULL'
    drop_condition: str = 'kill'  # 'kill', 'backstab', 'dodge'


@dataclass
class SyntaxBuffer:
    """Player's syntax chain buffer."""
    verbs: List[str] = field(default_factory=list)
    max_verbs: int = 3


@dataclass
class WeaponComponent:
    """A single weapon instance."""
    weapon_type: str = 'slash'
    base_type: str = 'slash'
    is_evolved: bool = False
    mods: list = field(default_factory=list)
    mod_slots: int = 2
    attack_timer: int = 0
    hit_counter: int = 0
    attack_counter: int = 0


@dataclass
class WeaponInventory:
    """Player weapon inventory (max 2 weapons, swap with TAB)."""
    weapons: List = field(default_factory=list)
    active_index: int = 0


@dataclass
class PlayerStats:
    """Persistent run stats modified by micro-upgrades."""
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
    invincibility_frames: int = 45
    verb_drop_rate: float = 0.0
    heal_bonus: float = 0.0
    upgrade_counts: dict = field(default_factory=dict)


# =============================================================================
# EFFECT COMPONENTS
# =============================================================================

@dataclass
class ScreenShake:
    """Screen shake effect."""
    intensity: int = 2
    frames_remaining: int = 0


@dataclass
class HitStop:
    """Hit-stop freeze effect."""
    frames_remaining: int = 0


@dataclass
class Lifetime:
    """Entity lifetime in frames (for particles, projectiles)."""
    frames_remaining: int = 30


@dataclass
class ParticleEmitter:
    """Emits particles over time."""
    emission_rate: float = 1.0  # Particles per frame
    accumulator: float = 0.0
    particle_char: str = '.'
    particle_color: int = 255
    particle_lifetime: int = 20
    velocity_min: Tuple[float, float] = (-0.5, -0.5)
    velocity_max: Tuple[float, float] = (0.5, 0.5)
    gravity: float = 0.1
    active: bool = True


@dataclass
class Gravity:
    """Gravity applied to velocity."""
    strength: float = 0.1


# =============================================================================
# TAG COMPONENTS (empty, used for queries)
# =============================================================================

@dataclass
class PlayerTag:
    """Marks the player entity."""
    pass


@dataclass
class EnemyTag:
    """Marks an enemy entity."""
    enemy_type: str = 'generic'


@dataclass
class ParticleTag:
    """Marks a particle entity."""
    pass


@dataclass
class ProjectileTag:
    """Marks a projectile entity."""
    pass


@dataclass
class Projectile:
    """Projectile flight data."""
    damage: int = 35
    knockback: float = 0.6
    owner_id: int = -1
    max_range: float = 30.0
    distance_traveled: float = 0.0
    weapon_color: int = 255
    piercing: bool = False
    stun_frames: int = 0
    hit_entities: list = field(default_factory=list)


@dataclass
class WallTag:
    """Marks a wall/boundary entity."""
    pass


@dataclass
class SpawnTelegraph:
    """Spawn telegraph marker. Counts down then spawns an enemy."""
    enemy_type: str = 'buffer_leak'
    frames_remaining: int = 30  # 0.5 seconds at 60 FPS
    total_frames: int = 30
    depth: int = 1


@dataclass
class EnemyProjectileTag:
    """Marks an enemy projectile entity."""
    damage: float = 1
    owner_id: int = -1
    speed: float = 0.5
    visual: str = '\u00b7'
    trail_length: int = 2


@dataclass
class RangedAttack:
    """Ranged attack capability for enemies."""
    cooldown: float = 2.0
    cooldown_timer: float = 0.0
    charge_time: float = 0.0
    charge_timer: float = 0.0
    is_charging: bool = False
    projectile_speed: float = 0.5
    projectile_damage: float = 1
    projectile_visual: str = '\u00b7'
    projectile_color: tuple = (255, 255, 0)
    telegraph_time: float = 0.3
    aim_lock_time: float = 0.0
    aim_dir_x: float = 0.0
    aim_dir_y: float = 0.0


@dataclass
class SniperState:
    """Sniper charge/lock/fire state machine."""
    phase: str = 'idle'  # idle, tracking, locked, firing, cooldown
    charge_timer: float = 0.0
    charge_duration: float = 1.5  # total charge time
    lock_time: float = 0.5  # last N seconds of charge lock direction
    fire_frames: int = 0  # frames beam is visible
    fire_duration: int = 4  # how many frames beam shows
    cooldown_timer: float = 0.0
    cooldown_duration: float = 1.0  # vulnerability window after firing
    fire_cooldown: float = 4.0  # time between shots
    fire_cooldown_timer: float = 2.0  # stagger initial shot
    aim_x: float = 0.0
    aim_y: float = 0.0
    beam_damage: int = 3
