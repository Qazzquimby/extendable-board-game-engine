import { EngineState, EntityState, ActionState } from '../types';
import * as Phaser from 'phaser';

export class GameScene extends Phaser.Scene {
    private entitiesGroup: Phaser.GameObjects.Group;
    private overlaysGroup: Phaser.GameObjects.Group;
    private gridGameObject: Phaser.GameObjects.Grid | null = null;
    private tileSize = 0;
    private gridOffsetX = 0;
    private gridOffsetY = 0;

    constructor() {
        super('GameScene');
        this.entitiesGroup = new Phaser.GameObjects.Group(this);
        this.overlaysGroup = new Phaser.GameObjects.Group(this);
    }

    public updateEngineState(state: EngineState, action?: ActionState, messages?: string[]) {
        if (this.entitiesGroup && this.overlaysGroup) {
            this.drawState(state, action, messages);
        } else {
            this.events.once(Phaser.Scenes.Events.CREATE, () => {
                this.drawState(state, action, messages);
            });
        }
    }

    private drawState(state: EngineState, action?: ActionState, messages?: string[]) {
        this.entitiesGroup.clear(true, true);
        this.overlaysGroup.clear(true, true);

        let maxX = 9;
        let maxY = 9;
        state.entities.forEach(e => {
            if (e.pos) {
                maxX = Math.max(maxX, e.pos[0] as number);
                maxY = Math.max(maxY, e.pos[1] as number);
            }
        });
        const gridWidth = maxX + 1;
        const gridHeight = maxY + 1;

        const TOP_BAR_HEIGHT = 100;
        const { width: screenWidth, height: screenHeight } = this.scale;
        const availableWidth = screenWidth;
        const availableHeight = (screenHeight - TOP_BAR_HEIGHT);

        this.tileSize = Math.floor(Math.min(availableWidth / gridWidth, availableHeight / gridHeight));
        const gridPixelWidth = gridWidth * this.tileSize;
        const gridPixelHeight = gridHeight * this.tileSize;

        this.gridOffsetX = Math.floor((availableWidth - gridPixelWidth) / 2);
        this.gridOffsetY = TOP_BAR_HEIGHT + Math.floor((availableHeight - gridPixelHeight) / 2);


        if (this.gridGameObject) {
            this.gridGameObject.destroy();
        }
        this.gridGameObject = this.add.grid(
            this.gridOffsetX + gridPixelWidth / 2,
            this.gridOffsetY + gridPixelHeight / 2,
            gridPixelWidth,
            gridPixelHeight,
            this.tileSize,
            this.tileSize,
            0x000000,
            0,
            0x666666,
            1.0
        );

        const turnOrder = state.entities
            .filter(e => e.hp > 0)
            .map(e => {
                const teamName = e.team === 1 ? 'Red' : 'Blue';
                const fullName = `${teamName} ${e.name} ${e.id}`;
                return e.id === state.active_entity ? `> ${fullName} <` : fullName;
            })
            .join(' | ');

        const messagesText = messages && messages.length > 0 ? `\nMessages:\n${messages.join('\n')}` : '';
        const infoText = this.add.text(10, 10, `Round: ${state.round_num} | Current Team: ${state.current_team === 1 ? 'Red' : 'Blue'}\nTurn Order: ${turnOrder}${messagesText}`, {
            fontSize: '16px',
            color: '#000000',
            backgroundColor: '#ffffff',
            padding: { x: 5, y: 5 }
        });
        this.entitiesGroup.add(infoText);

        let activeEntityContainer: Phaser.GameObjects.Container | null = null;
        let targetPos: [number, number] | null = null;

        state.entities.forEach(entityState => {
            const isActive = state.active_entity === entityState.id;
            const container = this.drawEntity(entityState, isActive);
            
            if (action) {
                if (action.actor === entityState.id) {
                    activeEntityContainer = container;
                }
                if (action.target === entityState.id) {
                    if (action.target === action.actor) {
                        targetPos = action.move_pos as [number, number];
                    } else {
                        targetPos = entityState.pos as [number, number];
                    }
                }
            } else if (isActive) {
                activeEntityContainer = container;
            }
        });

        if (action && activeEntityContainer) {
            this.animateAction(activeEntityContainer, action, targetPos);
        }
    }

    private animateAction(actor: Phaser.GameObjects.Container, action: ActionState, targetPos: [number, number] | null) {
        const path = action.move_path;
        if (path && path.length > 0) {
            const tweens = path.map((point: any) => ({
                x: this.gridOffsetX + point[0] * this.tileSize + this.tileSize / 2,
                y: this.gridOffsetY + point[1] * this.tileSize + this.tileSize / 2,
                duration: 150
            }));

            this.tweens.chain({
                targets: actor,
                tweens: tweens,
                onComplete: () => {
                    if (targetPos) {
                        this.drawAttackArrow(actor.x, actor.y, this.gridOffsetX + targetPos[0] * this.tileSize + this.tileSize / 2, this.gridOffsetY + targetPos[1] * this.tileSize + this.tileSize / 2);
                    }
                }
            });
        } else if (targetPos) {
            this.drawAttackArrow(actor.x, actor.y, this.gridOffsetX + targetPos[0] * this.tileSize + this.tileSize / 2, this.gridOffsetY + targetPos[1] * this.tileSize + this.tileSize / 2);
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
        if (!entity.pos) return null;
        const [x, y] = entity.pos as [number, number];
        const pixelX = this.gridOffsetX + x * this.tileSize + this.tileSize / 2;
        const pixelY = this.gridOffsetY + y * this.tileSize + this.tileSize / 2;

        const baseName = entity.name;

        const entityContainer = this.add.container(pixelX, pixelY);

        if (isActive) {
            const highlight = this.add.graphics();
            highlight.lineStyle(3, 0xffff00, 1);
            highlight.strokeCircle(0, 0, this.tileSize * 0.45);
            entityContainer.add(highlight);
        }

        const entityText = this.add.text(0, 0, baseName, {
            fontSize: `${this.tileSize * 0.25}px`,
            align: 'center',
            color: '#ffffff',
            stroke: '#000000',
            strokeThickness: 4,
            wordWrap: { width: this.tileSize, useAdvancedWrap: true }
        }).setOrigin(0.5);

        // Health bar
        const hpBarWidth = this.tileSize * 0.8;
        const hpBarHeight = 8;
        const hpBarY = this.tileSize * 0.4;

        const hpBackground = this.add.graphics();
        hpBackground.fillStyle(0x333333, 1);
        hpBackground.fillRect(-hpBarWidth/2, hpBarY, hpBarWidth, hpBarHeight);

        const hpForeground = this.add.graphics();
        const hpPercent = entity.hp / 10; // Assuming max hp is 10
        const teamColor = entity.team === 1 ? 0xff0000 : 0x0088ff;
        hpForeground.fillStyle(teamColor, 1);
        hpForeground.fillRect(-hpBarWidth/2, hpBarY, hpBarWidth * hpPercent, hpBarHeight);

        const hpText = this.add.text(0, hpBarY + hpBarHeight/2, `${entity.hp}`, {
            fontSize: '18px',
            color: '#ffffff'
        }).setOrigin(0.5);

        entityContainer.add([entityText, hpBackground, hpForeground, hpText]);

        this.entitiesGroup.add(entityContainer);
        return entityContainer;
    }
}
