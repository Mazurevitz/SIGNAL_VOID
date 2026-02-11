"""
ECS Systems
============
Functions that operate on entities with matching components.
Each system queries the World for entities with required components
and updates them.
"""

from typing import Tuple, Optional, List
import math
import random

from .ecs import World
from .components import (
    Position, Velocity, Friction, MaxSpeed, Knockback,
    Renderable, GhostTrail, AnimationState, HitFlash,
    CollisionBox, PlayerTag, EnemyTag, WallTag,
    Lifetime, Gravity, ParticleTag, ProjectileTag,
    DashState, PlayerControlled, AttackState, AttackMultiplier,
    AIBehavior, AIState, Health, Damage, Invulnerable,
    SyntaxDrop, SyntaxBuffer, Shield, ChargeAttack,
    PlayerStats, WeaponInventory, Stunned,
    RangedAttack, SniperState
)
from .engine import (
    GameRenderer,
    NEON_CYAN, NEON_MAGENTA, NEON_YELLOW, NEON_RED, NEON_GREEN,
    GRAY_DARK, GRAY_MED, GRAY_DARKER, WHITE
)


# =============================================================================
# PHYSICS SYSTEMS
# =============================================================================

def movement_system(world: World, dt: float = 1.0):
    """
    Update positions based on velocities.
    Applies friction, max-speed clamping, and knockback decay.
    """
    # Find player stats once for speed multiplier
    player_stats = None
    player_eid = None
    for eid, _, _ in world.query(PlayerTag, PlayerStats):
        player_eid = eid
        player_stats = world.get_component(eid, PlayerStats)
        break

    for entity_id, pos, vel in world.query(Position, Velocity):
        # Apply knockback if present
        knockback = world.get_component(entity_id, Knockback)
        if knockback:
            vel.x += knockback.x
            vel.y += knockback.y
            knockback.x *= knockback.decay
            knockback.y *= knockback.decay
            if abs(knockback.x) < 0.01 and abs(knockback.y) < 0.01:
                world.remove_component(entity_id, Knockback)

        # Apply friction (dampen velocity each frame)
        friction = world.get_component(entity_id, Friction)
        if friction:
            vel.x *= friction.value
            vel.y *= friction.value

        # Clamp to max speed (apply move speed multiplier for player)
        max_speed = world.get_component(entity_id, MaxSpeed)
        if max_speed:
            effective_max = max_speed.value
            if entity_id == player_eid and player_stats:
                effective_max *= player_stats.move_speed_multiplier
            speed = math.sqrt(vel.x * vel.x + vel.y * vel.y)
            if speed > effective_max:
                scale = effective_max / speed
                vel.x *= scale
                vel.y *= scale

        # Integrate position
        pos.x += vel.x * dt
        pos.y += vel.y * dt

        # Kill negligible velocity to prevent drift
        if abs(vel.x) < 0.005:
            vel.x = 0.0
        if abs(vel.y) < 0.005:
            vel.y = 0.0


def gravity_system(world: World):
    """Apply downward gravity to entities with Gravity component."""
    for entity_id, vel, grav in world.query(Velocity, Gravity):
        vel.y += grav.strength


def boundary_system(world: World, width: int, height: int, margin: int = 1) -> List[Tuple[int, float]]:
    """
    Clamp entities within the play area.

    Returns a list of (entity_id, impact_speed) for entities that
    hit a wall with significant velocity. Used to trigger effects.
    """
    wall_hits = []

    for entity_id, pos, vel in world.query(Position, Velocity):
        # Particles can leave the play area
        if world.has_component(entity_id, ParticleTag):
            continue

        # Projectiles handle their own boundary destruction
        if world.has_component(entity_id, ProjectileTag):
            continue

        hit = False
        impact_speed = 0.0

        if pos.x < margin:
            impact_speed = max(impact_speed, abs(vel.x))
            pos.x = float(margin)
            vel.x = 0.0
            hit = True
        elif pos.x > width - margin - 1:
            impact_speed = max(impact_speed, abs(vel.x))
            pos.x = float(width - margin - 1)
            vel.x = 0.0
            hit = True

        if pos.y < margin:
            impact_speed = max(impact_speed, abs(vel.y))
            pos.y = float(margin)
            vel.y = 0.0
            hit = True
        elif pos.y > height - margin - 1:
            impact_speed = max(impact_speed, abs(vel.y))
            pos.y = float(height - margin - 1)
            vel.y = 0.0
            hit = True

        if hit and impact_speed > 0.3:
            wall_hits.append((entity_id, impact_speed))

    return wall_hits


# =============================================================================
# LIFETIME & ANIMATION
# =============================================================================

def lifetime_system(world: World):
    """Decrement lifetimes and destroy expired entities."""
    for entity_id, lifetime in world.query(Lifetime):
        lifetime.frames_remaining -= 1
        if lifetime.frames_remaining <= 0:
            world.destroy_entity(entity_id)


def animation_system(world: World):
    """Advance animation frames for animated entities."""
    for entity_id, rend, anim in world.query(Renderable, AnimationState):
        anim.frame_timer += 1
        if anim.frame_timer >= anim.frame_duration:
            anim.frame_timer = 0
            anim.current_frame += 1
            if anim.current_frame >= len(anim.frames):
                if anim.looping:
                    anim.current_frame = 0
                else:
                    anim.current_frame = len(anim.frames) - 1
            rend.char = anim.frames[anim.current_frame]


def hit_flash_system(world: World):
    """
    Tick hit-flash timers and swap entity colors.

    When a flash starts, the original color is stashed. When it
    ends, the original color is restored.
    """
    for entity_id, rend, flash in world.query(Renderable, HitFlash):
        if flash.frames_remaining > 0:
            flash.frames_remaining -= 1
            if not hasattr(flash, '_original_color'):
                flash._original_color = rend.color
            rend.color = flash.flash_color
        elif hasattr(flash, '_original_color'):
            rend.color = flash._original_color
            delattr(flash, '_original_color')


# =============================================================================
# PLAYER SYSTEMS
# =============================================================================

def dash_system(world: World):
    """
    Process active dashes: apply dash velocity overriding normal movement,
    and tick down cooldowns.
    """
    for entity_id, pos, vel, dash, ctrl in world.query(
        Position, Velocity, DashState, PlayerControlled
    ):
        if dash.cooldown_remaining > 0:
            dash.cooldown_remaining -= 1

        if dash.frames_remaining > 0:
            dash.frames_remaining -= 1
            vel.x = dash.direction_x * dash.speed
            vel.y = dash.direction_y * dash.speed


