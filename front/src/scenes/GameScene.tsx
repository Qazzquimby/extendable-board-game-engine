import { EngineState, EntityState, ActionState } from '../types';
import * as Phaser from 'phaser';

const TEAM_COLORS = [0x3388ff, 0xff4444];
const TEAM_COLORS_LIGHT = [0x66aaff, 0xff7777];
const TEAM_LABELS = ['Blue', 'Red'];
const GRID_BG = 0x2a2a2a;
const GRID_LINE = 0x444444;

function getHpColor(hp: number): number {
  if (hp <= 0) return 0x555555;
  if (hp <= 3) return 0xff3333;
  if (hp <= 6) return 0xffaa00;
  return 0x44cc44;
}

export class GameScene extends Phaser.Scene {
    private entitiesGroup: Phaser.GameObjects.Group;
    private overlaysGroup: Phaser.GameObjects.Group;
    private uiGroup: Phaser.GameObjects.Group;
    private gridGameObject: Phaser.GameObjects.Grid | null = null;
    private gridBg: Phaser.GameObjects.Rectangle | null = null;
    private tileSize = 0;
    private gridOffsetX = 0;
    private gridOffsetY = 0;

    constructor() {
        super('GameScene');
        this.entitiesGroup = new Phaser.GameObjects.Group(this);
        this.overlaysGroup = new Phaser.GameObjects.Group(this);
        this.uiGroup = new Phaser.GameObjects.Group(this);
    }

    public updateEngineState(state: EngineState, action?: ActionState) {
        if (this.entitiesGroup && this.overlaysGroup) {
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
        this.uiGroup.clear(true, true);

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

        const TOP_BAR_HEIGHT = 50;
        const { width: screenWidth, height: screenHeight } = this.scale;
        const availableWidth = screenWidth;
        const availableHeight = (screenHeight - TOP_BAR_HEIGHT);

        this.tileSize = Math.floor(Math.min(availableWidth / (gridWidth + 1), availableHeight / (gridHeight + 1)));
        const gridPixelWidth = gridWidth * this.tileSize;
        const gridPixelHeight = gridHeight * this.tileSize;

        this.gridOffsetX = Math.floor((availableWidth - gridPixelWidth) / 2);
        this.gridOffsetY = TOP_BAR_HEIGHT + Math.floor((availableHeight - gridPixelHeight) / 2);

        // Top bar
        const roundText = this.add.text(12, 12, `Round ${state.round_num}`, {
            fontSize: '18px',
            color: '#ffffff',
            fontFamily: 'monospace',
            fontStyle: 'bold',
        });
        this.uiGroup.add(roundText);

        const teamText = this.add.text(screenWidth / 2, 12, `${TEAM_LABELS[state.current_team]}'s Turn`, {
            fontSize: '16px',
            color: TEAM_COLORS[state.current_team] === 0x3388ff ? '#66aaff' : '#ff7777',
            fontFamily: 'monospace',
        }).setOrigin(0.5, 0);
        this.uiGroup.add(teamText);

        // Grid background
        if (this.gridBg) this.gridBg.destroy();
        this.gridBg = this.add.rectangle(
            this.gridOffsetX + gridPixelWidth / 2,
            this.gridOffsetY + gridPixelHeight / 2,
            gridPixelWidth,
            gridPixelHeight,
            GRID_BG
        );
        this.gridBg.setDepth(-1);

        // Grid lines
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
            GRID_LINE,
            0.3,
            GRID_LINE,
            0.5
        );
        this.gridGameObject.setDepth(0);

        let activeEntityContainer: Phaser.GameObjects.Container | null = null;
        let targetPos: [number, number] | null = null;

        const posCounts: Record<string, number> = {};
        const posIndex: Record<number, number> = {};

        state.entities.forEach(e => {
            if (e.pos) {
                const key = `${e.pos[0]},${e.pos[1]}`;
                posCounts[key] = (posCounts[key] || 0) + 1;
                posIndex[e.id] = posCounts[key] - 1;
            }
        });

        state.entities.forEach(entityState => {
            const isActive = state.active_entity === entityState.id;
            let totalAtPos = 1;
            let indexAtPos = 0;
            if (entityState.pos) {
                const key = `${entityState.pos[0]},${entityState.pos[1]}`;
                totalAtPos = posCounts[key];
                indexAtPos = posIndex[entityState.id];
            }
            const container = this.drawEntity(entityState, isActive, totalAtPos, indexAtPos);

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
                duration: 200,
                ease: 'Sine.easeInOut',
            }));

