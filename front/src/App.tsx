import { useState } from 'react';
import { GameLog } from './types';
import { SetupScreen } from './SetupScreen';
import { PlaybackScreen } from './PlaybackScreen';

type Mode = 'setup' | 'playback';

function App() {
  const [mode, setMode] = useState<Mode>('setup');
  const [gameLog, setGameLog] = useState<GameLog | null>(null);

  const handlePlay = (log: GameLog) => {
    setGameLog(log);
    setMode('playback');
  };

  const handleBack = () => {
    setMode('setup');
    setGameLog(null);
  };

  if (mode === 'playback' && gameLog) {
    return <PlaybackScreen gameLog={gameLog} onBack={handleBack} />;
  }

  return <SetupScreen onPlay={handlePlay} />;
}

export default App;
