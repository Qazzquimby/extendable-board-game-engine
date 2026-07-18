# Reinhardt Charge: damage all for 4, not 6/1; position adjacent

**Status:** ready-for-agent
**Severity:** high
**Reporter:** user

## Problems

1. Charge deals 6 damage to first enemy hit, 1 to rest. Should be a single instance of 4 damage to everyone pushed.
2. Reinhardt doesn't end adjacent to pushed entities — only moved one space from start.

## Fix needed

1. All enemies in path take 4 damage (same amount to all)
2. Reinhardt ends adjacent to the nearest pushed entity's FINAL position (after they've been pushed)
