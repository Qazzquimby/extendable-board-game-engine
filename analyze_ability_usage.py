#!/usr/bin/env python3
"""
Ability usage analyzer — runs varied game setups to stress-test hero abilities.

Runs N games with configurable team compositions, grid sizes, and starting
positions to ensure every ability gets tested in relevant situations.

Usage:
    python analyze_ability_usage.py Soldier76 --games 10                  # varied defaults
    python analyze_ability_usage.py Soldier76 --games 20 --varied          # explicit
    python analyze_ability_usage.py Zenyatta --ally Tracer --ally Mercy   # 2v1 with allies
    python analyze_ability_usage.py Reinhardt --team2 Soldier76,Scout     # 1v2
    python analyze_ability_usage.py Necrophos --games 15 --close          # start adjacent
"""

import sys
import argparse
import random
from pathlib import Path
from collections import defaultdict

_src = str(Path(__file__).resolve().parent / "backend" / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
_src2 = str(Path(__file__).resolve().parent / "backend")
if _src2 not in sys.path:
    sys.path.insert(0, _src2)

from engine import Engine, RuleBasedAgent
from grid import Grid
from point import Point
from hero_registry import get_hero_class, list_heroes


# ── Setup templates ──

SETUPS = {
    # (description, grid_size, team0_positions, team1_positions)
    # team0: [hero_pos, ally1_pos, ally2_pos]
    # team1: [enemy1_pos, enemy2_pos]
    "far": (
        "Far apart",
        10,
        [Point(0, 4)],
        [Point(9, 4)],
    ),
    "close": (
        "Close quarters",
        6,
        [Point(0, 2)],
        [Point(3, 2)],
    ),
    "scattered": (
        "Scattered positions",
        8,
        [Point(1, 1)],
        [Point(6, 6)],
    ),
    "with_ally_simple": (
        "With an ally",
        8,
        [Point(0, 2), Point(0, 4)],
        [Point(7, 3)],
    ),
    "1v2": (
        "Outnumbered",
        8,
        [Point(0, 3)],
        [Point(7, 2), Point(7, 4)],
    ),
    "2v2": (
        "Even teams",
        8,
        [Point(0, 2), Point(0, 5)],
        [Point(7, 2), Point(7, 5)],
    ),
    "2v2_scattered": (
        "2v2 scattered",
        10,
        [Point(0, 2), Point(0, 7)],
        [Point(9, 3), Point(9, 6)],
    ),
}


def pick_opponent(exclude=None):
    """Pick a random opponent hero from available ones."""
    all_heroes = list_heroes()
    if exclude:
        all_heroes = [h for h in all_heroes if h != exclude]
    if not all_heroes:
        return "Axe"
    return random.choice(all_heroes)


def build_setup(hero_cls, hero_name, setup_name, seed, allies=None, opponents=None):
    """Build a game setup from a named template or randomised parameters."""
    random.seed(seed)

    if setup_name in SETUPS:
        desc, grid_size, team0_pos, team1_pos = SETUPS[setup_name]
    elif setup_name == "random":
        # Randomised: pick grid size 6-10, positions at varying distances
        grid_size = random.randint(6, 10)
        mid = grid_size // 2
        d = random.randint(2, mid)
        team0_pos = [Point(mid - d, random.randint(0, grid_size - 1))]
        team1_pos = [Point(mid + d, random.randint(0, grid_size - 1))]
        desc = f"Random (grid {grid_size}, dist ~{d * 2})"
    else:
        raise ValueError(f"Unknown setup: {setup_name}")

    g = Grid(grid_size, grid_size)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=seed)

    # Place hero-under-test
    hero = hero_cls(engine=e, pos=team0_pos[0], team=0)

    # Place allies (if specified)
    ally_entities = []
    ally_classes = allies or []
    for i, ally_name in enumerate(ally_classes):
        pos_idx = min(i + 1, len(team0_pos) - 1)
        try:
            ally_cls = get_hero_class(ally_name)
            ally = ally_cls(engine=e, pos=team0_pos[pos_idx], team=0)
            ally_entities.append(ally)
        except KeyError:
            print(f"  WARNING: Unknown ally '{ally_name}', skipping")

    # Place opponents
    opponent_entities = []
    opp_classes = opponents or [pick_opponent(hero_name)]
    for i, opp_name in enumerate(opp_classes):
        pos_idx = min(i, len(team1_pos) - 1)
        try:
            opp_cls = get_hero_class(opp_name)
            opp = opp_cls(engine=e, pos=team1_pos[pos_idx], team=1)
            opponent_entities.append(opp)
        except KeyError:
            print(f"  WARNING: Unknown opponent '{opp_name}', skipping")

    e.finalize_setup()
    return e, hero, ally_entities, opponent_entities, desc


