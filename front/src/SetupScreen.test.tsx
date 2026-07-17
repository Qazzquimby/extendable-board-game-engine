import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SetupScreen } from './SetupScreen';

beforeEach(() => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(['Axe', 'Necrophos', 'MeleeHero']),
  } as Response);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('SetupScreen', () => {
  it('renders hero roster fetched from API', async () => {
    render(<SetupScreen onPlay={() => {}} />);
    expect(await screen.findByText('Axe')).toBeInTheDocument();
    expect(screen.getByText('Necrophos')).toBeInTheDocument();
    expect(screen.getByText('MeleeHero')).toBeInTheDocument();
  });

  it('highlights selected hero', async () => {
    render(<SetupScreen onPlay={() => {}} />);
    const axe = await screen.findByText('Axe');
    fireEvent.click(axe);
    expect(axe).toHaveStyle('background: #f0f8ff');
  });

  it('places hero on grid cell click', async () => {
    render(<SetupScreen onPlay={() => {}} />);
    const axe = await screen.findByText('Axe');
    fireEvent.click(axe);

    const cell = screen.getByText('0,0');
    fireEvent.click(cell);

    // Hero appears in team panel with coordinates
    expect(screen.getByText(/Axe \[0,0\]/)).toBeInTheDocument();
  });

  it('removes hero from team on × click', async () => {
    render(<SetupScreen onPlay={() => {}} />);
    const axe = await screen.findByText('Axe');
    fireEvent.click(axe);

    const cell = screen.getByText('0,0');
    fireEvent.click(cell);

    // Placed hero appears in team panel with coordinates
    expect(screen.getByText(/Axe \[0,0\]/)).toBeInTheDocument();

    const removeBtn = screen.getByText('×');
    fireEvent.click(removeBtn);

    // Hero removed from team panel
    expect(screen.queryByText(/Axe \[0,0\]/)).toBeNull();
  });

  it('allows duplicate heroes on the same team', async () => {
    render(<SetupScreen onPlay={() => {}} />);
    const axe = await screen.findByText('Axe');

    // Place Axe twice on team 0
    fireEvent.click(axe);
    fireEvent.click(screen.getByText('0,0'));

    // Select Axe again (still in roster since duplicates allowed)
    const axeBtns = screen.getAllByText('Axe');
    fireEvent.click(axeBtns[0]);
    fireEvent.click(screen.getByText('0,1'));

    // Team panel shows both placements
    expect(screen.getByText(/Axe \[0,0\]/)).toBeInTheDocument();
    expect(screen.getByText(/Axe \[0,1\]/)).toBeInTheDocument();
  });

  it('disables Play button when teams are empty', () => {
    render(<SetupScreen onPlay={() => {}} />);
    expect(screen.getByText('▶ Play')).toBeDisabled();
  });

  it('disables Play button when only one team has heroes', async () => {
    render(<SetupScreen onPlay={() => {}} />);
    const axe = await screen.findByText('Axe');
    fireEvent.click(axe);

    const cell = screen.getByText('0,0');
    fireEvent.click(cell);

    expect(screen.getByText('▶ Play')).toBeDisabled();
  });

  it('calls onPlay with game log when Play is clicked', async () => {
    const onPlay = vi.fn();
    render(<SetupScreen onPlay={onPlay} />);

    const axe = await screen.findByText('Axe');
    const necro = screen.getByText('Necrophos');
    const melee = screen.getByText('MeleeHero');
    fireEvent.click(axe);
    fireEvent.click(screen.getByText('0,0'));

    fireEvent.click(screen.getByText('Team 2 (0)'));
    fireEvent.click(necro);
    fireEvent.click(screen.getByText('4,4'));

    fireEvent.click(screen.getByText('Team 1 (1)'));
    fireEvent.click(melee);
    fireEvent.click(screen.getByText('4,3'));

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ winner_team: 0, logs: [] }),
    } as Response);

    fireEvent.click(screen.getByText('▶ Play'));
    await vi.waitFor(() => expect(onPlay).toHaveBeenCalled());
  });
});
