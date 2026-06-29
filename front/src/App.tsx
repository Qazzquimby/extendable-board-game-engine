import { useState, useEffect } from 'react';
import { GameLog } from './types';
import PhaserComponent from './PhaserComponent';

function App() {
  const [games, setGames] = useState<GameLog[]>([]);
  const [currentGameIndex, setCurrentGameIndex] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);

  const currentGame = games[currentGameIndex];
  const log = currentGame?.logs || [];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        setCurrentStep((s) => Math.min(log.length - 1, s + 1));
      } else if (e.key === 'ArrowLeft') {
        setCurrentStep((s) => Math.max(0, s - 1));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [log.length]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const content = e.target?.result;
          if (typeof content === 'string') {
            const jsonGames = JSON.parse(content);
            if (Array.isArray(jsonGames)) {
                setGames(jsonGames);
                setCurrentGameIndex(0);
                setCurrentStep(0);
            } else {
                alert("Log file is not a JSON array of games.");
            }
          }
        } catch (error) {
          console.error("Error parsing JSON log file:", error);
          alert("Failed to parse log file. Is it valid JSON?");
        }
      };
      reader.readAsText(file);
    }
  };

  const currentLogEntry = log[currentStep];
  const stateToRender = currentLogEntry?.before_state;

  const getDestination = (logEntry: typeof currentLogEntry) => {
    if (logEntry.action.move_path?.length) {
      return logEntry.action.move_path[logEntry.action.move_path.length - 1];
    } else {
      return 'same space'
    }
  }

  return (
    <div>
      <h1>Game Log Visualizer</h1>
      <input type="file" accept=".json,.jsonl" onChange={handleFileChange} />
      {games.length > 0 && (
          <div style={{display: 'flex'}}>
            <div style={{
              width: '300px',
              marginLeft: '20px',
              borderLeft: '1px solid #ccc',
              paddingLeft: '20px',
              height: '95vh',
              overflowY: 'auto'
            }}>
              <h2>Turn Log</h2>
              {currentLogEntry?.messages?.length ? (
                  currentLogEntry.messages.map((msg, index) => (
                      <p key={index} style={{
                        margin: '2px 0',
                        fontSize: '14px',
                        whiteSpace: 'pre-wrap'
                      }}>{msg}</p>
                  ))
              ) : (
                  <p>No log messages for this turn.</p>
              )}
            </div>
            <div style={{flex: 1}}>
              <div style={{margin: '10px 0'}}>
                <label>
                  Select Game:
                  <select
                      value={currentGameIndex}
                      onChange={(e) => {
                        setCurrentGameIndex(Number(e.target.value));
                        setCurrentStep(0);
                      }}
                      style={{marginLeft: '10px'}}
                  >
                    {games.map((g, i) => (
                        <option key={i}
                                value={i}>Game {i + 1} {g.winner_team !== null ? `(Team ${g.winner_team} Won)` : '(Tie)'}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div>
                <button onClick={() => setCurrentStep(s => Math.max(0, s - 1))}
                        disabled={currentStep === 0}>
                  Previous
                </button>
                <span> Step {currentStep} / {log.length - 1} </span>
                <button onClick={() => setCurrentStep(s => Math.min(log.length - 1, s + 1))}
                        disabled={currentStep === log.length - 1}>
                  Next
                </button>
              </div>
              {currentLogEntry && 'action' in currentLogEntry && currentLogEntry.action.actor !== -1 && (
                  <div>
                    <h3>Action</h3>
                    <p>Actor: {stateToRender?.entities.find(e => e.id === currentLogEntry.action.actor)?.name || currentLogEntry.action.actor}</p>
                    <p>"{currentLogEntry.action.movement_name}" to
                      [{String(getDestination(currentLogEntry))}], then
                      performing {currentLogEntry.action.ability}{currentLogEntry.action.target !== null ? ` on ${stateToRender?.entities.find(e => e.id === currentLogEntry.action.target)?.name || currentLogEntry.action.target}` : ''}.</p>
                  </div>
              )}
              {currentLogEntry && 'action' in currentLogEntry && currentLogEntry.action.actor === -1 && (
                  <div>
                    <h3>Game Over</h3>
                  </div>
              )}
              <div>
                {stateToRender &&
                    <PhaserComponent engineState={stateToRender} action={currentLogEntry?.action}/>}
              </div>
              <div style={{ marginTop: '20px', marginBottom: '20px' }}>
                <h3>Entities in Current State</h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                  {stateToRender?.entities.map(e => (
                    <div key={e.id} style={{ border: '1px solid #ccc', padding: '5px', borderRadius: '4px', fontSize: '12px', width: '200px' }}>
                      <strong>{e.name} (Team {e.team === 1 ? 'Red' : 'Blue'})</strong><br/>
                      HP: {e.hp}<br/>
                      Pos: {e.pos ? `[${e.pos[0]}, ${e.pos[1]}]` : 'None'}<br/>
                      {e.modifiers && e.modifiers.length > 0 && (
                        <div style={{ marginTop: '4px', color: '#666' }}>
                          Mods: {e.modifiers.join(', ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
      )}
    </div>
  );
}

export default App;
