import { EngineState, EntityState, ActionState } from '../types';
import * as Phaser from 'phaser';

const TILE_SIZE = 50;
const GRID_WIDTH = 20;
const GRID_HEIGHT = 20;
const HERO_EMOJIS: { [key: string]: string } = {
    "Melee Hero": "⚔️",
    "Ranged Hero": "🏹",
};

export class GameScene extends Phaser.Scene {
    private entitiesGroup: Phaser.GameObjects.Group;
    private overlaysGroup: Phaser.GameObjects.Group;

    constructor() {
        super('GameScene');
        this.entitiesGroup = new Phaser.GameObjects.Group(this);
        this.overlaysGroup = new Phaser.GameObjects.Group(this);
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

    public updateEngineState(state: EngineState, action?: ActionState) {
        if (this.sys.isActive()) {
            this.drawState(state, action);
        } else {
            this.events.once(Phaser.Scenes.Events.CREATE, () => {
                this.drawState(state, action);
            });
        }
    }

    private drawState(state: EngineState, action?: ActionState) {
        this.entitiesGroup.clear(true, true);
        this.overlaysGroup.clear(true, true);

        const turnOrder = state.entities
            .filter(e => e.hp > 0)
            .map(e => e.name === state.active_entity ? `> ${e.name} <` : e.name)
            .join(' | ');

        const infoText = this.add.text(10, 10, `Round: ${state.round_num} | Current Team: ${state.current_team === 1 ? 'Red' : 'Blue'}\nTurn Order: ${turnOrder}`, {
            fontSize: '16px',
            color: '#000000',
            backgroundColor: '#ffffff',
            padding: { x: 5, y: 5 }
        });
        this.entitiesGroup.add(infoText);

        let activeEntityContainer: Phaser.GameObjects.Container | null = null;
        let targetPos: [number, number] | null = null;

        state.entities.forEach(entityState => {
            const container = this.drawEntity(entityState, state.active_entity === entityState.name);
            if (state.active_entity === entityState.name) {
                activeEntityContainer = container;
            }
            if (action && action.target.startsWith(entityState.name)) {
                targetPos = entityState.pos as [number, number];
            }
        });

        if (action && activeEntityContainer) {
            this.animateAction(activeEntityContainer, action, targetPos);
        }
    }

    private animateAction(actor: Phaser.GameObjects.Container, action: ActionState, targetPos: [number, number] | null) {
        const path = action.path;
        if (path && path.length > 0) {
            const tweens = path.map((point: any) => ({
                x: point[0] * TILE_SIZE + TILE_SIZE / 2,
                y: point[1] * TILE_SIZE + TILE_SIZE / 2,
                duration: 150
            }));
            
            this.tweens.chain({
                targets: actor,
                tweens: tweens,
                onComplete: () => {
                    if (targetPos) {
                        this.drawAttackArrow(actor.x, actor.y, targetPos[0] * TILE_SIZE + TILE_SIZE / 2, targetPos[1] * TILE_SIZE + TILE_SIZE / 2);
                    }
                }
            });
        } else if (targetPos) {
            this.drawAttackArrow(actor.x, actor.y, targetPos[0] * TILE_SIZE + TILE_SIZE / 2, targetPos[1] * TILE_SIZE + TILE_SIZE / 2);
        }
    }

    private drawAttackArrow(fromX: number, fromY: number, toX: number, toY: number) {
        if (fromX === toX && fromY === toY) return;
        const arrow = this.add.graphics();
        arrow.lineStyle(4, 0xff0000, 0.8);
        
        arrow.beginPath();
        arrow.moveTo(fromX, fromY);
        arrow.lineTo(toX, toY);
        
        const angle = Phaser.Math.Angle.Between(fromX, fromY, toX, toY);
        const arrowHeadLength = 15;
        
        arrow.lineTo(toX - arrowHeadLength * Math.cos(angle - Math.PI / 6), toY - arrowHeadLength * Math.sin(angle - Math.PI / 6));
        arrow.moveTo(toX, toY);
        arrow.lineTo(toX - arrowHeadLength * Math.cos(angle + Math.PI / 6), toY - arrowHeadLength * Math.sin(angle + Math.PI / 6));
        
        arrow.strokePath();
        this.overlaysGroup.add(arrow);
    }

    private drawEntity(entity: EntityState, isActive: boolean) {
        const [x, y] = entity.pos as [number, number];
        const pixelX = x * TILE_SIZE + TILE_SIZE / 2;
        const pixelY = y * TILE_SIZE + TILE_SIZE / 2;

        const emoji = HERO_EMOJIS[entity.name] || '❓';

        const entityContainer = this.add.container(pixelX, pixelY);

        if (isActive) {
            const highlight = this.add.graphics();
            highlight.lineStyle(3, 0xffff00, 1);
            highlight.strokeCircle(0, 0, TILE_SIZE * 0.45);
            entityContainer.add(highlight);
        }

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
        const teamColor = entity.team === 1 ? 0xff0000 : 0x0088ff;
        hpForeground.fillStyle(teamColor, 1);
        hpForeground.fillRect(-hpBarWidth/2, hpBarY, hpBarWidth * hpPercent, hpBarHeight);

        const hpText = this.add.text(0, hpBarY + hpBarHeight/2, `${entity.hp}`, {
            fontSize: '10px',
            color: '#ffffff'
        }).setOrigin(0.5);

        entityContainer.add([entityText, hpBackground, hpForeground, hpText]);

        this.entitiesGroup.add(entityContainer);
        return entityContainer;
    }
}
