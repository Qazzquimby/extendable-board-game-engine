#!/usr/bin/env python3
"""
Ability usage analyzer.

Runs N games with a specific hero and reports which abilities are never used.
Output goes to analyze_output.txt (UTF-8).

Usage:
    python analyze_ability_usage.py Soldier76 --games 10 --opponent Axe
    python analyze_ability_usage.py Scout --games 5 --opponent Reinhardt --seed 42
"""

import sys
import argparse
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


def run_game(hero_cls, hero_name, opponent_cls, opponent_name, seed, grid_size=6):
    g = Grid(grid_size, grid_size)
    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=seed)

    hero = hero_cls(engine=e, pos=Point(0, 2), team=0)
    opponent = opponent_cls(engine=e, pos=Point(grid_size - 1, 2), team=1)

    e.finalize_setup()
    log = e.run_game()

    # Collect ability uses from action_logs
    usage = defaultdict(int)
    for entry in log.logs:
        for al in entry.action_logs:
            al_lower = al.lower()
            for ab in hero.abilities:
                ab_lower = ab.name.lower()
                if ab_lower in al_lower and (' uses ' in al_lower or ' used ' in al_lower):
                    usage[ab.name] += 1

    return dict(usage), log, hero


def analyze_ability(hero_name, opponent_name='Axe', games=10, seed=42):
    outpath = Path(__file__).resolve().parent / 'analyze_output.txt'
    with open(outpath, 'w', encoding='utf-8') as outf:
        def w(msg):
            print(msg)
            outf.write(msg + '\n')
            outf.flush()

        try:
            hero_cls = get_hero_class(hero_name)
        except KeyError:
            avail = list_heroes()
            w(f"Unknown hero '{hero_name}'. Available: {avail}")
            return

        try:
            opponent_cls = get_hero_class(opponent_name)
        except KeyError:
            avail = list_heroes()
            w(f"Unknown opponent '{opponent_name}'. Available: {avail}")
            return

        # Instantiate once to get ability names
        temp_e = Engine(grid=Grid(6, 6), agents={0: RuleBasedAgent(), 1: RuleBasedAgent()}, seed=0)
        temp_h = hero_cls(engine=temp_e, pos=Point(0, 0), team=0)
        ability_names = [ab.name for ab in temp_h.abilities if ab.name != 'Do Nothing']
        total_uses = {name: 0 for name in ability_names}
        games_with_use = {name: 0 for name in ability_names}

        w(f"\n=== Analyzing {hero_name} vs {opponent_name} ({games} games) ===\n")

        for game_idx in range(games):
            current_seed = seed + game_idx
            try:
                usage, _log, hero = run_game(hero_cls, hero_name, opponent_cls, opponent_name, current_seed)
            except Exception as e:
                w(f"  Game {game_idx+1} (seed={current_seed}): CRASHED - {e}")
                continue

            winner = getattr(_log, 'winner_team', '?')
            for name in ability_names:
                uses = usage.get(name, 0)
                total_uses[name] += uses
                if uses > 0:
                    games_with_use[name] += 1

            used_list = [n for n in ability_names if usage.get(n, 0) > 0]
            w(f"  Game {game_idx+1} (seed={current_seed}, winner=team {winner}): {used_list or 'NOTHING'}")

        w(f"\n--- Summary ---")
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
    parser = argparse.ArgumentParser(description="Analyze hero ability usage")
    parser.add_argument("hero", help="Hero class name to analyze")
    parser.add_argument("--opponent", default="Axe", help="Opponent hero class name")
    parser.add_argument("--games", type=int, default=10, help="Number of games to run")
    parser.add_argument("--seed", type=int, default=42, help="Base seed")
    args = parser.parse_args()
    analyze_ability(args.hero, args.opponent, args.games, args.seed)