            this.tweens.chain({
                targets: actor,
                tweens: tweens,
                onComplete: () => {
                    if (targetPos) {
                        this.drawAttackArrow(actor.x, actor.y, this.gridOffsetX + targetPos[0] * this.tileSize + this.tileSize / 2, this.gridOffsetY + targetPos[1] * this.tileSize + this.tileSize / 2);
                        this.showDamagePop(actor.x, actor.y, targetPos);
                    }
                },
            });
        } else if (targetPos) {
            this.drawAttackArrow(actor.x, actor.y, this.gridOffsetX + targetPos[0] * this.tileSize + this.tileSize / 2, this.gridOffsetY + targetPos[1] * this.tileSize + this.tileSize / 2);
            this.showDamagePop(actor.x, actor.y, targetPos);
        }
    }

    private showDamagePop(fromX: number, fromY: number, toPos: [number, number]) {
        const toX = this.gridOffsetX + toPos[0] * this.tileSize + this.tileSize / 2;
        const toY = this.gridOffsetY + toPos[1] * this.tileSize + this.tileSize / 2;
        const midX = (fromX + toX) / 2;
        const midY = Math.min(fromY, toY) - this.tileSize * 0.4;

        const pop = this.add.text(midX, midY, '⚔', {
            fontSize: `${this.tileSize * 0.4}px`,
            color: '#ff4444',
            fontFamily: 'monospace',
            stroke: '#000',
            strokeThickness: 3,
        }).setOrigin(0.5).setAlpha(1);
        this.overlaysGroup.add(pop);

        this.tweens.add({
            targets: pop,
            y: midY - 30,
            alpha: 0,
            duration: 1000,
            ease: 'Quad.easeOut',
            onComplete: () => pop.destroy(),
        });
    }

    private drawAttackArrow(fromX: number, fromY: number, toX: number, toY: number) {
        if (fromX === toX && fromY === toY) return;
        const arrow = this.add.graphics();
        arrow.lineStyle(3, 0xff8800, 0.9);

        arrow.beginPath();
        arrow.moveTo(fromX, fromY);
        arrow.lineTo(toX, toY);

        const angle = Phaser.Math.Angle.Between(fromX, fromY, toX, toY);
        const arrowHeadLength = 12;

        arrow.lineTo(toX - arrowHeadLength * Math.cos(angle - Math.PI / 6), toY - arrowHeadLength * Math.sin(angle - Math.PI / 6));
        arrow.moveTo(toX, toY);
        arrow.lineTo(toX - arrowHeadLength * Math.cos(angle + Math.PI / 6), toY - arrowHeadLength * Math.sin(angle + Math.PI / 6));

        arrow.strokePath();
        this.overlaysGroup.add(arrow);
    }

    private drawEntity(entity: EntityState, isActive: boolean, totalAtPos: number, indexAtPos: number) {
        if (!entity.pos) return null;
        const [x, y] = entity.pos as [number, number];
        let pixelX = this.gridOffsetX + x * this.tileSize + this.tileSize / 2;
        let pixelY = this.gridOffsetY + y * this.tileSize + this.tileSize / 2;

        if (totalAtPos > 1) {
            const offset = (indexAtPos - (totalAtPos - 1) / 2) * (this.tileSize * 0.25);
            pixelX += offset;
            pixelY += offset;
        }

        const isDead = entity.hp <= 0;
        const entityContainer = this.add.container(pixelX, pixelY);

        // Team-colored background disc
        const bg = this.add.graphics();
        const radius = this.tileSize * 0.4;
        const teamColor = isDead ? 0x444444 : TEAM_COLORS[entity.team];

        bg.fillStyle(teamColor, isDead ? 0.4 : 0.85);
        bg.fillCircle(0, 0, radius);
        bg.lineStyle(2, isDead ? 0x666666 : TEAM_COLORS_LIGHT[entity.team], 1);
        bg.strokeCircle(0, 0, radius);
        entityContainer.add(bg);

        // Active entity highlight ring
        if (isActive && !isDead) {
            const ring = this.add.graphics();
            ring.lineStyle(3, 0xffff44, 1);
            ring.strokeCircle(0, 0, radius + 4);
            entityContainer.add(ring);
        }

        // Entity name
        const displayName = isDead ? `💀${entity.name}` : entity.name;
        const nameText = this.add.text(0, 0, displayName, {
            fontSize: `${Math.max(10, this.tileSize * 0.22)}px`,
            align: 'center',
            color: '#ffffff',
            fontFamily: 'monospace',
            fontStyle: isDead ? 'normal' : 'bold',
            stroke: '#000000',
            strokeThickness: 3,
            wordWrap: { width: this.tileSize * 0.8, useAdvancedWrap: true },
        }).setOrigin(0.5);
        entityContainer.add(nameText);

        // HP indicator
        const hpY = radius + 2;
        const hpColor = isDead ? 0x666666 : getHpColor(entity.hp);
        const hpBg = this.add.graphics();
        hpBg.fillStyle(0x222222, 0.8);
        hpBg.fillRoundedRect(-radius, hpY - 4, radius * 2, 10, 3);
        entityContainer.add(hpBg);

        const hpFg = this.add.graphics();
        // Scale bar against a reasonable max (12 = max hero HP in current heroes)
        const hpWidth = Math.max(2, Math.min(radius * 2, (entity.hp / 12) * radius * 2));
        hpFg.fillStyle(hpColor, 1);
        hpFg.fillRoundedRect(-radius, hpY - 4, hpWidth, 10, 3);
        entityContainer.add(hpFg);

        const hpText = this.add.text(0, hpY + 1, `${entity.hp}`, {
            fontSize: '10px',
            color: '#ffffff',
            fontFamily: 'monospace',
            fontStyle: 'bold',
            stroke: '#000000',
            strokeThickness: 2,
        }).setOrigin(0.5);
        entityContainer.add(hpText);

        // Modifier badges (small colored dots)
        if (entity.modifiers && entity.modifiers.length > 0) {
            const mods = entity.modifiers.slice(0, 4);
            const dotY = hpY + 12;
            const dotStartX = -(mods.length - 1) * 5;
            mods.forEach((mod, i) => {
                const dot = this.add.graphics();
                dot.fillStyle(0xffcc00, 0.9);
                dot.fillCircle(dotStartX + i * 10, dotY, 3);
                entityContainer.add(dot);

                // First modifier gets a label
                if (i === 0) {
                    const label = this.add.text(dotStartX - 4, dotY + 5, mod.substring(0, 8), {
                        fontSize: '7px',
                        color: '#ffcc00',
                        fontFamily: 'monospace',
                    }).setOrigin(0, 0);
                    entityContainer.add(label);
                }
            });
        }

        this.entitiesGroup.add(entityContainer);
        return entityContainer;
    }
}
