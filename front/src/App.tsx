import { useState } from 'react';
import { LogEntry } from './types';
import PhaserComponent from './PhaserComponent';

function App() {
  const [log, setLog] = useState<LogEntry[]>([]);
  const [currentStep, setCurrentStep] = useState(0);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const content = e.target?.result;
          if (typeof content === 'string') {
            const jsonLog = JSON.parse(content);
            if (Array.isArray(jsonLog)) {
                setLog(jsonLog);
                setCurrentStep(0);
            } else {
                alert("Log file is not a JSON array of log entries.");
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

  return (
    <div>
      <h1>Game Log Visualizer</h1>
      <input type="file" accept=".json,.jsonl" onChange={handleFileChange} />
      {log.length > 0 && (
        <>
          <div>
            <button onClick={() => setCurrentStep(s => Math.max(0, s - 1))} disabled={currentStep === 0}>
              Previous
            </button>
            <span> Step {currentStep} / {log.length - 1} </span>
            <button onClick={() => setCurrentStep(s => Math.min(log.length - 1, s + 1))} disabled={currentStep === log.length - 1}>
              Next
            </button>
          </div>
          {currentLogEntry && (
            <div>
              <h3>Action</h3>
              <p>Actor: {currentLogEntry.action.actor} performing {currentLogEntry.action.ability} on {currentLogEntry.action.target} after moving to [{String(currentLogEntry.action.move_pos)}]</p>
            </div>
          )}
          {stateToRender && <PhaserComponent engineState={stateToRender} />}
        </>
      )}
    </div>
  );
}

export default App;
>>>>>>> REPLACE



front/src/PhaserComponent.tsx
<<<<<<< SEARCH
=======
import Phaser from 'phaser';
import React, { useEffect, useRef } from 'react';
import { GameScene } from './scenes/GameScene';
import { EngineState } from './types';

interface PhaserComponentProps {
  engineState: EngineState;
}

const GRID_WIDTH = 10;
const GRID_HEIGHT = 10;
const TILE_SIZE = 50;

const PhaserComponent: React.FC<PhaserComponentProps> = ({ engineState }) => {
  const gameContainer = useRef<HTMLDivElement>(null);
  const gameInstance = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    if (gameContainer.current && !gameInstance.current) {
      const config: Phaser.Types.Core.GameConfig = {
        type: Phaser.AUTO,
        width: GRID_WIDTH * TILE_SIZE,
        height: GRID_HEIGHT * TILE_SIZE,
        parent: gameContainer.current,
        backgroundColor: '#cccccc',
        scene: GameScene,
      };
      gameInstance.current = new Phaser.Game(config);
    }

    return () => {
      gameInstance.current?.destroy(true);
      gameInstance.current = null;
    };
  }, []);

  useEffect(() => {
    if (gameInstance.current && engineState) {
        const scene = gameInstance.current.scene.getScene('GameScene') as GameScene;
        if (scene) {
            scene.updateEngineState(engineState);
        }
    }
  }, [engineState]);

  return <div ref={gameContainer} style={{ width: GRID_WIDTH * TILE_SIZE, height: GRID_HEIGHT * TILE_SIZE, margin: '20px 0' }}/>;
};

export default PhaserComponent;
