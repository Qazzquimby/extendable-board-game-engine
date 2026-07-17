import { useState, useEffect } from 'react';

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

const GRID_SIZE = 5;
const TEAM_COLORS = ['#4488ff', '#ff4444'];
const TEAM_LABELS = ['Blue Team', 'Red Team'];

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

  useEffect(() => {
    fetch('/heroes')
      .then((r) => r.json())
      .then(setHeroes)
      .catch(() => setError('Failed to load hero list'));
  }, []);

  const availableHeroes = heroes.filter(
    (h) =>
      !teams[0].heroes.some((p) => p.class_name === h) &&
      !teams[1].heroes.some((p) => p.class_name === h)
  );

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
          grid_size: GRID_SIZE,
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
      <h1 style={{ marginBottom: '20px' }}>Game Setup</h1>

      <div style={{ display: 'flex', gap: '20px', alignItems: 'flex-start' }}>
        {/* Hero Roster */}
        <div style={{
          width: '220px',
          border: '1px solid #ccc',
          borderRadius: '8px',
          padding: '12px',
          background: '#f8f8f8',
        }}>
          <h3 style={{ margin: '0 0 10px' }}>Hero Roster</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {availableHeroes.map((hero) => (
              <button
                key={hero}
                onClick={() => setSelectedHero(selectedHero === hero ? null : hero)}
                style={{
                  padding: '6px 10px',
                  border: `2px solid ${selectedHero === hero ? TEAM_COLORS[selectedTeam] : '#ddd'}`,
                  borderRadius: '4px',
                  background: selectedHero === hero ? '#eef' : 'white',
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontSize: '14px',
                }}
              >
                {hero}
              </button>
            ))}
          </div>
          {selectedHero && (
            <p style={{ fontSize: '12px', color: '#666', margin: '8px 0 0' }}>
              Click a grid cell to place {selectedHero}
            </p>
          )}
        </div>

        {/* Grid */}
        <div>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
            {[0, 1].map((t) => (
              <button
                key={t}
                onClick={() => { setSelectedTeam(t); setSelectedHero(null); }}
                style={{
                  padding: '6px 14px',
                  borderRadius: '4px',
                  border: `2px solid ${TEAM_COLORS[t]}`,
                  background: selectedTeam === t ? TEAM_COLORS[t] : 'white',
                  color: selectedTeam === t ? 'white' : TEAM_COLORS[t],
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '14px',
                }}
              >
                {TEAM_LABELS[t]} ({teams[t].heroes.length})
              </button>
            ))}
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${GRID_SIZE}, 60px)`,
            gridTemplateRows: `repeat(${GRID_SIZE}, 60px)`,
            gap: '2px',
            border: '3px solid #aaa',
            borderRadius: '4px',
            background: '#e8e8e8',
            padding: '2px',
          }}>
            {Array.from({ length: GRID_SIZE * GRID_SIZE }, (_, i) => {
              const x = i % GRID_SIZE;
              const y = Math.floor(i / GRID_SIZE);
              const entity = getEntityAt(x, y);
              const occupied = isOccupied(x, y);

              return (
                <div
                  key={i}
                  onClick={() => !occupied && handleGridClick(x, y)}
                  style={{
                    width: '60px',
                    height: '60px',
                    border: '1px solid #ccc',
                    borderRadius: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: occupied ? 'default' : 'pointer',
                    background: entity
                      ? TEAM_COLORS[entity.team]
                      : selectedHero
                        ? '#f0f8ff'
                        : 'white',
                    color: entity ? 'white' : '#999',
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
            <p style={{ color: 'red', marginTop: '8px', fontSize: '14px' }}>{error}</p>
          )}
        </div>

        {/* Team Roster */}
        <div style={{ width: '200px' }}>
          {[0, 1].map((t) => (
            <div
              key={t}
              style={{
                border: `2px solid ${TEAM_COLORS[t]}`,
                borderRadius: '8px',
                padding: '10px',
                marginBottom: '10px',
                background: t === selectedTeam ? '#f0f4ff' : 'white',
              }}
            >
              <h4 style={{ margin: '0 0 6px', color: TEAM_COLORS[t] }}>{TEAM_LABELS[t]}</h4>
              {teams[t].heroes.length === 0 ? (
                <p style={{ fontSize: '12px', color: '#434343', margin: 0 }}>Empty</p>
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
                          color: '#c00',
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
            background: loading ? '#ccc' : '#28a745',
            color: 'white',
            cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading ? 'Running...' : '▶ Play'}
        </button>
      </div>
    </div>
  );
}
