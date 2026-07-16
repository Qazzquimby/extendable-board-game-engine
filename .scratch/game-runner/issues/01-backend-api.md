# 01 — Backend API server

**What to build:** A FastAPI server with `POST /run-game` (accepts hero config, returns GameLog) and `GET /heroes` (returns available hero classes). Testable via curl or TestClient.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] FastAPI app with /heroes and /run-game endpoints
- [x] Validate hero classes, positions, and grid bounds
- [x] pytest TestClient tests for valid/invalid/error/deterministic cases
- [x] All heroes discoverable (fixed broken imports in reinhardt.py and spy.py)

**Commit:** 6721bbc
