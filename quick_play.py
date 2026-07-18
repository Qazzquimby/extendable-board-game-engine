#!/usr/bin/env python3
"""
Quick-play harness: set up a game, run it, print a readable result summary.
Usage:
    python quick_play.py                          # Symmetra vs Axe (defaults)
    python quick_play.py --seed 7                 # Specific seed
    python quick_play.py --hero0 Symmetra --hero1 Axe --grid 6
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend", "src"))

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--grid", type=int, default=6)
    parser.add_argument("--hero0", default="Symmetra")
    parser.add_argument("--hero1", default="Axe")
    args = parser.parse_args()

    from engine import Engine, RuleBasedAgent
    from grid import Grid
    from point import Point
    from hero_registry import get_hero_class

    g = Grid(args.grid, args.grid)

    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    e = Engine(grid=g, agents=agents, seed=args.seed)

    Hero0 = get_hero_class(args.hero0)
    Hero1 = get_hero_class(args.hero1)

    h0 = Hero0(engine=e, pos=Point(0, 0), team=0)
    h1 = Hero1(engine=e, pos=Point(args.grid - 1, 0), team=1)

    e.finalize_setup()
    log = e.run_game()

    print(f"Game: {args.hero0} (team 0) vs {args.hero1} (team 1)")
    print(f"Grid: {args.grid}x{args.grid},  seed: {args.seed}")
    print(f"Turns: {len(log.logs)}")
    print(f"Winner: team {log.winner_team} ({args.hero0 if log.winner_team == 0 else args.hero1 if log.winner_team == 1 else 'draw'})")
    print()

    # Final state
    team0_alive = []
    team1_alive = []
    for ent in sorted(e.entities, key=lambda x: x.id):
        entry = f"  {ent.name}: {ent.hp}/{ent.max_hp}"
        if ent.pos is not None:
            entry += f"  @({ent.pos.x},{ent.pos.y})"
        else:
            entry += "  (dead)"
        if ent.team == 0:
            team0_alive.append(entry)
        else:
            team1_alive.append(entry)

    print("Team 0:")
    for line in team0_alive:
        print(line)
    print("Team 1:")
    for line in team1_alive:
        print(line)
    print()

    # Ability use summary
    from collections import Counter
    ability_uses = Counter()
    damage_dealt = Counter()
    for entry in log.logs:
        for ev in entry.events:
            if ev.ability_name:
                ability_uses[ev.ability_name] += 1
            if ev.type == "damage" and ev.amount and ev.source_id:
                src = e.get_entity_by_id(ev.source_id)
                if src:
                    damage_dealt[src.name] += ev.amount

    print("Ability uses:")
    for ability, count in ability_uses.most_common():
        print(f"  {ability}: {count}")
    print()

    print("Damage dealt:")
    for name, dmg in damage_dealt.most_common():
        print(f"  {name}: {dmg}")


if __name__ == "__main__":
    main()
