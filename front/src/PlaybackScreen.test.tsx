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
    // Entry 0: initial board state
    {
      state: {
        round_num: 1,
        current_team: 0,
        active_entity: 1,
        entities: [
          { id: 1, name: 'Axe', hp: 10, pos: [0, 0] as [number, number], team: 0, move_actions: 1, standard_actions: 1, free_actions: 99 },
          { id: 2, name: 'Necrophos', hp: 8, pos: [4, 4] as [number, number], team: 1, move_actions: 1, standard_actions: 1, free_actions: 99 },
        ],
      },
      events: [],
      done: false,
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
        {
          ...mockGameLog.logs[0],
          events: [{ type: 'damage', target_id: 1, amount: 3 }],
        },
      ],
    };
    render(<PlaybackScreen gameLog={gameLog} onBack={() => {}} />);
    expect(screen.getByText(/Step 0 \/ 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Next ▶'));
    expect(screen.getByText(/Step 1 \/ 1/)).toBeInTheDocument();
  });

  it('shows action_logs in the sidebar', () => {
    const gameLog: GameLog = {
      winner_team: null,
      logs: [
        mockGameLog.logs[0],
        {
          state: mockGameLog.logs[0].state,
          events: [{ type: 'damage', target_id: 1, amount: 3 }],
          action_logs: ['Axe used Battle Hunger.', '-- Axe dealt 3 damage to Necrophos.'],
          done: false,
        },
      ],
    };
    render(<PlaybackScreen gameLog={gameLog} onBack={() => {}} />);
    // Step to entry 1
    fireEvent.click(screen.getByText('Next ▶'));
    expect(screen.getByText(/Axe used Battle Hunger/)).toBeInTheDocument();
    expect(screen.getByText(/Axe dealt 3 damage/)).toBeInTheDocument();
    // Check sidebar shows the entry (several 'Step 1' on page, pick via container)
  });

  it('shows event summary for frames with events', () => {
    const gameLog: GameLog = {
      winner_team: 0,
      logs: [
        mockGameLog.logs[0],
        {
          state: mockGameLog.logs[0].state,
          events: [
            { type: 'ability_use', actor_id: 1, ability_name: 'Battle Hunger' },
            { type: 'move', target_id: 1 },
            { type: 'damage', target_id: 2, amount: 3 },
          ],
          done: false,
        },
      ],
    };
    render(<PlaybackScreen gameLog={gameLog} onBack={() => {}} />);
    // Step to entry 1
    fireEvent.click(screen.getByText('Next ▶'));
    expect(screen.getByText(/Battle Hunger/)).toBeInTheDocument();
    // We'll check that the sidebar renders event type summary
    const sidebarEls = screen.getAllByText(/damage/);
    expect(sidebarEls.length).toBeGreaterThanOrEqual(1);
  });
});
