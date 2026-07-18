#!/usr/bin/env python3
"""
Quick-play harness: set up a game, run it, print readable results.
Usage:
    python quick_play.py                                    # Symmetra vs Axe
    python quick_play.py --seed 7                           # Specific seed
    python quick_play.py --hero0 Symmetra --hero1 Axe       # Named heroes
    python quick_play.py --grid 6 --turns 5                 # Verbose first 5 turns
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
    parser.add_argument("--turns", type=int, default=0,
                        help="Show raw events for the first N turns (0=skip)")
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

    # ── Debug: show raw events for first N turns ──
    if args.turns > 0:
        print(f"─── First {args.turns} turns ───")
        for i, entry in enumerate(log.logs[:args.turns]):
            state = entry.state
            # Snapshot: which entities are where
            entities_at = {}
            for es in state.entities:
                if es.pos:
                    key = f"({es.pos[0]},{es.pos[1]})"
                    entities_at.setdefault(key, []).append(es.name)
            print(f"\n  Turn {i}: round={state.round_num} team={state.current_team}")
            # Grid map
            for y in range(args.grid - 1, -1, -1):
                row = f"    {y}|"
                for x in range(args.grid):
                    key = f"({x},{y})"
                    if key in entities_at:
                        names = entities_at[key]
                        # abbreviate to first letter(s)
                        abbr = ",".join(n[:4] for n in names)
                        row += f" {abbr:4s}"
                    else:
                        row += " .   "
                print(row)
            print("     " + "─" * (args.grid * 5))
            print("     " + "".join(f"{x:5d}" for x in range(args.grid)))

            # Events this turn
            for ev in entry.events:
                parts = []
                if ev.type:
                    parts.append(ev.type)
                if ev.ability_name:
                    parts.append(ev.ability_name)
                if ev.amount:
                    parts.append(f"amt={ev.amount}")
                if ev.source_id is not None:
                    src = e.get_entity_by_id(ev.source_id)
                    parts.append(f"src={src.name if src else ev.source_id}")
                if ev.target_id is not None:
                    tgt = e.get_entity_by_id(ev.target_id)
                    parts.append(f"tgt={tgt.name if tgt else ev.target_id}")
                if ev.target_pos:
                    parts.append(f"at=({ev.target_pos[0]},{ev.target_pos[1]})")
                print(f"    {' '.join(parts)}" if parts else "")
        print()

    # ── Final state ──
    print("─── Final State ───")
    for ent in sorted(e.entities, key=lambda x: x.id):
        entry = f"  {ent.name}: {ent.hp}/{ent.max_hp}"
        if ent.pos is not None:
            entry += f"  @({ent.pos.x},{ent.pos.y})"
        else:
            entry += "  (dead)"
        entry += f"  team={ent.team}"
        print(entry)
    print()

    # ── Ability use summary ──
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
