# Need automated ability-usage analyzer

**Status:** ready-for-agent
**Severity:** medium
**Reporter:** user

## Problem

No easy way to run N games with a specific hero and see which abilities are never used. Currently you'd have to read through game logs manually.

## Expected behavior

A script that:
1. Creates N games (e.g., 10) all containing a specific hero on one team
2. Tracks which abilities that hero uses each game
3. Reports which abilities are never used (or used < threshold % of available turns)

## Implementation idea

Add ability-use logging to `quick_play.py` or create a new `analyze_usage.py` script that:
- Accepts hero name, number of games, opponent hero
- Runs games with RuleBasedAgent
- After each game, records which abilities the target hero used
- Summarizes: "X used Heavy Pulse Rifle 10/10 games, Biotic Field 0/10 games"
