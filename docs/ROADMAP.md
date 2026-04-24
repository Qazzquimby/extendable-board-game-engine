# Development Roadmap

*All features must be tested and type hinted.*

- **Action Space Definition:** Create a discrete, enumerable action space for player agents.
Add 'plausible action' generation for AI, enumerating reasonable movements+action targetings given the hero and ability's constraints.
Combinations of move destination and ability targets. Move destination takes from
- As close as possible to [enemy]
- As close as possible to [enemy] while being [ally] and [that enemy]
- As close as possible to [objective]
- As far as possible from [enemy] while being in range of current ability
Each for all targets and deduplicated. There's a PlausibleAction for each destination+distinct set of ability targets.
Some abilities don't have targets or have multiple/an area effect. Sometimes a character can't move. Move speed is limited.
PlausibleActions are an AI aide. Naturally they're composed of smaller effects. A PlausibleAction could potentially be interrupted, in which case a new PlausibleAction would be calculated from the new state.

- **State Serialization:** Implement deep copying and JSON/dict export of the full game state (entities, positions, modifiers, hp).
- **Event Logging:** Build a history/replay system that logs all events and state changes for debugging and training analysis.
Save game logs in an interpretable state which can be later visualized.

Produce a log visualizer. Aim to stick loosely to these dependencies

    "@colyseus/command": "^0.3.1",
    "@colyseus/monitor": "^0.17.7",
    "@colyseus/redis-driver": "^0.17.6",
    "@colyseus/redis-presence": "^0.17.6",
    "@colyseus/schema": "^4.0.20",
    "@colyseus/sdk": "^0.17.41",
    "@colyseus/tools": "^0.17.18",
    "@colyseus/ws-transport": "^0.17.9",
    "@reduxjs/toolkit": "^2.3.0",
    "colyseus": "^0.17.8",
    "cors": "^2.8.5",
    "cron": "^4.3.1",
    "d3": "^7.8.5",
    "dayjs": "^1.11.13",
    "discord.js": "^14.26.3",
    "dotenv": "^17.4.2",
    "express": "^5.2.1",
    "express-basic-auth": "^1.2.0",
    "fast-xml-parser": "^5.7.1",
    "firebase": "^10.0.0",
    "firebase-admin": "^13.8.0",
    "firebaseui": "^6.1.0",
    "fs-extra": "^11.2.0",
    "graceful-fs": "^4.2.10",
    "helmet": "^8.0.0",
    "html2canvas": "^1.4.1",
    "i18next": "^26.0.6",
    "i18next-browser-languagedetector": "^8.0.0",
    "i18next-http-backend": "^3.0.5",
    "immer": "^11.0.1",
    "jimp": "^1.6.0",
    "loglevel": "^1.8.1",
    "markdown-to-config": "^0.4.0",
    "marked": "^18.0.2",
    "matter-js": "^0.20.0",
    "mongoose": "^9.4.1",
    "phaser": "^3.90.0",
    "phaser-animated-tiles-phaser3.5": "^2.0.5",
    "phaser3-rex-plugins": "^1.80.6",
    "pm2-prom-module-client": "^1.0.3",
    "prom-client": "^15.1.1",
    "react": "^19.0.0",
    "react-circular-progressbar": "^2.1.0",
    "react-dom": "^19.0.0",
    "react-i18next": "^16.5.0",
    "react-pro-sidebar": "^1.1.0",
    "react-redux": "^9.1.2",
    "react-router": "^7.14.1",
    "react-tabs": "^6.0.2",
    "react-toastify": "^11.1.0",
    "react-tooltip": "^5.30.0",
    "react-virtualized-auto-sizer": "^2.0.3",
    "react-window": "^2.2.7",
    "recharts": "^3.6.0"

- **Determinism & RNG:** Centralize and seed all random number generation (attack rolls, crits) to ensure reproducible rollouts.
- **Event System Enhancements:** Add support for replacement events, deterministic ability ordering, and conditional modifiers.
