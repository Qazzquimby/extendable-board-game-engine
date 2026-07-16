# 02 — Setup screen + API integration

**What to build:** A React setup screen with a hero roster (fetched from /heroes), team assignment, grid placement, and a "Play" button. On play, calls POST /run-game and transitions to the existing playback visualizer. Replaces file-drag-drop workflow end-to-end.

**Blocked by:** 01 — Backend API server

**Status:** ready-for-agent

- [x] SetupScreen component with hero roster, team assignment, grid placement
- [x] PlaybackScreen extracted from previous App.tsx
- [x] App.tsx manages mode switching (setup → playback → back)
- [x] Vite proxy config for /heroes and /run-game
- [x] No log file management — click Play, see the game
