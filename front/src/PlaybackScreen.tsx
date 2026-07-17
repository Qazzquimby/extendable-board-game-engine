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
  const logRefs = useRef<(HTMLDivElement | null)[]>([]);

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

  // Auto-scroll log sidebar to current entry
  useEffect(() => {
    const el = logRefs.current[currentStep];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [currentStep]);

  // Ensure logRefs array matches logs length
  if (logRefs.current.length !== logs.length) {
    logRefs.current = logRefs.current.slice(0, logs.length);
    while (logRefs.current.length < logs.length) logRefs.current.push(null);
  }

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
    <div style={{ background: theme.bg.page, color: theme.fg.primary, height: '100vh', overflow: 'hidden', display: 'flex', flexDirection: 'column', fontFamily: 'sans-serif' }}>
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

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Written log sidebar */}
        <div
          style={{
            width: '320px',
            borderRight: `1px solid ${theme.borders.subtle}`,
            padding: '0',
            height: '100%',
            overflowY: 'auto',
            background: theme.bg.panel,
            order: -1,
          }}
        >
          <h3 style={{
            margin: '0',
            padding: '12px 12px 8px',
            fontSize: '14px',
            color: theme.fg.muted,
            textTransform: 'uppercase',
            letterSpacing: '1px',
            borderBottom: `1px solid ${theme.borders.subtle}`,
            position: 'sticky',
            top: 0,
            background: theme.bg.panel,
            zIndex: 1,
          }}>
            Game Log
          </h3>
          {logs.map((entry, idx) => {
            const isCurrent = idx === currentStep;
            const actionLogs = entry.action_logs || [];
            return (
              <div
                key={idx}
                ref={isCurrent ? (el) => { logRefs.current[idx] = el; } : undefined}
                style={{
                  padding: '8px 12px',
                  borderBottom: `1px solid ${theme.borders.subtle}`,
                  background: isCurrent ? theme.bg.surfaceHover : 'transparent',
                  borderLeft: isCurrent ? `3px solid ${theme.accent.gold}` : '3px solid transparent',
                  cursor: 'pointer',
                }}
                onClick={() => { setCurrentStep(idx); setIsPlaying(false); }}
              >
                <div style={{
                  fontSize: '11px',
                  color: isCurrent ? theme.fg.primary : theme.fg.muted,
                  fontWeight: isCurrent ? 'bold' : 'normal',
                  marginBottom: '4px',
                }}>
                  {entry.done ? '🏁 Game Over' : `Step ${idx}`}
                  <span style={{ color: theme.fg.disabled, marginLeft: '4px' }}>
                    r{entry.state.round_num}
                    {entry.state.active_entity != null ? ` | #{${entry.state.active_entity}}` : ''}
                  </span>
                </div>
                {actionLogs.length > 0 ? (
                  actionLogs.map((msg, mi) => (
                    <div
                      key={mi}
                      style={{
                        fontSize: '12px',
                        lineHeight: 1.5,
                        color: msg.startsWith('--') ? theme.fg.disabled : isCurrent ? theme.fg.primary : theme.fg.secondary,
                        paddingLeft: msg.startsWith('--') ? '0' : '0',
                        marginLeft: (msg.match(/^--+/)?.[0]?.length || 0) * 8,
                        fontStyle: msg.startsWith('--') ? 'italic' : 'normal',
                      }}
                    >
                      {msg.replace(/^--+\s*/, '').replace(/^\.\s*/, '')}
                    </div>
                  ))
                ) : (
                  isCurrent ? (
                    <div style={{ fontSize: '12px', color: theme.fg.placeholder, fontStyle: 'italic' }}>
                      {idx === 0 ? 'Initial board' : 'Processing...'}
                    </div>
                  ) : null
                )}
                {entry.events && entry.events.length > 0 && (
                  <div style={{ fontSize: '11px', color: theme.fg.disabled, marginTop: '4px' }}>
                    {entry.events.length} event{entry.events.length !== 1 ? 's' : ''}
                    {': '}{Array.from(new Set(entry.events.map(e => e.type))).join(', ')}
                  </div>
                )}
              </div>
            );
          })}
          <div ref={logEndRef} />
        </div>

        {/* Main view */}
        <div style={{ flex: 1, padding: '8px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
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

          {/* Event summary — always present, shows what happened in this frame */}
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
            minHeight: '20px',
          }}>
            {currentLogEntry?.events && currentLogEntry.events.length > 0 ? (
              (() => {
                // Show unique event types with counts, grouped
                const byType = new Map<string, typeof currentLogEntry.events>();
                for (const e of currentLogEntry.events) {
                  const arr = byType.get(e.type) || [];
                  arr.push(e);
                  byType.set(e.type, arr);
                }
                return Array.from(byType.entries()).slice(0, 4).map(([type, same]) => {
                  const first = same[0];
                  return (
                    <span key={type}>
                      <span style={{ color: theme.fg.dim, textTransform: 'capitalize' }}>{type}</span>
                      {type === 'damage' && first.amount != null && (
                        <> <span style={{ color: theme.accent.hit }}>{first.amount}</span>{same.length > 1 ? ` ×${same.length}` : ''}</>
                      )}
                      {type === 'heal' && first.amount != null && (
                        <> <span style={{ color: theme.hp.high }}>+{first.amount}</span>{same.length > 1 ? ` ×${same.length}` : ''}</>
                      )}
                      {type === 'move' && <span style={{ color: theme.fg.muted }}> {same.length}× tile</span>}
                      {type === 'ability_use' && first.ability_name && (
                        <> <span style={{ color: theme.accent.ability }}>{first.ability_name}</span></>
                      )}
                      {type === 'death' && <span style={{ color: theme.hp.dead }}> {same.length} died</span>}
                    </span>
                  );
                });
              })()
            ) : (
              <span style={{ color: theme.fg.disabled, fontStyle: 'italic' }}>Initial board</span>
            )}
          </div>

          {stateToRender && (
            <PhaserComponent
              engineState={stateToRender}
              events={currentLogEntry?.events || []}
              onAnimationComplete={handleAnimationComplete}
            />
          )}

        </div>

        {/* Entity sidebar */}
        <div
          style={{
            width: '220px',
            borderLeft: `1px solid ${theme.borders.subtle}`,
            padding: '0',
            height: '100%',
            overflowY: 'auto',
            background: theme.bg.panel,
            flexShrink: 0,
          }}
        >
          <h3 style={{
            margin: '0',
            padding: '12px 12px 8px',
            fontSize: '14px',
            color: theme.fg.muted,
            textTransform: 'uppercase',
            letterSpacing: '1px',
            borderBottom: `1px solid ${theme.borders.subtle}`,
            position: 'sticky',
            top: 0,
            background: theme.bg.panel,
            zIndex: 1,
          }}>
            Entities
          </h3>
          {(stateToRender?.entities || []).map((e) => {
            const teamColor = theme.team[e.team as 0 | 1];
            const dead = e.hp <= 0;
            return (
              <div
                key={e.id}
                style={{
                  padding: '8px 12px',
                  borderBottom: `1px solid ${theme.borders.subtle}`,
                }}
              >
                <div style={{
                  fontWeight: 'bold',
                  color: dead ? theme.hp.dead : teamColor,
                  fontSize: '13px',
                }}>
                  {dead ? '💀 ' : ''}{e.name}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '4px' }}>
                  <div style={{
                    flex: 1,
                    height: '6px',
                    borderRadius: '3px',
                    background: theme.hp.bg,
                    overflow: 'hidden',
                  }}>
                    <div style={{
                      width: `${dead ? 0 : Math.max(3, (e.hp / 12) * 100)}%`,
                      height: '100%',
                      background: hpColor(e.hp, dead),
                      borderRadius: '3px',
                    }} />
                  </div>
                  <span style={{ fontSize: '11px', color: theme.fg.secondary }}>{e.hp}</span>
                </div>
                <div style={{ fontSize: '11px', color: theme.fg.disabled, marginTop: '2px' }}>
                  Pos: [{e.pos ? `${e.pos[0]},${e.pos[1]}` : '?'}]
                  {' | '}Team {e.team + 1}
                </div>
                {e.modifiers && e.modifiers.length > 0 && (
                  <div style={{ color: theme.accent.modifier, marginTop: '3px', fontSize: '11px', lineHeight: 1.4 }}>
                    {e.modifiers.join(', ')}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