def analyze_ability(
    hero_name,
    allies=None,
    opponents=None,
    games=10,
    seed=42,
    varied=True,
):
    outpath = Path(__file__).resolve().parent / "analyze_output.txt"
    with open(outpath, "w", encoding="utf-8") as outf:
        def w(msg):
            print(msg)
            outf.write(msg + "\n")
            outf.flush()

        try:
            hero_cls = get_hero_class(hero_name)
        except KeyError:
            avail = list_heroes()
            w(f"Unknown hero '{hero_name}'. Available: {avail}")
            return

        # Resolve opponent names upfront
        opp_names = opponents or [pick_opponent(hero_name)]

        # Ability names from a temp instance
        temp_e = Engine(grid=Grid(6, 6), agents={0: RuleBasedAgent(), 1: RuleBasedAgent()}, seed=0)
        temp_h = hero_cls(engine=temp_e, pos=Point(0, 0), team=0)
        ability_names = [ab.name for ab in temp_h.abilities if ab.name != "Do Nothing"]
        total_uses = {name: 0 for name in ability_names}
        games_with_use = {name: 0 for name in ability_names}

        # Decide which setups to use
        if varied:
            # Cycle through all interesting setups
            setup_names = list(SETUPS.keys())
            # Add "random" every 3 games for variety
            cycle = setup_names * ((games // len(setup_names)) + 1)
            # Interleave random
            game_setups = []
            for i in range(games):
                if i > 0 and i % 3 == 0:
                    game_setups.append("random")
                else:
                    game_setups.append(cycle[i])
            game_setups = game_setups[:games]
        else:
            game_setups = ["far"] * games

        w(f"\n=== Analyzing {hero_name} ({games} games, varied setups) ===\n")

        for game_idx in range(games):
            current_seed = seed + game_idx
            setup_name = game_setups[game_idx]

            try:
                e, hero, ally_ents, opp_ents, desc = build_setup(
                    hero_cls, hero_name, setup_name, current_seed,
                    allies=allies, opponents=opp_names,
                )
                log = e.run_game()
            except Exception as ex:
                w(f"  Game {game_idx+1} (seed={current_seed}, {setup_name}): CRASHED - {ex}")
                import traceback
                traceback.print_exc()
                continue

            # Parse ability uses from action logs
            usage = defaultdict(int)
            for entry in log.logs:
                for al in entry.action_logs:
                    al_lower = al.lower()
                    for ab in hero.abilities:
                        ab_lower = ab.name.lower()
                        if ab_lower in al_lower and (" uses " in al_lower or " used " in al_lower):
                            usage[ab.name] += 1

            winner = getattr(log, "winner_team", "?")
            for name in ability_names:
                uses = usage.get(name, 0)
                total_uses[name] += uses
                if uses > 0:
                    games_with_use[name] += 1

            used_list = [n for n in ability_names if usage.get(n, 0) > 0]
            opps_named = ", ".join(e.name for e in opp_ents)
            w(f"  Game {game_idx+1:2d} [{setup_name:16s}] (seed={current_seed}, winner=team {winner}): {used_list or 'NOTHING'}")

        w(f"\n--- Summary ({hero_name}) ---")
        for name in ability_names:
            pct = (games_with_use[name] / games) * 100
            avg = total_uses[name] / games
            flag = " ** NEVER USED **" if games_with_use[name] == 0 else ""
            w(f"  {name:30s} used in {games_with_use[name]:2d}/{games} games ({pct:3.0f}%) avg {avg:.1f}/game{flag}")

        never_used = [n for n in ability_names if games_with_use[n] == 0]
        if never_used:
            w(f"\n  ** NEVER USED: {never_used}")
        else:
            w(f"\n  ** All abilities used at least once")

        w(f"\nResults saved to {outpath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze hero ability usage across varied setups")
    parser.add_argument("hero", help="Hero class name to analyze")
    parser.add_argument("--games", type=int, default=10, help="Number of games to run")
    parser.add_argument("--seed", type=int, default=42, help="Base seed")
    parser.add_argument("--ally", action="append", dest="allies", help="Ally hero class name (repeatable)")
    parser.add_argument("--team2", dest="opponents", help="Comma-separated opponent hero class names")
    parser.add_argument("--setup", default=None, choices=list(SETUPS.keys()) + [None],
                        help="Use a specific setup for all games (default: varied)")
    parser.add_argument("--close", action="store_true", help="Shortcut for --setup close")
    parser.add_argument("--varied", action="store_true", default=True,
                        help="Vary setups across games (default: True)")
    args = parser.parse_args()

    # Parse opponents
    opponents = args.opponents.split(",") if args.opponents else None

    # Determine if varied or fixed
    if args.close:
        setup_name = "close"
        varied = False
    elif args.setup:
        setup_name = args.setup
        varied = False
    else:
        setup_name = None
        varied = args.varied

    analyze_ability(
        args.hero,
        allies=args.allies,
        opponents=opponents,
        games=args.games,
        seed=args.seed,
        varied=varied,
    )
