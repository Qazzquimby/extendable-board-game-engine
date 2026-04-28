# Development Roadmap

*All features must be tested and type hinted.*

Entities with same name seem to be taking actions from each other's locations? Looks eg one ranged hero teleporting on top of another and then moving from that location. "Stay" causes them to just teleport onto another unit
Example transcript
(Blue has two ranged heroes top left, red has a ranged and melee bottom right)
"Ranged hero blue performing do nothing on ranged hero blue (...) Movement stay to 0,0". We see an arrow between 0,0 to where the red ranged was, and the red ranged is moved to 0,0.
"Ranged hero blue performing do nothing on ranged hero blue. Movement stay to 0, 1". We see arrow from 0,1 to where red ranged started at the bottom right (not 0,0 where they appeared to move) and now red ranged is at 0,1.
Arrow is supposed to be between an entity and their target but 
Initial screen when loading logs is blank with nothing on the grid.
Entities with the same name and team need to be disambiguated in the logs and icon, probably with numbers (only if multiple of same entity on same team)
Should log movement before action since movement takes place first.