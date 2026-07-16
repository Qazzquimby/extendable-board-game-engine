import { useState, useEffect, useCallback } from 'react';
import { GameLog, EngineState } from './types';
import PhaserComponent from './PhaserComponent';

interface PlaybackScreenProps {
  gameLog: GameLog;
  onBack: () => void;
}

export function PlaybackScreen({ gameLog, onBack }: PlaybackScreenProps) {
  const logs = gameLog?.logs || [];
  const [currentStep, setCurrentStep] = useState(0);

  const goBack = useCallback(() => setCurrentStep((s) => Math.max(0, s - 1)), []);
  const goForward = useCallback(
    () => setCurrentStep((s) => Math.min(logs.length - 1, s + 1)),
    [logs.length]
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') goForward();
      else if (e.key === 'ArrowLeft') goBack();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [goBack, goForward]);

  const currentLogEntry = logs[currentStep];
  const stateToRender: EngineState | undefined = currentLogEntry?.before_state;

  const getDestination = (logEntry: typeof currentLogEntry) => {
    if (logEntry?.action.move_path?.length) {
      return logEntry.action.move_path[logEntry.action.move_path.length - 1];
    }
    return 'same space';
  };

  return (
    <div>
      <div style={{ padding: '10px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onBack}
          style={{
            padding: '6px 14px',
            borderRadius: '4px',
            border: '1px solid #ccc',
            background: 'white',
            cursor: 'pointer',
            fontSize: '14px',
          }}
        >
          ← Setup
        </button>
        <h2 style={{ margin: 0, fontSize: '16px' }}>
          {gameLog.winner_team !== null
            ? `Team ${gameLog.winner_team === 1 ? 'Red' : 'Blue'} Won!`
            : 'Game Over (Tie)'}
        </h2>
      </div>

      <div style={{ display: 'flex' }}>
        {/* Written log sidebar */}
        <div
          style={{
            width: '300px',
            marginLeft: '20px',
            borderLeft: '1px solid #ccc',
            paddingLeft: '20px',
            height: '90vh',
            overflowY: 'auto',
          }}
        >
          <h3>Turn Log</h3>
          {currentLogEntry?.messages?.length ? (
            currentLogEntry.messages.map((msg, i) => (
              <p
                key={i}
                style={{
                  margin: '2px 0',
                  fontSize: '14px',
                  whiteSpace: 'pre-wrap',
                }}
              >
                {msg}
              </p>
            ))
          ) : (
            <p>No log messages for this turn.</p>
          )}
        </div>

        {/* Main view */}
        <div style={{ flex: 1 }}>
          <div style={{ margin: '10px 0' }}>
            <button onClick={goBack} disabled={currentStep === 0} style={{ marginRight: '10px' }}>
              ◀ Previous
            </button>
            <span>
              Step {currentStep} / {logs.length - 1}
            </span>
            <button
              onClick={goForward}
              disabled={currentStep === logs.length - 1}
              style={{ marginLeft: '10px' }}
            >
              Next ▶
            </button>
          </div>

          {currentLogEntry && 'action' in currentLogEntry && currentLogEntry.action.actor !== -1 && (
            <div>
              <h3>Action</h3>
              <p>
                Actor:{' '}
                {stateToRender?.entities.find((e) => e.id === currentLogEntry.action.actor)
                  ?.name || currentLogEntry.action.actor}
              </p>
              <p>
                "{currentLogEntry.action.movement_name}" to [{String(getDestination(currentLogEntry))}],
                then performing {currentLogEntry.action.ability}
                {currentLogEntry.action.target !== null
                  ? ` on ${stateToRender?.entities.find((e) => e.id === currentLogEntry.action.target)?.name || currentLogEntry.action.target}`
                  : ''}
                .
              </p>
            </div>
          )}

          {currentLogEntry && 'action' in currentLogEntry && currentLogEntry.action.actor === -1 && (
            <div>
              <h3>Game Over</h3>
            </div>
          )}

          {stateToRender && <PhaserComponent engineState={stateToRender} action={currentLogEntry?.action} />}

          <div style={{ marginTop: '20px', marginBottom: '20px' }}>
            <h3>Entities</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              {stateToRender?.entities.map((e) => (
                <div
                  key={e.id}
                  style={{
                    border: '1px solid #ccc',
                    padding: '5px',
                    borderRadius: '4px',
                    fontSize: '12px',
                    width: '200px',
                  }}
                >
                  <strong>
                    {e.name} (Team {e.team === 1 ? 'Red' : 'Blue'})
                  </strong>
                  <br />
                  HP: {e.hp}
                  <br />
                  Pos: {e.pos ? `[${e.pos[0]}, ${e.pos[1]}]` : 'None'}
                  <br />
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
    </div>
  );
}
