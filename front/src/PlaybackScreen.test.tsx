import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlaybackScreen } from './PlaybackScreen';
import { GameLog } from './types';

vi.mock('./PhaserComponent', () => ({
  default: () => <div data-testid="phaser-mock" />,
}));

const mockGameLog: GameLog = {
  winner_team: 0,
  logs: [
    {
      before_state: {
        round_num: 1,
        current_team: 0,
        active_entity: 1,
        entities: [
          { id: 1, name: 'Axe', hp: 10, pos: [0, 0] as [number, number], team: 0, move_actions: 1, standard_actions: 1, free_actions: 99 },
          { id: 2, name: 'Necrophos', hp: 8, pos: [4, 4] as [number, number], team: 1, move_actions: 1, standard_actions: 1, free_actions: 99 },
        ],
      },
      action: { actor: 1, target: 2, ability: 'Battle Hunger', move_path: [[0, 0], [1, 0], [1, 1]] as [number, number][], movement_name: 'Move' },
      after_state: {
        round_num: 1,
        current_team: 0,
        active_entity: 1,
        entities: [
          { id: 1, name: 'Axe', hp: 10, pos: [1, 1] as [number, number], team: 0, move_actions: 0, standard_actions: 0, free_actions: 99 },
          { id: 2, name: 'Necrophos', hp: 8, pos: [4, 4] as [number, number], team: 1, move_actions: 1, standard_actions: 1, free_actions: 99 },
        ],
      },
      done: false,
      messages: ['Axe used Battle Hunger on Necrophos.'],
    },
  ],
};

describe('PlaybackScreen', () => {
  it('renders game title', () => {
    render(<PlaybackScreen gameLog={mockGameLog} onBack={() => {}} />);
    expect(screen.getByText(/Team Blue Wins/)).toBeInTheDocument();
  });

  it('renders step counter', () => {
    render(<PlaybackScreen gameLog={mockGameLog} onBack={() => {}} />);
    expect(screen.getByText(/Step 0 \/ 0/)).toBeInTheDocument();
  });

  it('renders written log messages', () => {
    render(<PlaybackScreen gameLog={mockGameLog} onBack={() => {}} />);
    expect(screen.getByText(/Axe used Battle Hunger/)).toBeInTheDocument();
  });

  it('renders entity panels', () => {
    render(<PlaybackScreen gameLog={mockGameLog} onBack={() => {}} />);
    expect(screen.getAllByText(/Axe/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Necrophos/).length).toBeGreaterThanOrEqual(1);
  });

  it('renders Phaser mock component', () => {
    render(<PlaybackScreen gameLog={mockGameLog} onBack={() => {}} />);
    expect(screen.getByTestId('phaser-mock')).toBeInTheDocument();
  });

  it('calls onBack when Setup button is clicked', () => {
    const onBack = vi.fn();
    render(<PlaybackScreen gameLog={mockGameLog} onBack={onBack} />);
    fireEvent.click(screen.getByText('← Setup'));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it('advances step on Next button click', () => {
    const gameLog: GameLog = {
      winner_team: null,
      logs: [
        { ...mockGameLog.logs[0] },
        { ...mockGameLog.logs[0], action: { ...mockGameLog.logs[0].action, ability: 'Other' }, messages: ['Second step'] },
      ],
    };
    render(<PlaybackScreen gameLog={gameLog} onBack={() => {}} />);
    expect(screen.getByText(/Step 0 \/ 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Next ▶'));
    expect(screen.getByText(/Step 1 \/ 1/)).toBeInTheDocument();
  });
});
