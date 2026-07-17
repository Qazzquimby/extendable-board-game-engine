import React, { useEffect, useRef } from 'react';
import { GameScene } from './scenes/GameScene';
import { EngineState, ActionState } from './types';
import * as Phaser from 'phaser';

interface PhaserComponentProps {
  engineState: EngineState;
  action?: ActionState;
  onAnimationComplete?: () => void;
}

const GRID_WIDTH = 10;
const GRID_HEIGHT = 10;
const TILE_SIZE = 70;
const CANVAS_WIDTH = GRID_WIDTH * TILE_SIZE;
const CANVAS_HEIGHT = GRID_HEIGHT * TILE_SIZE;

const PhaserComponent: React.FC<PhaserComponentProps> = ({ engineState, action, onAnimationComplete }) => {
  const gameContainer = useRef<HTMLDivElement>(null);
  const gameInstance = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    if (gameContainer.current && !gameInstance.current) {
      const config: Phaser.Types.Core.GameConfig = {
        type: Phaser.AUTO,
        width: CANVAS_WIDTH,
        height: CANVAS_HEIGHT,
        parent: gameContainer.current,
        backgroundColor: '#1a1a1a',
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
            scene.setAnimationCallback(onAnimationComplete || (() => {}));
            scene.updateEngineState(engineState, action);
        }
    }
  }, [engineState, action, onAnimationComplete]);

  return <div ref={gameContainer} style={{ width: '100%', maxWidth: CANVAS_WIDTH, height: CANVAS_HEIGHT, margin: '20px 0', overflow: 'hidden' }}/>;
};

export default PhaserComponent;
