import { useState, useEffect, useCallback, useRef } from 'react';
import { GameLog, EngineState } from './types';
import PhaserComponent from './PhaserComponent';

interface PlaybackScreenProps {
  gameLog: GameLog;
  onBack: () => void;
}

export function PlaybackScreen({ gameLog, onBack }: PlaybackScreenProps) {
  const logs = gameLog?.logs || [];
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(800); // ms per step
  const logEndRef = useRef<HTMLDivElement>(null);

  const goBack = useCallback(() => setCurrentStep((s) => Math.max(0, s - 1)), []);
  const goForward = useCallback(
    () => setCurrentStep((s) => Math.min(logs.length - 1, s + 1)),
    [logs.length]
  );

  // Auto-play timer
  useEffect(() => {
    if (!isPlaying) return;
    const atEnd = currentStep >= logs.length - 1;
    if (atEnd) {
      setIsPlaying(false);
      return;
    }
    const timer = setTimeout(() => goForward(), speed);
    return () => clearTimeout(timer);
  }, [isPlaying, currentStep, speed, goForward, logs.length]);

  const togglePlay = useCallback(() => {
    if (currentStep >= logs.length - 1) {
      setCurrentStep(0); // restart
    }
    setIsPlaying((p) => !p);
  }, [currentStep, logs.length]);

  // Keyboard: arrows for step, space for play/pause
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') goForward();
      else if (e.key === 'ArrowLeft') goBack();
      else if (e.key === ' ') { e.preventDefault(); togglePlay(); }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [goBack, goForward, togglePlay]);

  // Auto-scroll log to bottom
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentStep]);

  const currentLogEntry = logs[currentStep];
  const stateToRender: EngineState | undefined = currentLogEntry?.before_state;

  const getDestination = (logEntry: typeof currentLogEntry) => {
    if (logEntry?.action.move_path?.length) {
      return logEntry.action.move_path[logEntry.action.move_path.length - 1];
    }
    return 'same space';
  };

  return (
    <div style={{ background: '#1a1a1a', color: '#eee', minHeight: '100vh', fontFamily: 'sans-serif' }}>
      {/* Top bar */}
      <div style={{
        padding: '8px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        borderBottom: '1px solid #333',
        background: '#222',
      }}>
        <button
          onClick={onBack}
          style={{
            padding: '6px 14px',
            borderRadius: '4px',
            border: '1px solid #555',
            background: '#333',
            color: '#eee',
            cursor: 'pointer',
            fontSize: '14px',
          }}
        >
          ← Setup
        </button>

        <button
          onClick={togglePlay}
          style={{
            padding: '6px 16px',
            borderRadius: '4px',
            border: 'none',
            background: isPlaying ? '#cc7a00' : '#28a745',
            color: 'white',
            cursor: 'pointer',
            fontSize: '16px',
            fontWeight: 'bold',
          }}
        >
          {isPlaying ? '⏸ Pause' : '▶ Auto-Play'}
        </button>

        <span style={{ fontSize: '14px', color: '#aaa' }}>
          Step {currentStep} / {logs.length - 1}
        </span>

        <span style={{ fontSize: '13px', color: '#666' }}>Speed:</span>
        <select
          value={speed}
          onChange={(e) => setSpeed(Number(e.target.value))}
          style={{
            padding: '4px 8px',
            borderRadius: '4px',
            border: '1px solid #555',
            background: '#333',
            color: '#eee',
            fontSize: '13px',
          }}
        >
          <option value={1500}>Slow</option>
          <option value={800}>Normal</option>
          <option value={400}>Fast</option>
          <option value={150}>Turbo</option>
        </select>

        <span style={{ fontSize: '13px', color: '#666' }}>Space: Play/Pause</span>

        <span style={{ marginLeft: 'auto', fontSize: '16px', color: '#ffd700' }}>
          {gameLog.winner_team !== null
            ? `🏆 Team ${gameLog.winner_team === 1 ? 'Red' : 'Blue'} Wins!`
            : 'Game Over (Tie)'}
        </span>
      </div>

      <div style={{ display: 'flex' }}>
        {/* Written log sidebar */}
        <div
          style={{
            width: '320px',
            borderRight: '1px solid #333',
            padding: '12px',
            height: 'calc(100vh - 52px)',
            overflowY: 'auto',
            background: '#1e1e1e',
            order: -1,
          }}
        >
          <h3 style={{ margin: '0 0 8px', fontSize: '14px', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px' }}>
            Turn Log
          </h3>
          {currentLogEntry?.messages?.length ? (
            <>
              {currentLogEntry.messages.map((msg, i) => (
                <p
                  key={i}
                  style={{
                    margin: '2px 0',
                    fontSize: '13px',
                    whiteSpace: 'pre-wrap',
                    color: msg.startsWith('Missed') ? '#ff6666' : msg.startsWith('Crit') ? '#ffd700' : '#ccc',
                    lineHeight: 1.4,
                  }}
                >
                  {msg}
                </p>
              ))}
              <div ref={logEndRef} />
            </>
          ) : (
            <p style={{ fontSize: '13px', color: '#666', fontStyle: 'italic' }}>No messages for this turn.</p>
          )}
        </div>

        {/* Main view */}
        <div style={{ flex: 1, padding: '8px' }}>
          {/* Step controls */}
          <div style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={goBack}
              disabled={currentStep === 0}
              style={{
                padding: '6px 14px',
                borderRadius: '4px',
                border: '1px solid #555',
                background: currentStep === 0 ? '#2a2a2a' : '#333',
                color: currentStep === 0 ? '#555' : '#eee',
                cursor: currentStep === 0 ? 'default' : 'pointer',
                fontSize: '14px',
              }}
            >
              ◀ Prev
            </button>
            <button
              onClick={goForward}
              disabled={currentStep === logs.length - 1}
              style={{
                padding: '6px 14px',
                borderRadius: '4px',
                border: '1px solid #555',
                background: currentStep === logs.length - 1 ? '#2a2a2a' : '#333',
                color: currentStep === logs.length - 1 ? '#555' : '#eee',
                cursor: currentStep === logs.length - 1 ? 'default' : 'pointer',
                fontSize: '14px',
              }}
            >
              Next ▶
            </button>

            {/* Step slider */}
            <input
              type="range"
              min={0}
              max={logs.length - 1}
              value={currentStep}
              onChange={(e) => { setCurrentStep(Number(e.target.value)); setIsPlaying(false); }}
              style={{ flex: 1, maxWidth: '400px', cursor: 'pointer' }}
              title="Scrub through game steps"
            />
          </div>

          {/* Current action details */}
          {currentLogEntry && 'action' in currentLogEntry && currentLogEntry.action.actor !== -1 && (
            <div style={{
              background: '#222',
              borderRadius: '6px',
              padding: '8px 12px',
              marginBottom: '8px',
              fontSize: '13px',
              color: '#ccc',
              display: 'flex',
              gap: '12px',
              flexWrap: 'wrap',
            }}>
              <span>
                <span style={{ color: '#888' }}>Actor:</span>{' '}
                <span style={{ color: '#fff' }}>
                  {stateToRender?.entities.find((e) => e.id === currentLogEntry.action.actor)?.name || currentLogEntry.action.actor}
                </span>
              </span>
              <span>
                <span style={{ color: '#888' }}>Ability:</span>{' '}
                <span style={{ color: '#6cf' }}>{currentLogEntry.action.ability}</span>
              </span>
              <span>
                <span style={{ color: '#888' }}>Move:</span>{' '}
                <span style={{ color: '#aaa' }}>{currentLogEntry.action.movement_name} → [{String(getDestination(currentLogEntry))}]</span>
              </span>
              {currentLogEntry.action.target !== null && (
                <span>
                  <span style={{ color: '#888' }}>Target:</span>{' '}
                  <span style={{ color: '#f66' }}>
                    {stateToRender?.entities.find((e) => e.id === currentLogEntry.action.target)?.name || currentLogEntry.action.target}
                  </span>
                </span>
              )}
            </div>
          )}

          {currentLogEntry && 'action' in currentLogEntry && currentLogEntry.action.actor === -1 && (
            <div style={{ textAlign: 'center', padding: '20px', fontSize: '18px', color: '#ffd700' }}>
              🏁 Game Over
            </div>
          )}

          {stateToRender && <PhaserComponent engineState={stateToRender} action={currentLogEntry?.action} />}

          {/* Entity panels */}
          <div style={{ marginTop: '12px' }}>
            <h3 style={{ fontSize: '13px', color: '#aaa', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '8px' }}>
              Entities
            </h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {stateToRender?.entities.map((e) => {
                const teamColor = e.team === 1 ? '#ff4444' : '#3388ff';
                return (
                  <div
                    key={e.id}
                    style={{
                      border: `1px solid ${e.hp <= 0 ? '#444' : teamColor}`,
                      background: e.hp <= 0 ? '#222' : '#1a1a2a',
                      padding: '6px 10px',
                      borderRadius: '6px',
                      fontSize: '12px',
                      minWidth: '150px',
                    }}
                  >
                    <div style={{ fontWeight: 'bold', color: e.hp <= 0 ? '#666' : teamColor }}>
                      {e.hp <= 0 ? '💀' : ''}{e.name}
                    </div>
                    <div style={{ color: '#aaa' }}>
                      HP: <span style={{ color: e.hp <= 0 ? '#666' : e.hp <= 3 ? '#f66' : e.hp <= 6 ? '#fa0' : '#4c4' }}>{e.hp}</span>
                      {' | '}Pos: [{e.pos ? `${e.pos[0]},${e.pos[1]}` : '?'}]
                    </div>
                    {e.modifiers && e.modifiers.length > 0 && (
                      <div style={{ color: '#ca0', marginTop: '2px', fontSize: '11px' }}>
                        {e.modifiers.join(', ')}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
