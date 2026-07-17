import { useState, useEffect } from 'react';
import { theme } from './theme';

interface HeroPlacement {
  class_name: string;
  pos: [number, number];
}

interface TeamSetup {
  heroes: HeroPlacement[];
}

interface SetupScreenProps {
  onPlay: (gameLog: any) => void;
}

const DEFAULT_GRID_SIZE = 6;

export function SetupScreen({ onPlay }: SetupScreenProps) {
  const [heroes, setHeroes] = useState<string[]>([]);
  const [teams, setTeams] = useState<TeamSetup[]>([
    { heroes: [] },
    { heroes: [] },
  ]);
  const [selectedTeam, setSelectedTeam] = useState<number>(0);
  const [selectedHero, setSelectedHero] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gridSize, setGridSize] = useState(DEFAULT_GRID_SIZE);

  useEffect(() => {
    fetch('/heroes')
      .then((r) => r.json())
      .then(setHeroes)
      .catch(() => setError('Failed to load hero list'));
  }, []);

  // Show all heroes — duplicates are allowed
  const handleGridClick = (x: number, y: number) => {
    if (!selectedHero) return;
    const team = teams[selectedTeam];
    if (team.heroes.some((p) => p.pos[0] === x && p.pos[1] === y)) return;
    setTeams((prev) => {
      const next = [...prev];
      next[selectedTeam] = {
        heroes: [...next[selectedTeam].heroes, { class_name: selectedHero, pos: [x, y] as [number, number] }],
      };
      return next;
    });
    setSelectedHero(null);
  };

  const removeHero = (teamIdx: number, index: number) => {
    setTeams((prev) => {
      const next = [...prev];
      next[teamIdx] = {
        heroes: next[teamIdx].heroes.filter((_, i) => i !== index),
      };
      return next;
    });
  };

  const handlePlay = async () => {
    if (teams[0].heroes.length === 0 || teams[1].heroes.length === 0) {
      setError('Both teams need at least one hero.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/run-game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed: Math.floor(Math.random() * 100000),
          grid_size: gridSize,
          teams: teams.map((t) => ({ heroes: t.heroes })),
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to run game');
      }
      const gameLog = await response.json();
      onPlay(gameLog);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const isOccupied = (x: number, y: number) => {
    for (const team of teams) {
      if (team.heroes.some((p) => p.pos[0] === x && p.pos[1] === y)) return true;
    }
    return false;
  };

  const getEntityAt = (x: number, y: number) => {
    for (let t = 0; t < teams.length; t++) {
      const found = teams[t].heroes.find((p) => p.pos[0] === x && p.pos[1] === y);
      if (found) return { ...found, team: t };
    }
    return null;
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1 style={{ marginBottom: '20px', color: theme.fg.primary }}>Game Setup</h1>

      <div style={{ display: 'flex', gap: '20px', alignItems: 'flex-start' }}>
        {/* Hero Roster: always shows all heroes regardless of placement */}
        <div style={{
          width: '220px',
          border: `1px solid ${theme.borders.gridLine}`,
          borderRadius: '8px',
          padding: '12px',
          background: theme.bg.roster,
        }}>
          <h3 style={{ margin: '0 0 10px', color: theme.fg.placeholder }}>Hero Roster</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {heroes.map((hero, idx) => (
              <button
                key={`${hero}-${idx}`}
                onClick={() => setSelectedHero(selectedHero === hero ? null : hero)}
                style={{
                  padding: '6px 10px',
                  border: `2px solid ${selectedHero === hero ? theme.team[selectedTeam as 0 | 1] : theme.borders.gridLine}`,
                  borderRadius: '4px',
                  background: selectedHero === hero ? theme.bg.gridCellHover : theme.bg.gridCell,
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontSize: '14px',
                  color: theme.fg.placeholder,
                }}
              >
                {hero}
              </button>
            ))}
          </div>
          {selectedHero && (
            <p style={{ fontSize: '12px', color: theme.fg.placeholder, margin: '8px 0 0' }}>
              Click a grid cell to place {selectedHero}
            </p>
          )}
        </div>

        {/* Grid */}
        <div>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <label style={{ fontSize: '13px', color: theme.fg.placeholder, marginRight: '4px' }}>
              Grid:{' '}
              <select
                value={gridSize}
                onChange={(e) => setGridSize(Number(e.target.value))}
                style={{
                  padding: '2px 6px',
                  borderRadius: '4px',
                  border: `1px solid ${theme.borders.gridLine}`,
                  fontSize: '13px',
                }}
              >
                {[5, 6, 7, 8, 9, 10].map(s => (
                  <option key={s} value={s}>{s}×{s}</option>
                ))}
              </select>
            </label>
            {([0, 1] as const).map((t) => (
              <button
                key={t}
                onClick={() => { setSelectedTeam(t); setSelectedHero(null); }}
                style={{
                  padding: '6px 14px',
                  borderRadius: '4px',
                  border: `2px solid ${theme.team[t]}`,
                  background: selectedTeam === t ? theme.team[t] : theme.bg.gridCell,
                  color: selectedTeam === t ? theme.fg.bright : theme.team[t],
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '14px',
                }}
              >
                Team {t + 1} ({teams[t].heroes.length})
              </button>
            ))}
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${gridSize}, 60px)`,
            gridTemplateRows: `repeat(${gridSize}, 60px)`,
            gap: '2px',
            border: `3px solid ${theme.borders.gridBorder}`,
            borderRadius: '4px',
            background: theme.bg.grid,
            padding: '2px',
          }}>
            {Array.from({ length: gridSize * gridSize }, (_, i) => {
              const x = i % gridSize;
              const y = Math.floor(i / gridSize);
              const entity = getEntityAt(x, y);
              const occupied = isOccupied(x, y);

              return (
                <div
                  key={i}
                  onClick={() => !occupied && handleGridClick(x, y)}
                  style={{
                    width: '60px',
                    height: '60px',
                    border: `1px solid ${theme.borders.gridLine}`,
                    borderRadius: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: occupied ? 'default' : 'pointer',
                    background: entity
                      ? theme.team[entity.team as 0 | 1]
                      : selectedHero
                        ? theme.bg.gridCellHover
                        : theme.bg.gridCell,
                    color: entity ? theme.fg.bright : theme.fg.placeholder,
                    fontSize: '11px',
                    fontWeight: entity ? 'bold' : 'normal',
                    textAlign: 'center',
                    opacity: entity ? 1 : 0.6,
                    transition: 'background 0.15s',
                    padding: '2px',
                    overflow: 'hidden',
                    position: 'relative',
                  }}
                >
                  {entity ? (
                    <span style={{ lineHeight: 1.2 }}>{entity.class_name}</span>
                  ) : (
                    <span style={{ fontSize: '10px' }}>{x},{y}</span>
                  )}
                </div>
              );
            })}
          </div>

          {error && (
            <p style={{ color: theme.accent.hit, marginTop: '8px', fontSize: '14px' }}>{error}</p>
          )}
        </div>

        {/* Team Roster */}
        <div style={{ width: '200px' }}>
          {([0, 1] as const).map((t) => (
            <div
              key={t}
              style={{
                border: `2px solid ${theme.team[t]}`,
                borderRadius: '8px',
                padding: '10px',
                marginBottom: '10px',
                background: t === selectedTeam ? theme.bg.roster : theme.bg.gridCell,
              }}
            >
              <h4 style={{ margin: '0 0 6px', color: theme.team[t] }}>Team {t + 1}</h4>
              {teams[t].heroes.length === 0 ? (
                <p style={{ fontSize: '12px', color: theme.fg.placeholder, margin: 0 }}>Empty</p>
              ) : (
                <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                  {teams[t].heroes.map((h, i) => (
                    <li
                      key={i}
                      style={{
                        fontSize: '13px',
                        padding: '2px 0',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        color: theme.fg.placeholder,
                      }}
                    >
                      <span>
                        {h.class_name} [{h.pos[0]},{h.pos[1]}]
                      </span>
                      <button
                        onClick={() => removeHero(t, i)}
                        style={{
                          border: 'none',
                          background: 'none',
                          cursor: 'pointer',
                          color: theme.accent.danger,
                          fontSize: '14px',
                          padding: '0 4px',
                        }}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: '20px' }}>
        <button
          onClick={handlePlay}
          disabled={loading || teams[0].heroes.length === 0 || teams[1].heroes.length === 0}
          style={{
            padding: '12px 36px',
            fontSize: '18px',
            fontWeight: 'bold',
            borderRadius: '8px',
            border: 'none',
            background: loading ? theme.bg.surfaceHover : theme.accent.primary,
            color: theme.fg.bright,
            cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading ? 'Running...' : '▶ Play'}
        </button>
      </div>
    </div>
  );
}