def ghost_trail_system(world: World):
    """
    Record positions for dash ghost trails.

    Called BEFORE movement so echoes trail behind the player.
    When not dashing, trails fade out one echo per frame.
    """
    for entity_id, pos, trail, dash in world.query(Position, GhostTrail, DashState):
        if dash.frames_remaining > 0:
            trail.enabled = True
            trail.positions.append((pos.x, pos.y))
            while len(trail.positions) > trail.max_echoes:
                trail.positions.pop(0)
        else:
            trail.enabled = False
            if trail.positions:
                trail.positions.pop(0)


# =============================================================================
# AI SYSTEM
# =============================================================================

def ai_system(world: World):
    """
    Run AI state machines for all enemies.

    State machine: idle → detect → chase → attack → recover → idle
    Each behavior_type has different logic in the chase/attack phases.
    """
    # Find the player once for all AI queries
    player_pos = None
    player_id = None
    for eid, pos, _ in world.query(Position, PlayerTag):
        player_pos = pos
        player_id = eid
        break

    if player_pos is None:
        return

    for entity_id, pos, vel, ai, _ in world.query(
        Position, Velocity, AIBehavior, EnemyTag
    ):
        # Stun check: freeze AI while stunned
        stun = world.get_component(entity_id, Stunned)
        if stun and stun.frames_remaining > 0:
            stun.frames_remaining -= 1
            vel.x *= 0.5
            vel.y *= 0.5
            continue

        ai.target_entity = player_id
        dist = get_distance(pos, player_pos)
        dir_x, dir_y = get_direction_to(pos, player_pos)

        # Update facing direction toward player
        # Skip if shield-stunned (staggered after blocking)
        if hasattr(ai, '_shield_stun') and ai._shield_stun > 0:
            ai._shield_stun -= 1
        elif abs(dir_x) > 0.1 or abs(dir_y) > 0.1:
            if ai.turn_speed > 0:
                # Constant angular turn rate (radians/frame)
                current_angle = math.atan2(ai.facing_y, ai.facing_x)
                target_angle = math.atan2(dir_y, dir_x)
                diff = target_angle - current_angle
                # Shortest arc
                while diff > math.pi: diff -= 2 * math.pi
                while diff < -math.pi: diff += 2 * math.pi
                if abs(diff) <= ai.turn_speed:
                    ai.facing_x = dir_x
                    ai.facing_y = dir_y
                else:
                    sign = 1 if diff > 0 else -1
                    new_angle = current_angle + sign * ai.turn_speed
                    ai.facing_x = math.cos(new_angle)
                    ai.facing_y = math.sin(new_angle)
            else:
                ai.facing_x = dir_x
                ai.facing_y = dir_y

        ai.state_timer += 1

        # Route to behavior-specific handlers
        if ai.behavior_type == 'chase':
            _ai_chase_behavior(world, entity_id, pos, vel, ai, dist, dir_x, dir_y)
        elif ai.behavior_type == 'guard':
            _ai_guard_behavior(world, entity_id, pos, vel, ai, dist, dir_x, dir_y)
        elif ai.behavior_type == 'charge':
            _ai_charge_behavior(world, entity_id, pos, vel, ai, dist, dir_x, dir_y, player_pos)
        elif ai.behavior_type == 'spammer':
            _ai_spammer_behavior(world, entity_id, pos, vel, ai, dist, dir_x, dir_y, player_pos)
        elif ai.behavior_type == 'sniper':
            _ai_sniper_behavior(world, entity_id, pos, vel, ai, dist, dir_x, dir_y, player_pos)


# =============================================================================
# CHASE BEHAVIOR (Buffer-Leak)
# =============================================================================

def _ai_chase_behavior(world: World, entity_id: int, pos: Position,
                       vel: Velocity, ai: AIBehavior, dist: float,
                       dir_x: float, dir_y: float):
    """Chase behavior with lunge: chase → lunge → recover. Always active."""
    if ai.state == AIState.IDLE or ai.state == AIState.DETECT:
        # Skip idle/detect — always chase immediately
        ai.state = AIState.CHASE
        ai.state_timer = 0

    if ai.state == AIState.CHASE:
        # Accelerate toward player
        vel.x += dir_x * ai.move_speed * 0.3
        vel.y += dir_y * ai.move_speed * 0.3

        # Lunge when close (within 4 tiles)
        if dist < 4.0 and ai.state_timer > 30:
            ai.state = AIState.ATTACK
            ai.state_timer = 0

    elif ai.state == AIState.ATTACK:
        # Lunge burst — high speed toward player for 10 frames
        if ai.state_timer < 10:
            vel.x += dir_x * 0.8
            vel.y += dir_y * 0.8
        else:
            ai.state = AIState.RECOVER
            ai.state_timer = 0

    elif ai.state == AIState.RECOVER:
        vel.x *= 0.85
        vel.y *= 0.85
        if ai.state_timer > 18:  # 0.3s recovery
            ai.state = AIState.CHASE
            ai.state_timer = 0


# =============================================================================
# GUARD BEHAVIOR (Firewall)
# =============================================================================

