import Phaser from 'phaser';
import { EngineState, EntityState } from '../types';

const TILE_SIZE = 50;
const GRID_WIDTH = 10;
const GRID_HEIGHT = 10;
const HERO_EMOJIS: { [key: string]: string } = {
    "Melee Hero": "⚔️",
    "Ranged Hero": "🏹",
};

export class GameScene extends Phaser.Scene {
    private entitiesGroup: Phaser.GameObjects.Group;

    constructor() {
        super('GameScene');
        this.entitiesGroup = new Phaser.GameObjects.Group(this);
    }

    create() {
        this.add.grid(
            (GRID_WIDTH * TILE_SIZE) / 2,
            (GRID_HEIGHT * TILE_SIZE) / 2,
            GRID_WIDTH * TILE_SIZE,
            GRID_HEIGHT * TILE_SIZE,
            TILE_SIZE,
            TILE_SIZE,
            0x000000,
            0,
            0xffffff,
            0.2
        );
    }

    public updateEngineState(state: EngineState) {
        if (this.sys.isBooted) {
            this.drawState(state);
        } else {
            this.events.once(Phaser.Scenes.Events.CREATE, () => {
                this.drawState(state);
            });
        }
    }

    private drawState(state: EngineState) {
        this.entitiesGroup.clear(true, true);

        state.entities.forEach(entityState => {
            this.drawEntity(entityState);
        });
    }

    private drawEntity(entity: EntityState) {
        const [x, y] = entity.pos as [number, number];
        const pixelX = x * TILE_SIZE + TILE_SIZE / 2;
        const pixelY = y * TILE_SIZE + TILE_SIZE / 2;

        const emoji = HERO_EMOJIS[entity.name] || '❓';

        const entityContainer = this.add.container(pixelX, pixelY);

        const entityText = this.add.text(0, 0, emoji, {
            fontSize: `${TILE_SIZE * 0.6}px`,
            align: 'center',
        }).setOrigin(0.5);

        // Health bar
        const hpBarWidth = TILE_SIZE * 0.8;
        const hpBarHeight = 8;
        const hpBarY = TILE_SIZE * 0.4;

        const hpBackground = this.add.graphics();
        hpBackground.fillStyle(0x333333, 1);
        hpBackground.fillRect(-hpBarWidth/2, hpBarY, hpBarWidth, hpBarHeight);

        const hpForeground = this.add.graphics();
        const hpPercent = entity.hp / 10; // Assuming max hp is 10
        hpForeground.fillStyle(entity.team === 1 ? '#00cc00' : '#cc0000', 1);
        hpForeground.fillRect(-hpBarWidth/2, hpBarY, hpBarWidth * hpPercent, hpBarHeight);

        const hpText = this.add.text(0, hpBarY + hpBarHeight/2, `${entity.hp}`, {
            fontSize: '10px',
            color: '#ffffff'
        }).setOrigin(0.5);

        entityContainer.add([entityText, hpBackground, hpForeground, hpText]);

        this.entitiesGroup.add(entityContainer);
    }
}