# Scout Crit-a-Cola does nothing

**Status:** ready-for-agent
**Severity:** high
**Reporter:** user

## Problem

Scout's Crit-a-Cola ability applies `CritAColaBuff` and `CritAColaDebuff` modifiers, but these modifiers have methods (`apply_damage_buff`, `apply_vulnerable`) that nothing in the engine actually calls. The modifiers are applied but have zero mechanical effect.

## Expected behavior

Crit-a-Cola should make Scout deal +50% damage and receive +50% damage for 1 turn.

## Root cause

The modifier methods `apply_damage_buff()` and `apply_vulnerable()` are custom methods that nothing in the damage pipeline reads. The damage system doesn't check for these hooks.

## Fix

Need to either:
1. Hook into the damage pipeline so modifiers can modify incoming/outgoing damage, OR
2. Change the approach (e.g., use a simpler mechanic like +1 damage / -1 armor)