def _ai_guard_behavior(world: World, entity_id: int, pos: Position,
                       vel: Velocity, ai: AIBehavior, dist: float,
                       dir_x: float, dir_y: float):
    """Guard behavior: intercept pathfinding + shield bash. Always active."""
    if ai.state == AIState.IDLE or ai.state == AIState.DETECT:
        ai.state = AIState.CHASE
        ai.state_timer = 0

    if ai.state == AIState.CHASE:
        # Intercept: predict player movement by looking at player velocity
        player_id = ai.target_entity
        p_vel = world.get_component(player_id, Velocity) if player_id is not None else None
        intercept_x, intercept_y = dir_x, dir_y
        if p_vel and (abs(p_vel.x) > 0.05 or abs(p_vel.y) > 0.05):
            # Aim ahead of player by ~10 frames
            predict_frames = 10
            from .components import Position as P
            pp = world.get_component(player_id, P)
            if pp:
                future_x = pp.x + p_vel.x * predict_frames
                future_y = pp.y + p_vel.y * predict_frames
                fdx = future_x - pos.x
                fdy = future_y - pos.y
                fdist = math.sqrt(fdx * fdx + fdy * fdy)
                if fdist > 0:
                    intercept_x = fdx / fdist
                    intercept_y = fdy / fdist

        vel.x += intercept_x * ai.move_speed * 0.2
        vel.y += intercept_y * ai.move_speed * 0.2

        # Shield bash when player is close AND in front
        if dist < ai.attack_range:
            # Check if player is in front (dot product with facing)
            front_dot = dir_x * ai.facing_x + dir_y * ai.facing_y
            if front_dot > 0.5 and ai.state_timer > 180:  # 3s cooldown
                ai.state = AIState.ATTACK
                ai.state_timer = 0

    elif ai.state == AIState.ATTACK:
        # Shield bash: burst forward for 18 frames (0.3s)
        if ai.state_timer < 18:
            vel.x = ai.facing_x * 0.6
            vel.y = ai.facing_y * 0.6
        else:
            ai.state = AIState.RECOVER
            ai.state_timer = 0

    elif ai.state == AIState.RECOVER:
        vel.x *= 0.8
        vel.y *= 0.8
        if ai.state_timer > 30:
            ai.state = AIState.CHASE
            ai.state_timer = 0


# =============================================================================
# CHARGE BEHAVIOR (Overclocker)
# =============================================================================

