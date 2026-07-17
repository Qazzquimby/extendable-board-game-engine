import React, { useEffect, useRef } from 'react';
import { GameScene } from './scenes/GameScene';
import { EngineState } from './types';
import * as Phaser from 'phaser';

interface PhaserComponentProps {
  engineState: EngineState;
  onAnimationComplete?: () => void;
}

// Render at higher internal resolution for crisp text, then CSS-clamp to fit.
const GRID_WIDTH = 10;
const GRID_HEIGHT = 10;
const TILE_SIZE = 140;
const CANVAS_WIDTH = GRID_WIDTH * TILE_SIZE;
const CANVAS_HEIGHT = GRID_HEIGHT * TILE_SIZE;

const PhaserComponent: React.FC<PhaserComponentProps> = ({ engineState, onAnimationComplete }) => {
  const gameContainer = useRef<HTMLDivElement>(null);
  const gameInstance = useRef<Phaser.Game | null>(null);
  const pendingState = useRef<EngineState | null>(null);
  const animCallback = useRef(onAnimationComplete);

  // Keep callback ref current without triggering re-renders
  animCallback.current = onAnimationComplete;

  useEffect(() => {
    if (gameContainer.current && !gameInstance.current) {
      const config: Phaser.Types.Core.GameConfig = {
        type: Phaser.AUTO,
        width: CANVAS_WIDTH,
        height: CANVAS_HEIGHT,
        parent: gameContainer.current,
        backgroundColor: '#1a1a1a',
        scene: GameScene,
        canvasStyle: 'display: block; width: 100%; max-width: ' + CANVAS_WIDTH + 'px; height: auto;',
      };
      gameInstance.current = new Phaser.Game(config);
    }
    return () => {
      gameInstance.current?.destroy(true);
      gameInstance.current = null;
    };
  }, []);

  useEffect(() => {
    if (!gameInstance.current) return;

    const scene = gameInstance.current.scene.getScene('GameScene') as GameScene | null;
    if (scene && scene.scene.isActive()) {
      scene.setAnimationCallback(animCallback.current || (() => {}));
      scene.updateEngineState(engineState);
    } else {
      // Scene not ready yet — store for later
      pendingState.current = engineState;
      // Poll until scene is ready
      const check = setInterval(() => {
        const s = gameInstance.current?.scene.getScene('GameScene') as GameScene | null;
        if (s && s.scene.isActive()) {
          clearInterval(check);
          if (pendingState.current) {
            s.setAnimationCallback(animCallback.current || (() => {}));
            s.updateEngineState(pendingState.current);
            pendingState.current = null;
          }
        }
      }, 50);
      // Stop checking after 5 seconds
      setTimeout(() => clearInterval(check), 5000);
    }
  }, [engineState]);

  return <div ref={gameContainer} style={{ width: '100%', maxWidth: CANVAS_WIDTH, margin: '20px 0' }}/>;
};

export default PhaserComponent;
