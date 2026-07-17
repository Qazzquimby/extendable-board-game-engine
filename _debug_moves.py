"""Debug script to trace move path generation and ChangeLocationEvent emission."""
import sys
sys.path.insert(0, 'backend/src')
sys.path.insert(0, 'backend')

from src.engine import Engine, EventQueue
from src.entities import Entity, TeamMember, Hero
from src.grid import Grid
from src.choices import PlausibleMoveAndAction
from src.events import ChangeLocationEvent
from src.hero_registry import HeroRegistry

# Monkey-patch ChangeLocationEvent constructor
_orig_cls_init = ChangeLocationEvent.__init__
def _patched_cls_init(self, **kwargs):
    print(f"  ChangeLocationEvent(subject={kwargs.get('subject')}, new_pos={kwargs.get('new_pos')})", flush=True)
    _orig_cls_init(self, **kwargs)
ChangeLocationEvent.__init__ = _patched_cls_init

# Monkey-patch EventQueue.enqueue
_orig_enqueue = EventQueue.enqueue
def _patched_enqueue(self, event):
    if isinstance(event, ChangeLocationEvent):
        print(f"  ENQUEUE ChangeLocationEvent subject_id={event.subject_id} new_pos={event.new_pos}", flush=True)
    return _orig_enqueue(self, event)
EventQueue.enqueue = _patched_enqueue

# Monkey-patch Engine.step
_orig_step = Engine.step
def _patched_step(self, action, action_idx):
    import pyturnbased as ptb
    action_name = getattr(action, 'ability', None)
    if action_name:
        action_name = action_name.name
    move_path = getattr(action, 'move_path', None)
    mp_len = len(move_path) if move_path else 0
    actor = getattr(action, 'actor', self.active_entity)
    actor_name = actor.name if actor else '?'
    print(f"\n### STEP: {actor_name} action={action_name} move_path=({mp_len})", flush=True)
    if move_path:
        for i, p in enumerate(move_path):
            print(f"    path[{i}] = {p} (type={type(p).__name__})", flush=True)
    return _orig_step(self, action, action_idx)
Engine.step = _patched_step

# Run a minimal game
registry = HeroRegistry()
heroes = [registry.get('Axe'), registry.get('MeleeHero')]
team1 = TeamMember(heroes=[Hero(hero_cls=heroes[0], pos=(0,0))])
team2 = TeamMember(heroes=[Hero(hero_cls=heroes[1], pos=(4,3))])

engine = Engine(teams=[team1, team2], grid=Grid(6,6), seed=42, hero_registry=registry)
result = engine.run_game()
print(f"\nTotal log entries: {len(result.logs)}")
for i, entry in enumerate(result.logs[:4]):
    evt_types = [e.type for e in entry.events]
    print(f"  [{i}] events={evt_types}")
