# ModValue Integration Report

I have updated `QuerySpeed`, `QueryDefense`, and `QueryCrit` to use `ModValue` for accumulating modifiers, rather than evaluating as raw integers directly. 

As a result, `Entity.get_defense` and `Entity.get_crit` will now properly pull `.value` after queries resolve, and modifier implementations like `Slow` can use `.add(...)` on the query result instead of direct integer manipulation. 

*(Note: Other standard events like `DamageEvent`, `HealEvent`, `PushEvent`, and `PullEvent` were already initializing their quantities using `ModValue`, but you may want to review modifiers interacting with them throughout the codebase to ensure they utilize `.add()` or `.mult()` instead of direct assignment!)*
