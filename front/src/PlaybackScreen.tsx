import { useState, useEffect, useCallback, useRef } from 'react';
import { GameLog, EngineState } from './types';
import { theme } from './theme';
import PhaserComponent from './PhaserComponent';

interface PlaybackScreenProps {
  gameLog: GameLog;
  onBack: () => void;
}

const teamLabel = (t: number | null) => (t === 1 ? 'Red' : 'Blue');

export function PlaybackScreen({ gameLog, onBack }: PlaybackScreenProps) {
  const logs = gameLog?.logs || [];
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(800); // ms per step
  const logEndRef = useRef<HTMLDivElement>(null);
  const animatingRef = useRef(false);
  const pendingStepRef = useRef(false);

  const goBack = useCallback(() => setCurrentStep((s) => Math.max(0, s - 1)), []);
  const goForward = useCallback(
    () => setCurrentStep((s) => Math.min(logs.length - 1, s + 1)),
    [logs.length]
  );

  const handleAnimationComplete = useCallback(() => {
    animatingRef.current = false;
    if (pendingStepRef.current) {
      pendingStepRef.current = false;
      goForward();
    }
  }, [goForward]);

  // Auto-play timer
  useEffect(() => {
    if (!isPlaying) return;
    const atEnd = currentStep >= logs.length - 1;
    if (atEnd) {
      setIsPlaying(false);
      return;
    }
    if (animatingRef.current) {
      pendingStepRef.current = true;
      return;
    }
    const timer = setTimeout(() => {
      if (animatingRef.current) {
        pendingStepRef.current = true;
      } else {
        goForward();
      }
    }, speed);
    return () => clearTimeout(timer);
  }, [isPlaying, currentStep, speed, goForward, logs.length]);

  const togglePlay = useCallback(() => {
    if (currentStep >= logs.length - 1) {
      setCurrentStep(0);
    }
    setIsPlaying((p) => !p);
  }, [currentStep, logs.length]);

  // Keyboard
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (animatingRef.current) return;
      if (e.key === 'ArrowRight') goForward();
      else if (e.key === 'ArrowLeft') goBack();
      else if (e.key === ' ') { e.preventDefault(); togglePlay(); }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [goBack, goForward, togglePlay]);

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentStep]);

  const currentLogEntry = logs[currentStep];
  const stateToRender: EngineState | undefined = currentLogEntry?.state;

  // Find first ability_use event to show what ability triggered this frame
  const mainAbilityEvent = currentLogEntry?.events.find(e => e.type === 'ability_use');

  const hpColor = (hp: number, dead: boolean) => {
    if (dead) return theme.hp.dead;
    if (hp <= 3) return theme.hp.low;
    if (hp <= 6) return theme.hp.mid;
    return theme.hp.high;
  };

  return (
    <div style={{ background: theme.bg.page, color: theme.fg.primary, minHeight: '100vh', fontFamily: 'sans-serif' }}>
      {/* Top bar */}
      <div style={{
        padding: '8px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        borderBottom: `1px solid ${theme.borders.subtle}`,
        background: theme.bg.surface,
      }}>
        <button onClick={onBack} className="btn-ghost">
          ← Setup
        </button>

        <button
          onClick={togglePlay}
          style={{
            padding: '6px 16px',
            borderRadius: '4px',
            border: 'none',
            background: isPlaying ? theme.accent.warning : theme.accent.primary,
            color: theme.fg.bright,
            cursor: 'pointer',
            fontSize: '16px',
            fontWeight: 'bold',
          }}
        >
          {isPlaying ? '⏸ Pause' : '▶ Auto-Play'}
        </button>

        <span style={{ fontSize: '14px', color: theme.fg.muted }}>
          Step {currentStep} / {logs.length - 1}
        </span>

        <span style={{ fontSize: '13px', color: theme.fg.disabled }}>Speed:</span>
        <select
          value={speed}
          onChange={(e) => setSpeed(Number(e.target.value))}
          style={{
            padding: '4px 8px',
            borderRadius: '4px',
            border: `1px solid ${theme.borders.light}`,
            background: theme.bg.surfaceHover,
            color: theme.fg.primary,
            fontSize: '13px',
          }}
        >
          <option value={1500}>Slow</option>
          <option value={800}>Normal</option>
          <option value={400}>Fast</option>
          <option value={150}>Turbo</option>
        </select>

        <span style={{ fontSize: '13px', color: theme.fg.disabled }}>Space: Play/Pause</span>

        <span style={{ marginLeft: 'auto', fontSize: '16px', color: theme.accent.gold }}>
          {gameLog.winner_team !== null
            ? `🏆 Team ${teamLabel(gameLog.winner_team)} Wins!`
            : 'Game Over (Tie)'}
        </span>
      </div>

      <div style={{ display: 'flex' }}>
        {/* Written log sidebar */}
        <div
          style={{
            width: '320px',
            borderRight: `1px solid ${theme.borders.subtle}`,
            padding: '12px',
            height: 'calc(100vh - 52px)',
            overflowY: 'auto',
            background: theme.bg.panel,
            order: -1,
          }}
        >
          <h3 style={{
            margin: '0 0 8px',
            fontSize: '14px',
            color: theme.fg.muted,
            textTransform: 'uppercase',
            letterSpacing: '1px',
          }}>
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
                    color: msg.startsWith('Missed') ? theme.accent.miss : msg.startsWith('Crit') ? theme.accent.crit : theme.fg.secondary,
                    lineHeight: 1.4,
                  }}
                >
                  {msg}
                </p>
              ))}
              <div ref={logEndRef} />
            </>
          ) : (
            <p style={{ fontSize: '13px', color: theme.fg.placeholder, fontStyle: 'italic' }}>No messages for this turn.</p>
          )}
        </div>

        {/* Main view */}
        <div style={{ flex: 1, padding: '8px' }}>
          {/* Step controls */}
          <div style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={goBack}
              disabled={currentStep === 0}
              className="btn-ghost"
            >
              ◀ Prev
            </button>
            <button
              onClick={goForward}
              disabled={currentStep === logs.length - 1}
              className="btn-ghost"
            >
              Next ▶
            </button>

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

          {/* Event summary — show what happened in this frame */}
          {currentLogEntry?.events && currentLogEntry.events.length > 0 && (
            <div style={{
              background: theme.bg.surface,
              borderRadius: '6px',
              padding: '8px 12px',
              marginBottom: '8px',
              fontSize: '13px',
              color: theme.fg.secondary,
              display: 'flex',
              gap: '8px',
              flexWrap: 'wrap',
            }}>
              {/* Show up to 3 event types as a compact summary */}
              {Array.from(new Set(currentLogEntry.events.map(e => e.type))).slice(0, 3).map(type => {
                const same = currentLogEntry.events.filter(e => e.type === type);
                const first = same[0];
                return (
                  <span key={type}>
                    <span style={{ color: theme.fg.dim, textTransform: 'capitalize' }}>{type}</span>
                    {type === 'damage' && first.amount != null && (
                      <> <span style={{ color: theme.accent.hit }}>{first.amount}</span>{same.length > 1 ? ` ×${same.length}` : ''}</>
                    )}
                    {type === 'move' && <span style={{ color: theme.fg.muted }}> {same.length}× tile</span>}
                    {type === 'ability_use' && first.ability_name && (
                      <> <span style={{ color: theme.accent.ability }}>{first.ability_name}</span></>
                    )}
                    {type === 'death' && <span style={{ color: theme.hp.dead }}> {same.length} died</span>}
                  </span>
                );
              })}
            </div>
          )}

          {stateToRender && (
            <PhaserComponent
              engineState={stateToRender}
              onAnimationComplete={handleAnimationComplete}
            />
          )}

          {/* Entity panels */}
          <div style={{ marginTop: '12px' }}>
            <h3 style={{
              fontSize: '13px',
              color: theme.fg.muted,
              textTransform: 'uppercase',
              letterSpacing: '1px',
              marginBottom: '8px',
            }}>
              Entities
            </h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {(stateToRender?.entities || []).map((e) => {
                const teamColor = theme.team[e.team as 0 | 1];
                const dead = e.hp <= 0;
                return (
                  <div
                    key={e.id}
                    style={{
                      border: `1px solid ${dead ? theme.borders.muted : teamColor}`,
                      background: dead ? theme.bg.surface : theme.bg.card,
                      padding: '6px 10px',
                      borderRadius: '6px',
                      fontSize: '12px',
                      minWidth: '150px',
                      color: theme.fg.secondary,
                    }}
                  >
                    <div style={{ fontWeight: 'bold', color: dead ? theme.hp.dead : teamColor }}>
                      {dead ? '💀' : ''}{e.name}
                    </div>
                    <div>
                      HP: <span style={{ color: hpColor(e.hp, dead) }}>{e.hp}</span>
                      {' | '}Pos: [{e.pos ? `${e.pos[0]},${e.pos[1]}` : '?'}]
                    </div>
                    {e.modifiers && e.modifiers.length > 0 && (
                      <div style={{ color: theme.accent.modifier, marginTop: '2px', fontSize: '11px' }}>
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
