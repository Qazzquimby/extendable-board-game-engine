import { EngineState, EntityState } from '../types';

interface FrameEvent {
  type: string;
  actor_id?: number | null;
  target_id?: number | null;
  ability_name?: string | null;
  amount?: number | null;
  source_pos?: [number, number] | null;
  target_pos?: [number, number] | null;
  source_id?: number | null;
  [k: string]: unknown;
}
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
    public isAnimating = false;
    private onAnimComplete: (() => void) | null = null;
    private isDragging = false;
    private dragPointer: { x: number; y: number } | null = null;

    constructor() {
        super('GameScene');
        this.entitiesGroup = new Phaser.GameObjects.Group(this);
        this.overlaysGroup = new Phaser.GameObjects.Group(this);
        this.uiGroup = new Phaser.GameObjects.Group(this);
    }

    create() {
        // Enable zoom with scroll wheel
        this.input.on('wheel', (_pointer: Phaser.Input.Pointer, _gameObjects: any[], _deltaX: number, deltaY: number) => {
            const cam = this.cameras.main;
            const step = deltaY > 0 ? -0.1 : 0.1;
            const newZoom = Phaser.Math.Clamp(cam.zoom + step, 0.3, 3);
            cam.setZoom(newZoom);
        });

        // Enable drag-to-pan
        this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
            this.isDragging = true;
            this.dragPointer = { x: pointer.x, y: pointer.y };
        });

        this.input.on('pointermove', (pointer: Phaser.Input.Pointer) => {
            if (this.isDragging && this.dragPointer) {
                const cam = this.cameras.main;
                const dx = pointer.x - this.dragPointer.x;
                const dy = pointer.y - this.dragPointer.y;
                cam.scrollX -= dx / cam.zoom;
                cam.scrollY -= dy / cam.zoom;
                this.dragPointer = { x: pointer.x, y: pointer.y };
            }
        });

        this.input.on('pointerup', () => {
            this.isDragging = false;
            this.dragPointer = null;
        });
    }

    public setAnimationCallback(cb: () => void) {
        this.onAnimComplete = cb;
    }

    public updateEngineState(state: EngineState, events?: FrameEvent[]) {
        if (this.entitiesGroup && this.overlaysGroup) {
            this.drawState(state, events || []);
        } else {
            this.events.once(Phaser.Scenes.Events.CREATE, () => {
                this.drawState(state, events || []);
            });
        }
    }

    private drawState(state: EngineState, events: FrameEvent[]) {
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

        const posCounts: Record<string, number> = {};
        const posIndex: Record<number, number> = {};

        state.entities.forEach(e => {
            if (e.pos) {
                const key = `${e.pos[0]},${e.pos[1]}`;
                posCounts[key] = (posCounts[key] || 0) + 1;
                posIndex[e.id] = posCounts[key] - 1;
            }
        });

        // Store containers for animation reference
        const entityContainers: Map<number, Phaser.GameObjects.Container> = new Map();

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
            if (container) entityContainers.set(entityState.id, container);
        });

        // Animate based on events
        if (events.length > 0) {
            this.animateFromEvents(events, entityContainers);
        }
    }

    private animateFromEvents(events: FrameEvent[], entityContainers: Map<number, Phaser.GameObjects.Container>) {
        this.isAnimating = true;
        let totalDuration = 0;

        for (const event of events) {
            const t = event.type;
            const tid = event.target_id;
            const sid = event.source_id;

            if (t === 'move' && tid != null && event.source_pos && event.target_pos) {
                const container = entityContainers.get(tid);
                if (container) {
                    // Start entity at source position for animation
                    const srcPixX = this.gridOffsetX + event.source_pos[0] * this.tileSize + this.tileSize / 2;
                    const srcPixY = this.gridOffsetY + event.source_pos[1] * this.tileSize + this.tileSize / 2;
                    const dstPixX = this.gridOffsetX + event.target_pos[0] * this.tileSize + this.tileSize / 2;
                    const dstPixY = this.gridOffsetY + event.target_pos[1] * this.tileSize + this.tileSize / 2;

                    // Place at source and tween to destination
                    container.setPosition(srcPixX, srcPixY);
                    const dur = 250;
                    this.tweens.add({
                        targets: container,
                        x: dstPixX,
                        y: dstPixY,
                        duration: dur,
                        ease: 'Sine.easeInOut',
                    });
                    totalDuration = Math.max(totalDuration, dur);
                }
            }

            if (t === 'damage' && tid != null && event.amount != null) {
                // Show damage popup at target position
                let targetPixX: number, targetPixY: number;
                const container = entityContainers.get(tid);
                if (container) {
                    targetPixX = container.x;
                    targetPixY = container.y;
                } else if (event.target_pos) {
                    targetPixX = this.gridOffsetX + event.target_pos[0] * this.tileSize + this.tileSize / 2;
                    targetPixY = this.gridOffsetY + event.target_pos[1] * this.tileSize + this.tileSize / 2;
                } else {
                    return;
                }

                // Draw attack arrow from source to target
                if (sid != null && sid !== tid) {
                    const srcContainer = entityContainers.get(sid);
                    if (srcContainer) {
                        this.drawAttackArrow(srcContainer.x, srcContainer.y, targetPixX, targetPixY);
                    }
                }

                const damageText = this.add.text(
                    targetPixX + (Math.random() - 0.5) * 20,
                    targetPixY - 20,
                    `-${event.amount}`,
                    {
                        fontSize: `${this.tileSize * 0.3}px`,
                        color: '#ff4444',
                        fontFamily: 'Arial, sans-serif',
                        fontStyle: 'bold',
                        stroke: '#000000',
                        strokeThickness: 2,
                    }
                ).setOrigin(0.5).setAlpha(1);
                this.overlaysGroup.add(damageText);

                this.tweens.add({
                    targets: damageText,
                    y: damageText.y - 40,
                    alpha: 0,
                    duration: 800,
                    delay: 100,
                    ease: 'Quad.easeOut',
                    onComplete: () => damageText.destroy(),
                });
                totalDuration = Math.max(totalDuration, 900);
            }

            if (t === 'heal' && tid != null && event.amount != null) {
                const container = entityContainers.get(tid);
                if (container) {
                    const healText = this.add.text(
                        container.x + (Math.random() - 0.5) * 20,
                        container.y - 20,
                        `+${event.amount}`,
                        {
                            fontSize: `${this.tileSize * 0.3}px`,
                            color: '#44ff44',
                            fontFamily: 'Arial, sans-serif',
                            fontStyle: 'bold',
                            stroke: '#000000',
                            strokeThickness: 2,
                        }
                    ).setOrigin(0.5).setAlpha(1);
                    this.overlaysGroup.add(healText);

                    this.tweens.add({
                        targets: healText,
                        y: healText.y - 40,
                        alpha: 0,
                        duration: 800,
                        delay: 100,
                        ease: 'Quad.easeOut',
                        onComplete: () => healText.destroy(),
                    });
                    totalDuration = Math.max(totalDuration, 900);
                }
            }

            if (t === 'ability_use' && tid != null) {
                // Flash the actor
                const container = entityContainers.get(tid);
                if (container) {
                    // Show ability name above entity for a moment
                    const abilName = event.ability_name || 'Ability';
                    const abilText = this.add.text(
                        container.x,
                        container.y - this.tileSize * 0.5,
                        abilName,
                        {
                            fontSize: `${this.tileSize * 0.16}px`,
                            color: '#ffdd44',
                            fontFamily: 'Arial, sans-serif',
                            fontStyle: 'bold',
                            stroke: '#000000',
                            strokeThickness: 2,
                        }
                    ).setOrigin(0.5).setAlpha(0);
                    this.overlaysGroup.add(abilText);

                    this.tweens.add({
                        targets: abilText,
                        alpha: 1,
                        y: abilText.y - 10,
                        duration: 300,
                        ease: 'Quad.easeOut',
                        yoyo: true,
                        hold: 500,
                        onComplete: () => abilText.destroy(),
                    });
                    totalDuration = Math.max(totalDuration, 1100);
                }
            }
        }

        // After all animations, signal completion
        this.time.delayedCall(totalDuration + 50, () => {
            this.isAnimating = false;
            this.onAnimComplete?.();
        });
    }

    private showDamagePop(fromX: number, fromY: number, toPos: [number, number], onDone?: () => void) {
        const toX = this.gridOffsetX + toPos[0] * this.tileSize + this.tileSize / 2;
        const toY = this.gridOffsetY + toPos[1] * this.tileSize + this.tileSize / 2;
        const midX = (fromX + toX) / 2;
        const midY = Math.min(fromY, toY) - this.tileSize * 0.4;

        const pop = this.add.text(midX, midY, '⚔', {
            fontSize: `${this.tileSize * 0.4}px`,
            color: '#ff4444',
            fontFamily: 'Arial, sans-serif',
            stroke: '#000',
            strokeThickness: 2,
        }).setOrigin(0.5).setAlpha(1);
        this.overlaysGroup.add(pop);

        this.tweens.add({
            targets: pop,
            y: midY - 30,
            alpha: 0,
            duration: 800,
            ease: 'Quad.easeOut',
            onComplete: () => {
                pop.destroy();
                onDone?.();
            },
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
        const arrowHeadLength = Math.max(8, Math.round(this.tileSize * 0.12));

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

        // --- Entity name (near center, but slightly above so HP bar fits below) ---
        const displayName = isDead ? `💀${entity.name}` : entity.name;
        const nameFontSize = `${Math.max(11, Math.round(this.tileSize * 0.2))}px`;
        const nameText = this.add.text(0, -6, displayName, {
            fontSize: nameFontSize,
            align: 'center',
            color: '#ffffff',
            fontFamily: 'Arial, sans-serif',
            fontStyle: isDead ? 'normal' : 'bold',
            stroke: '#000000',
            strokeThickness: 1.5,
            wordWrap: { width: this.tileSize * 0.9, useAdvancedWrap: true },
        }).setOrigin(0.5);
        entityContainer.add(nameText);

        // --- HP bar (below name, within the disc) ---
        const hpColor = isDead ? 0x666666 : getHpColor(entity.hp);
        const hpBarY = 14;
        const hpBarWidth = radius * 1.6;
        const hpBg = this.add.graphics();
        hpBg.fillStyle(0x222222, 0.8);
        hpBg.fillRoundedRect(-hpBarWidth / 2, hpBarY, hpBarWidth, 8, 3);
        entityContainer.add(hpBg);

        const hpFg = this.add.graphics();
        const hpWidth = Math.max(2, Math.min(hpBarWidth, (entity.hp / 12) * hpBarWidth));
        hpFg.fillStyle(hpColor, 1);
        hpFg.fillRoundedRect(-hpBarWidth / 2, hpBarY, hpWidth, 8, 3);
        entityContainer.add(hpFg);

        const hpText = this.add.text(0, hpBarY + 9, `${entity.hp}`, {
            fontSize: `${Math.max(11, Math.round(this.tileSize * 0.1))}px`,
            color: '#ffffff',
            fontFamily: 'Arial, sans-serif',
            fontStyle: 'bold',
            stroke: '#000000',
            strokeThickness: 1,
        }).setOrigin(0.5, 0);
        entityContainer.add(hpText);

        this.entitiesGroup.add(entityContainer);
        return entityContainer;
    }
}