def _ai_charge_behavior(world: World, entity_id: int, pos: Position,
                        vel: Velocity, ai: AIBehavior, dist: float,
                        dir_x: float, dir_y: float, player_pos: Position):
    """Charge behavior: orbit → charge → dash → reposition. Always active."""
    charge = world.get_component(entity_id, ChargeAttack)
    rend = world.get_component(entity_id, Renderable)

    if charge is None:
        _ai_chase_behavior(world, entity_id, pos, vel, ai, dist, dir_x, dir_y)
        return

    if ai.state == AIState.IDLE or ai.state == AIState.DETECT:
        ai.state = AIState.CHASE
        ai.state_timer = 0

    if ai.state == AIState.CHASE:
        # Orbit behavior: circle player at 6-8 tile radius
        orbit_radius = 7.0
        if dist < orbit_radius - 1:
            # Too close — strafe away
            vel.x -= dir_x * ai.move_speed * 0.15
            vel.y -= dir_y * ai.move_speed * 0.15
        elif dist > orbit_radius + 2:
            # Too far — close in
            vel.x += dir_x * ai.move_speed * 0.25
            vel.y += dir_y * ai.move_speed * 0.25

        # Lateral strafe (orbit around player)
        strafe_x = -dir_y
        strafe_y = dir_x
        # Alternate strafe direction periodically
        if (ai.state_timer // 90) % 2 == 0:
            strafe_x, strafe_y = -strafe_x, -strafe_y
        vel.x += strafe_x * ai.move_speed * 0.15
        vel.y += strafe_y * ai.move_speed * 0.15

        # Initiate charge after orbiting for a while (3s cooldown)
        if ai.state_timer > 180:
            ai.state = AIState.CHARGE
            ai.state_timer = 0
            charge.charging = True
            charge.charge_timer = 0
            charge._target_x = player_pos.x
            charge._target_y = player_pos.y

    elif ai.state == AIState.CHARGE:
        vel.x *= 0.7
        vel.y *= 0.7
        charge.charge_timer += 1

        # Telegraph: red flash
        if rend and charge.charge_timer < charge.charge_time:
            if not hasattr(charge, '_original_color'):
                charge._original_color = rend.color
            rend.color = NEON_RED if charge.charge_timer % 4 < 2 else 196

        # Update target during first 60% of charge (tracks player)
        if charge.charge_timer < charge.charge_time * 0.6:
            charge._target_x = player_pos.x
            charge._target_y = player_pos.y

        if charge.charge_timer >= charge.charge_time:
            dx = charge._target_x - pos.x
            dy = charge._target_y - pos.y
            dist_to_target = math.sqrt(dx * dx + dy * dy)
            if dist_to_target > 0:
                ai.facing_x = dx / dist_to_target
                ai.facing_y = dy / dist_to_target
            ai.state = AIState.ATTACK
            ai.state_timer = 0
            charge.charging = False

    elif ai.state == AIState.ATTACK:
        if ai.state_timer < 20:
            vel.x = ai.facing_x * charge.charge_speed
            vel.y = ai.facing_y * charge.charge_speed

            if ai.state_timer % 2 == 0:
                from .particles import spawn_particle
                spawn_particle(
                    world, pos.x, pos.y,
                    vx=random.uniform(-0.2, 0.2),
                    vy=random.uniform(-0.2, 0.2),
                    char=random.choice(['>', '<', '*', '~']),
                    color=NEON_CYAN,
                    lifetime=8,
                    gravity=0
                )

            if ai.state_timer == 19:
                syntax_drop = world.get_component(entity_id, SyntaxDrop)
                if syntax_drop:
                    if not hasattr(syntax_drop, '_hit_during_dash'):
                        syntax_drop._dodged = True
        else:
            ai.state = AIState.RECOVER
            ai.state_timer = 0
            if rend and hasattr(charge, '_original_color'):
                rend.color = charge._original_color
                delattr(charge, '_original_color')

    elif ai.state == AIState.RECOVER:
        vel.x *= 0.85
        vel.y *= 0.85
        if ai.state_timer > 30:  # Shorter recovery (was 40)
            ai.state = AIState.CHASE
            ai.state_timer = 0
            if hasattr(charge, '_target_x'):
                delattr(charge, '_target_x')
                delattr(charge, '_target_y')


# =============================================================================
# SPAMMER BEHAVIOR
# =============================================================================

def _ai_spammer_behavior(world: World, entity_id: int, pos: Position,
                         vel: Velocity, ai: AIBehavior, dist: float,
                         dir_x: float, dir_y: float, player_pos: Position):
    """Spammer: strafe at distance, fire projectiles, flee if rushed."""
    ranged = world.get_component(entity_id, RangedAttack)
    rend = world.get_component(entity_id, Renderable)

    if ai.state == AIState.IDLE or ai.state == AIState.DETECT:
        ai.state = AIState.CHASE
        ai.state_timer = 0

    preferred_range = 12.0
    flee_range = 5.0

    if ai.state == AIState.FLEE:
        # Run away from player
        vel.x -= dir_x * 0.5
        vel.y -= dir_y * 0.5
        if dist > flee_range + 3 or ai.state_timer > 60:
            ai.state = AIState.CHASE
            ai.state_timer = 0

    elif ai.state == AIState.CHASE:
        # Reposition: maintain preferred range with lateral strafe
        if dist < flee_range:
            ai.state = AIState.FLEE
            ai.state_timer = 0
            return

        if dist < preferred_range - 2:
            # Back away
            vel.x -= dir_x * ai.move_speed * 0.2
            vel.y -= dir_y * ai.move_speed * 0.2
        elif dist > preferred_range + 3:
            # Close in
            vel.x += dir_x * ai.move_speed * 0.2
            vel.y += dir_y * ai.move_speed * 0.2

        # Lateral strafe
        strafe_x = -dir_y
        strafe_y = dir_x
        if (ai.state_timer // 60) % 2 == 0:
            strafe_x, strafe_y = -strafe_x, -strafe_y
        vel.x += strafe_x * ai.move_speed * 0.15
        vel.y += strafe_y * ai.move_speed * 0.15

    # Ranged attack (runs in any state except flee)
    if ranged and ai.state != AIState.FLEE:
        ranged.cooldown_timer -= 1.0 / 60.0
        if ranged.is_charging:
            ranged.charge_timer += 1.0 / 60.0
            # Telegraph: pulse brighter
            if rend:
                if not hasattr(ranged, '_orig_color'):
                    ranged._orig_color = rend.color
                rend.color = WHITE if int(ranged.charge_timer * 10) % 2 == 0 else NEON_YELLOW

            if ranged.charge_timer >= ranged.telegraph_time:
                # Fire!
                from .enemy_projectiles import spawn_enemy_projectile
                aim_x, aim_y = dir_x, dir_y
                spawn_enemy_projectile(
                    world, pos.x, pos.y, aim_x, aim_y,
                    speed=ranged.projectile_speed,
                    damage=ranged.projectile_damage,
                    visual=ranged.projectile_visual,
                    color=NEON_YELLOW,
                    owner_id=entity_id,
                )
                ranged.is_charging = False
                ranged.charge_timer = 0.0
                ranged.cooldown_timer = ranged.cooldown
                if rend and hasattr(ranged, '_orig_color'):
                    rend.color = ranged._orig_color
                    delattr(ranged, '_orig_color')

        elif ranged.cooldown_timer <= 0:
            # Start charge-up
            ranged.is_charging = True
            ranged.charge_timer = 0.0


# =============================================================================
# SNIPER BEHAVIOR (placeholder — Phase D fills this in)
# =============================================================================

def _ai_sniper_behavior(world: World, entity_id: int, pos: Position,
                        vel: Velocity, ai: AIBehavior, dist: float,
                        dir_x: float, dir_y: float, player_pos: Position):
    """Sniper: reposition far, charge aim line, fire hitscan beam."""
    sniper = world.get_component(entity_id, SniperState)
    rend = world.get_component(entity_id, Renderable)
    if not sniper:
        return

    dt = 1.0 / 60.0
    preferred_range = 18.0

    # --- Movement: maintain distance, prefer edges/corners ---
    if sniper.phase in ('idle', 'cooldown'):
        if dist < preferred_range - 3:
            # Back away from player
            vel.x -= dir_x * ai.move_speed * 0.3
            vel.y -= dir_y * ai.move_speed * 0.3
        elif dist > preferred_range + 5:
            # Close in slightly
            vel.x += dir_x * ai.move_speed * 0.15
            vel.y += dir_y * ai.move_speed * 0.15

        # Lateral strafe to avoid being easy to rush
        strafe_x = -dir_y
        strafe_y = dir_x
        if (ai.state_timer // 90) % 2 == 0:
            strafe_x, strafe_y = -strafe_x, -strafe_y
        vel.x += strafe_x * ai.move_speed * 0.1
        vel.y += strafe_y * ai.move_speed * 0.1

    # --- Phase machine ---
    if sniper.phase == 'idle':
        sniper.fire_cooldown_timer -= dt
        if sniper.fire_cooldown_timer <= 0:
            sniper.phase = 'tracking'
            sniper.charge_timer = 0.0
            # Initial aim at player
            sniper.aim_x = dir_x
            sniper.aim_y = dir_y

    elif sniper.phase == 'tracking':
        # Stop moving during charge
        vel.x *= 0.8
        vel.y *= 0.8
        sniper.charge_timer += dt

        # Track player for first (charge_duration - lock_time) seconds
        track_duration = sniper.charge_duration - sniper.lock_time
        if sniper.charge_timer < track_duration:
            # Smoothly track player position
            sniper.aim_x = dir_x
            sniper.aim_y = dir_y
        else:
            # Lock phase: direction is fixed
            sniper.phase = 'locked'

        # Telegraph: pulse color
        if rend:
            t = int(sniper.charge_timer * 8)
            rend.color = WHITE if t % 2 == 0 else NEON_RED

    elif sniper.phase == 'locked':
        # Direction locked, counting down to fire
        vel.x *= 0.5
        vel.y *= 0.5
        sniper.charge_timer += dt

        # Bright flash to warn player
        if rend:
            t = int(sniper.charge_timer * 15)
            rend.color = WHITE if t % 2 == 0 else 196

        if sniper.charge_timer >= sniper.charge_duration:
            # Fire!
            sniper.phase = 'firing'
            sniper.fire_frames = sniper.fire_duration

            # Deal damage via hitscan
            _sniper_hitscan(world, entity_id, pos, sniper)

    elif sniper.phase == 'firing':
        vel.x = 0
        vel.y = 0
        sniper.fire_frames -= 1

        if rend:
            rend.color = WHITE

        if sniper.fire_frames <= 0:
            sniper.phase = 'cooldown'
            sniper.cooldown_timer = sniper.cooldown_duration
            if rend:
                rend.color = NEON_RED

    elif sniper.phase == 'cooldown':
        sniper.cooldown_timer -= dt
        # Dim during vulnerability
        if rend:
            rend.color = 52  # dim red

        if sniper.cooldown_timer <= 0:
            sniper.phase = 'idle'
            sniper.fire_cooldown_timer = sniper.fire_cooldown
            if rend:
                rend.color = NEON_RED


def _sniper_hitscan(world: World, sniper_id: int, sniper_pos: Position,
                    sniper: 'SniperState'):
    """Check hitscan beam collision with player."""
    from .particles import spawn_explosion

    # Find player
    player_id = None
    p_pos = None
    p_health = None
    for pid, pp, ph, _ in world.query(Position, Health, PlayerTag):
        player_id = pid
        p_pos = pp
        p_health = ph
        break

    if player_id is None:
        return

    # Check i-frames / dash
    invuln = world.get_component(player_id, Invulnerable)
    dash = world.get_component(player_id, DashState)
    if (invuln and invuln.frames_remaining > 0) or (dash and dash.frames_remaining > 0):
        return

    # Hitscan: check if player is within beam corridor
    dx = p_pos.x - sniper_pos.x
    dy = p_pos.y - sniper_pos.y

    # Project player position onto beam direction
    t = dx * sniper.aim_x + dy * sniper.aim_y
    if t < 0:
        return  # Player is behind the sniper

    # Perpendicular distance from beam line
    perp_x = dx - t * sniper.aim_x
    perp_y = dy - t * sniper.aim_y
    perp_dist = math.sqrt(perp_x * perp_x + perp_y * perp_y)

    if perp_dist < 1.5:  # Beam hit width
        p_stats = world.get_component(player_id, PlayerStats)
        effective_dmg = sniper.beam_damage
        if p_stats and p_stats.damage_reduction > 0:
            effective_dmg = max(1, int(effective_dmg * (1 - p_stats.damage_reduction)))
        p_health.current = max(0, p_health.current - effective_dmg)

        # I-frames
        iframes = p_stats.invincibility_frames if p_stats else 45
        world.add_component(player_id, Invulnerable(frames_remaining=iframes))

        # Knockback along beam direction
        world.add_component(player_id, Knockback(
            sniper.aim_x * 0.5, sniper.aim_y * 0.5, decay=0.7
        ))

        # Impact particles
        spawn_explosion(
            world, p_pos.x, p_pos.y,
            count=8, colors=[NEON_RED, WHITE, 196],
            chars=['!', '*', '+'], speed_min=0.3, speed_max=0.8,
            lifetime_min=6, lifetime_max=12, gravity=0
        )


# =============================================================================
# COMBAT SYSTEM
# =============================================================================

def combat_system(world: World, renderer: 'GameRenderer') -> List[dict]:
    """
    Handle all combat interactions:
      1. Player slash attack hitting enemies
      2. Enemy body contact damaging the player

    Returns a list of event dicts for the game loop to process
    (e.g., verb drops, death effects).
    """
    events = []

    # --- Player attack vs enemies ---
    for player_id, p_pos, attack, _ in world.query(
        Position, AttackState, PlayerTag
    ):
        if not attack.active:
            continue

        # Get player stats for size/damage/crit
        p_stats = world.get_component(player_id, PlayerStats)

        # Get active weapon data for damage/knockback
        _weapon_damage = 25
        _weapon_knockback = 1.2
        _weapon_extra_hitstop = 0
        _weapon_extra_shake = False
        _active_w = None
        p_inv = world.get_component(player_id, WeaponInventory)
        if p_inv and p_inv.weapons:
            from .weapons import get_weapon_data
            _active_w = p_inv.weapons[min(p_inv.active_index, len(p_inv.weapons) - 1)]
            _wdata = dict(get_weapon_data(_active_w))
            # Apply mod param modifications (e.g. --force 3x knockback)
            if _active_w.mods:
                from .weapon_mods import apply_mod_params
                apply_mod_params(_active_w, _wdata)
            _weapon_damage = _wdata.get('damage', 25)
            _weapon_knockback = _wdata.get('knockback', 1.2)
            _weapon_extra_hitstop = _wdata.get('hit_stop_frames', 0)
            _weapon_extra_shake = _wdata.get('screen_shake_on_hit', False)

        # Check each enemy against the attack zone
        shield_blocked = False
        for enemy_id, e_pos, e_health, e_tag in world.query(
            Position, Health, EnemyTag
        ):
            dx = e_pos.x - p_pos.x
            dy = e_pos.y - p_pos.y
            dist = math.sqrt(dx * dx + dy * dy)

            if attack.is_beam:
                # Beam: line collision — check distance from enemy to beam line(s)
                beam_range = attack.beam_range
                if p_stats:
                    beam_range *= p_stats.attack_size_multiplier
                # Determine beam directions (single or triple)
                _beam_count = _wdata.get('beam_count', 1) if p_inv and p_inv.weapons else 1
                _beam_spread = _wdata.get('beam_spread_angle', 0) if p_inv and p_inv.weapons else 0
                _base_angle = math.atan2(attack.direction_y, attack.direction_x)
                _beam_dirs = [(_base_angle, attack.direction_x, attack.direction_y)]
                if _beam_count >= 3 and _beam_spread > 0:
                    _spread_rad = math.radians(_beam_spread)
                    for _off in (_spread_rad, -_spread_rad):
                        _a = _base_angle + _off
                        _beam_dirs.append((_a, math.cos(_a), math.sin(_a)))
                # Check if enemy is hit by ANY beam line
                _beam_hit = False
                for _, _bdx, _bdy in _beam_dirs:
                    t = dx * _bdx + dy * _bdy
                    if t < 0 or t > beam_range:
                        continue
                    perp_x = dx - t * _bdx
                    perp_y = dy - t * _bdy
                    perp_dist = math.sqrt(perp_x * perp_x + perp_y * perp_y)
                    if perp_dist <= 1.2:
                        _beam_hit = True
                        break
                if not _beam_hit:
                    continue
            else:
                # Melee: cone in attack direction
                effective_radius = attack.radius
                if p_stats:
                    effective_radius *= p_stats.attack_size_multiplier
                if dist > effective_radius:
                    continue

                # Check if enemy is in the attack direction (dot product)
                if dist > 0:
                    ndx, ndy = dx / dist, dy / dist
                    dot = ndx * attack.direction_x + ndy * attack.direction_y
                    if dot < 0.3:  # Must be roughly in slash direction
                        continue

            # Check for shield blocking (Firewall) — not for beams, --sudo bypasses
            shield = world.get_component(enemy_id, Shield)
            ai = world.get_component(enemy_id, AIBehavior)
            is_backstab = False
            _has_sudo = _active_w and 'sudo_mod' in _active_w.mods if p_inv and p_inv.weapons else False

            if shield and shield.active and ai and not attack.is_beam and not _has_sudo:
                attack_dot = attack.direction_x * ai.facing_x + attack.direction_y * ai.facing_y

                if attack_dot < 0.3:
                    p_vel = world.get_component(player_id, Velocity)
                    if p_vel and dist > 0:
                        kb_x = -dx / dist * shield.knockback_force
                        kb_y = -dy / dist * shield.knockback_force
                        world.add_component(player_id, Knockback(kb_x, kb_y, decay=0.7))

                    renderer.trigger_shake(intensity=1, frames=3)
                    renderer.trigger_hitstop(2)

                    from .particles import spawn_directional_burst
                    spawn_directional_burst(
                        world, e_pos.x, e_pos.y,
                        -attack.direction_x, -attack.direction_y,
                        count=4,
                        colors=[NEON_YELLOW, WHITE],
                        chars=['!', '*', 'x']
                    )

                    ai._shield_stun = 30
                    shield_blocked = True
                    attack.active = False
                    break

                else:
                    is_backstab = True

            # Hit! Apply damage
            base_damage = _weapon_damage
            is_crit = False
            _auto_crit = _wdata.get('auto_crit', False) if p_inv and p_inv.weapons else False

            if p_stats:
                base_damage = int(base_damage * p_stats.damage_multiplier)
                if _auto_crit or random.random() < p_stats.crit_chance:
                    base_damage = int(base_damage * p_stats.crit_damage_multiplier)
                    is_crit = True

            multiplier = world.get_component(player_id, AttackMultiplier)
            if multiplier:
                total_damage = int(base_damage * multiplier.damage_multiplier * multiplier.hits)
                multiplier.uses_remaining -= 1
                if multiplier.uses_remaining <= 0:
                    world.remove_component(player_id, AttackMultiplier)
            else:
                total_damage = base_damage
            e_health.current -= total_damage

            if is_backstab:
                syntax_drop = world.get_component(enemy_id, SyntaxDrop)
                if syntax_drop:
                    syntax_drop._backstabbed = True

            flash = world.get_component(enemy_id, HitFlash)
            if flash:
                flash.frames_remaining = 4

            # Knockback
            if dist > 0:
                kb_x = dx / dist * _weapon_knockback
                kb_y = dy / dist * _weapon_knockback
            else:
                kb_x = attack.direction_x * _weapon_knockback
                kb_y = attack.direction_y * _weapon_knockback
            world.add_component(enemy_id, Knockback(kb_x, kb_y, decay=0.7))

            # Fire mod on_hit hooks
            if _active_w and _active_w.mods:
                from .weapon_mods import fire_on_hit
                fire_on_hit(
                    world, _active_w, enemy_id,
                    (e_pos.x, e_pos.y), total_damage,
                    (attack.direction_x, attack.direction_y), renderer
                )

            if attack.is_beam:
                # Overcharge: double damage after 3s continuous beam
                _overcharge_threshold = _wdata.get('overcharge_frames', 0) if p_inv and p_inv.weapons else 0
                if _overcharge_threshold > 0 and attack.beam_continuous_frames >= _overcharge_threshold:
                    e_health.current -= total_damage  # Deal damage again (double)
                # Beam: lighter feedback, hits all enemies (don't break)
                from .particles import spawn_particle
                spawn_particle(
                    world, e_pos.x, e_pos.y,
                    vx=random.uniform(-0.3, 0.3),
                    vy=random.uniform(-0.3, 0.3),
                    char=random.choice(['*', '+', '~']),
                    color=NEON_MAGENTA,
                    lifetime=random.randint(4, 8),
                    gravity=0
                )
                continue  # Beam hits ALL enemies along line

            # Melee: full feedback, one hit per swing
            renderer.trigger_hitstop(3 + _weapon_extra_hitstop)
            shake_int = 3 if _weapon_extra_shake else 2
            renderer.trigger_shake(intensity=shake_int, frames=4)

            from .particles import spawn_directional_burst
            if is_crit:
                spark_colors = [NEON_YELLOW, WHITE, NEON_RED]
                spark_count = 10
                spark_chars = ['!', '*', '+', 'x', '#']
            elif is_backstab:
                spark_colors = [NEON_RED, NEON_YELLOW, WHITE]
                spark_count = 8
                spark_chars = ['!', '*', '+', 'x']
            else:
                spark_colors = [WHITE, NEON_CYAN, NEON_YELLOW]
                spark_count = 6
                spark_chars = ['*', '+', 'x']
            spawn_directional_burst(
                world, e_pos.x, e_pos.y,
                attack.direction_x, attack.direction_y,
                count=spark_count,
                colors=spark_colors,
                chars=spark_chars
            )

            # Deactivate attack so it only hits once per swing
            attack.active = False
            break

    # --- Enemy body contact vs player ---
    for player_id, p_pos, p_health, p_box, _ in world.query(
        Position, Health, CollisionBox, PlayerTag
    ):
        # Skip if player has i-frames
        invuln = world.get_component(player_id, Invulnerable)
        if invuln and invuln.frames_remaining > 0:
            continue

        # Skip if player is dashing (dash grants i-frames)
        dash = world.get_component(player_id, DashState)
        if dash and dash.frames_remaining > 0:
            continue

        # Get player stats for damage reduction and i-frames
        p_stats = world.get_component(player_id, PlayerStats)

        for enemy_id, e_pos, e_box, dmg, e_tag in world.query(
            Position, CollisionBox, Damage, EnemyTag
        ):
            if collision_check(p_pos, p_box, e_pos, e_box):
                # Damage player (apply damage reduction)
                effective_dmg = dmg.amount
                if p_stats and p_stats.damage_reduction > 0:
                    effective_dmg = max(1, int(dmg.amount * (1 - p_stats.damage_reduction)))
                p_health.current -= effective_dmg
                p_health.current = max(0, p_health.current)

                # Grant i-frames (use stats value if available)
                iframes = p_stats.invincibility_frames if p_stats else 45
                world.add_component(player_id, Invulnerable(frames_remaining=iframes))

                # Knockback player away from enemy
                dx = p_pos.x - e_pos.x
                dy = p_pos.y - e_pos.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > 0:
                    kb_x = dx / dist * dmg.knockback_force
                    kb_y = dy / dist * dmg.knockback_force
                else:
                    kb_x = 0
                    kb_y = -dmg.knockback_force
                world.add_component(player_id, Knockback(kb_x, kb_y, decay=0.7))

                # Screen shake
                renderer.trigger_shake(intensity=2, frames=5)
                renderer.trigger_hitstop(2)

                # Damage sparks on player
                from .particles import spawn_explosion
                spawn_explosion(
                    world, p_pos.x, p_pos.y,
                    count=8,
                    colors=[NEON_RED, NEON_YELLOW, WHITE],
                    chars=['!', '*', '+', 'x'],
                    speed_min=0.3,
                    speed_max=0.8,
                    lifetime_min=10,
                    lifetime_max=20,
                    gravity=0.05
                )

                # Enemy-specific on-hit effects
                if e_tag.enemy_type == 'buffer_leak':
                    # Buffer-Leak: remove a verb on contact
                    syntax = world.get_component(player_id, SyntaxBuffer)
                    if syntax and syntax.verbs:
                        syntax.verbs.pop()
                        events.append({'type': 'verb_removed'})

                elif e_tag.enemy_type == 'overclocker':
                    # Overclocker: mark that dash hit the player (no dodge)
                    e_ai = world.get_component(enemy_id, AIBehavior)
                    syntax_drop = world.get_component(enemy_id, SyntaxDrop)
                    if e_ai and e_ai.state == AIState.ATTACK and syntax_drop:
                        syntax_drop._hit_during_dash = True
                        # Remove dodge flag
                        if hasattr(syntax_drop, '_dodged'):
                            delattr(syntax_drop, '_dodged')

                break  # Only one enemy hit per frame

    return events


def invulnerability_system(world: World):
    """Tick down invulnerability frames."""
    for entity_id, invuln in world.query(Invulnerable):
        if invuln.frames_remaining > 0:
            invuln.frames_remaining -= 1


def death_system(world: World, renderer: 'GameRenderer') -> List[dict]:
    """
    Check for dead enemies (health <= 0).
    Spawn death particles, emit verb drop events, destroy the entity.

    Returns event dicts for verb drops.
    """
    events = []

    # Get player stats once for verb drop rate bonus
    player_stats = None
    for eid, ps in world.query(PlayerStats):
        if world.has_component(eid, PlayerTag):
            player_stats = ps
            break

    dead_enemies = []
    for entity_id, pos, health, e_tag in world.query(Position, Health, EnemyTag):
        if health.current <= 0:
            dead_enemies.append((entity_id, pos.x, pos.y, e_tag.enemy_type))

    for entity_id, x, y, enemy_type in dead_enemies:
        # Spawn death particles based on enemy type
        _spawn_death_effect(world, x, y, enemy_type)

        # Screen shake for death
        renderer.trigger_shake(intensity=2, frames=5)

        # Always emit enemy_killed event
        events.append({'type': 'enemy_killed', 'enemy_type': enemy_type,
                       'x': x, 'y': y})

        # Check for verb drop
        syntax_drop = world.get_component(entity_id, SyntaxDrop)
        if syntax_drop:
            should_drop = False

            if syntax_drop.drop_condition == 'kill':
                should_drop = True
            elif syntax_drop.drop_condition == 'backstab':
                # Check if enemy was backstabbed
                should_drop = hasattr(syntax_drop, '_backstabbed') and syntax_drop._backstabbed
            elif syntax_drop.drop_condition == 'dodge':
                # Overclocker: drops when charge was dodged (checked elsewhere)
                should_drop = hasattr(syntax_drop, '_dodged') and syntax_drop._dodged

            if should_drop:
                events.append({
                    'type': 'verb_drop',
                    'verb': syntax_drop.verb,
                    'x': x,
                    'y': y,
                })

            # Bonus verb drop from upgrade
            if player_stats and player_stats.verb_drop_rate > 0:
                if random.random() < player_stats.verb_drop_rate:
                    bonus_verb = random.choice(
                        ['RECURSIVE', 'SUDO', 'DASH', 'SLICE', 'VOID', 'NULL']
                    )
                    events.append({
                        'type': 'verb_drop',
                        'verb': bonus_verb,
                        'x': x,
                        'y': y,
                    })

        world.destroy_entity(entity_id)

    return events


def _spawn_death_effect(world: World, x: float, y: float, enemy_type: str):
    """Spawn enemy-type-specific death particles."""
    from .particles import (
        spawn_death_particles_buffer_leak,
        spawn_death_particles_firewall,
        spawn_death_particles_overclocker,
        spawn_explosion
    )

    if enemy_type == 'buffer_leak':
        spawn_death_particles_buffer_leak(world, x, y)
    elif enemy_type == 'firewall':
        spawn_death_particles_firewall(world, x, y)
    elif enemy_type == 'overclocker':
        spawn_death_particles_overclocker(world, x, y)
    elif enemy_type == 'spammer':
        spawn_explosion(world, x, y, count=8,
                        colors=[NEON_YELLOW, WHITE, 226],
                        chars=['!', '*', '.'],
                        speed_max=1.0, gravity=0.05)
    elif enemy_type == 'sniper':
        spawn_explosion(world, x, y, count=12,
                        colors=[NEON_RED, WHITE, 196],
                        chars=['\u00a6', '*', '+', '.'],
                        speed_max=1.2, gravity=0.03)
    else:
        spawn_explosion(world, x, y, count=10)


# =============================================================================
# ATTACK SYSTEM
# =============================================================================

# Slash arc patterns: offsets relative to player for each direction
SLASH_ARCS = {
    (0, -1): [  # Up
        (-2, -2), (-1, -2), (0, -2), (1, -2), (2, -2),
        (-1, -1), (0, -1), (1, -1),
    ],
    (0, 1): [  # Down
        (-2, 2), (-1, 2), (0, 2), (1, 2), (2, 2),
        (-1, 1), (0, 1), (1, 1),
    ],
    (-1, 0): [  # Left
        (-2, -2), (-2, -1), (-2, 0), (-2, 1), (-2, 2),
        (-1, -1), (-1, 0), (-1, 1),
    ],
    (1, 0): [  # Right
        (2, -2), (2, -1), (2, 0), (2, 1), (2, 2),
        (1, -1), (1, 0), (1, 1),
    ],
}

SLASH_CHARS = ['/', '\\', '|', '-', '*', 'x', '+']

# Slash color cascade: bright → dim over the arc's lifetime
SLASH_COLORS = [WHITE, NEON_CYAN, NEON_MAGENTA, NEON_CYAN, GRAY_MED, GRAY_DARK]


def spawn_slash_arc(world: World, px: float, py: float, dir_x: float, dir_y: float):
    """
    Spawn a directional slash arc as short-lived particle entities.

    Each cell of the arc is a separate particle so the arc
    fades out naturally via the lifetime system.
    """
    from .particles import spawn_particle

    key = (int(dir_x), int(dir_y))
    arc_cells = SLASH_ARCS.get(key, [])

    for i, (ox, oy) in enumerate(arc_cells):
        # Stagger lifetime so outer cells fade first
        base_life = 12
        life = base_life - (i % 3) * 2

        # Pick visual
        char = random.choice(SLASH_CHARS)
        color_idx = min(i, len(SLASH_COLORS) - 1)
        color = SLASH_COLORS[color_idx]

        spawn_particle(
            world,
            px + ox, py + oy,
            vx=dir_x * 0.1, vy=dir_y * 0.1,
            char=char,
            color=color,
            lifetime=max(life, 4),
            gravity=0
        )


# =============================================================================
# RENDERING SYSTEMS
# =============================================================================

def render_system(world: World, renderer: GameRenderer):
    """
    Render all visible entities to the game buffer.

    Sorts by render layer, draws ghost trails first (behind entities),
    then entities themselves.
    """
    render_list = []

    for entity_id, pos, rend in world.query(Position, Renderable):
        if not rend.visible:
            continue
        # Skip particles (handled by particle_render_system)
        if world.has_component(entity_id, ParticleTag):
            continue
        render_list.append((rend.layer, entity_id, pos, rend))

    render_list.sort(key=lambda x: x[0])

    # Ghost trails (behind entities)
    for _, entity_id, pos, rend in render_list:
        trail = world.get_component(entity_id, GhostTrail)
        if trail and trail.positions:
            for i, (tx, ty) in enumerate(trail.positions):
                color_idx = min(i, len(trail.colors) - 1)
                # Oldest echo uses dimmest color
                color = trail.colors[-(color_idx + 1)]
                x, y = int(tx), int(ty)
                if 0 <= x < renderer.width and 0 <= y < renderer.game_height:
                    renderer.put(x, y, rend.char, color)

    # Entities
    for _, entity_id, pos, rend in render_list:
        x, y = int(pos.x), int(pos.y)
        if 0 <= x < renderer.width and 0 <= y < renderer.game_height:
            renderer.put(x, y, rend.char, rend.color)

        # Shield direction indicator
        shield = world.get_component(entity_id, Shield)
        ai = world.get_component(entity_id, AIBehavior)
        if shield and shield.active and ai:
            if abs(ai.facing_x) >= abs(ai.facing_y):
                sx = x + (1 if ai.facing_x > 0 else -1)
                sy = y
                char = ']' if ai.facing_x > 0 else '['
            else:
                sx = x
                sy = y + (1 if ai.facing_y > 0 else -1)
                char = 'v' if ai.facing_y > 0 else '^'
            if 0 <= sx < renderer.width and 0 <= sy < renderer.game_height:
                renderer.put(sx, sy, char, NEON_YELLOW)


def particle_render_system(world: World, renderer: GameRenderer):
    """
    Render particles. Fresh particles use their character; fading
    particles transition to braille sub-pixels for a smooth fade-out.
    """
    for entity_id, pos, rend, _, lifetime in world.query(
        Position, Renderable, ParticleTag, Lifetime
    ):
        if not rend.visible:
            continue

        # Life ratio determines render style
        max_life = 30
        life_ratio = max(0, lifetime.frames_remaining) / max_life

        if life_ratio > 0.4:
            # Full character rendering
            x, y = int(pos.x), int(pos.y)
            if 0 <= x < renderer.width and 0 <= y < renderer.game_height:
                renderer.put(x, y, rend.char, rend.color)
        else:
            # Sub-pixel braille rendering for smooth fade
            fade_color = rend.color if life_ratio > 0.2 else GRAY_DARK
            renderer.put_braille_pixel(pos.x, pos.y, fade_color)


def render_starfield(renderer: GameRenderer, stars: list):
    """
    Render a sparse starfield background.

    Stars are pre-generated (x, y, char, color) tuples.
    """
    for x, y, char, color in stars:
        if 0 <= x < renderer.width and 0 <= y < renderer.game_height:
            renderer.put(x, y, char, color)


def generate_starfield(width: int, height: int, density: float = 0.008) -> list:
    """
    Generate a random starfield for the background.

    Returns list of (x, y, char, color) tuples.
    """
    stars = []
    star_chars = ['.', '·', '∙', '+', '*']
    star_weights = [40, 30, 15, 10, 5]
    star_colors = [GRAY_DARKER, GRAY_DARK, 236, 237, 234]

    count = int(width * height * density)
    for _ in range(count):
        x = random.randint(1, width - 2)
        y = random.randint(1, height - 2)
        char = random.choices(star_chars, weights=star_weights, k=1)[0]
        color = random.choice(star_colors)
        stars.append((x, y, char, color))

    return stars


# =============================================================================
# COLLISION UTILITIES
# =============================================================================

def collision_check(
    pos1: Position, box1: CollisionBox,
    pos2: Position, box2: CollisionBox
) -> bool:
    """Check AABB overlap between two entities."""
    x1 = pos1.x + box1.offset_x
    y1 = pos1.y + box1.offset_y
    x2 = pos2.x + box2.offset_x
    y2 = pos2.y + box2.offset_y

    return (
        x1 < x2 + box2.width and
        x1 + box1.width > x2 and
        y1 < y2 + box2.height and
        y1 + box1.height > y2
    )


def get_direction_to(from_pos: Position, to_pos: Position) -> Tuple[float, float]:
    """Get normalized direction vector between two positions."""
    dx = to_pos.x - from_pos.x
    dy = to_pos.y - from_pos.y
    dist = math.sqrt(dx * dx + dy * dy)
    if dist > 0:
        return dx / dist, dy / dist
    return 0.0, 0.0


def get_distance(pos1: Position, pos2: Position) -> float:
    """Get Euclidean distance between two positions."""
    dx = pos2.x - pos1.x
    dy = pos2.y - pos1.y
    return math.sqrt(dx * dx + dy * dy)
