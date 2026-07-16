import { describe, it, expect, vi, beforeEach } from 'vitest';
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
    expect(axe).toHaveStyle('background: #eef');
  });

  it('places hero on grid cell click', async () => {
    render(<SetupScreen onPlay={() => {}} />);
    const axe = await screen.findByText('Axe');
    fireEvent.click(axe);

    const cell = screen.getByText('0,0');
    fireEvent.click(cell);

    expect(screen.getByText('Axe')).toBeInTheDocument();
  });

  it('removes hero from team on × click', async () => {
    render(<SetupScreen onPlay={() => {}} />);
    const axe = await screen.findByText('Axe');
    fireEvent.click(axe);

    const cell = screen.getByText('0,0');
    fireEvent.click(cell);

    const removeBtn = screen.getByText('×');
    fireEvent.click(removeBtn);
    expect(screen.queryByText('Axe')).toBeNull();
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

    fireEvent.click(screen.getByText('Red Team (0)'));
    fireEvent.click(necro);
    fireEvent.click(screen.getByText('4,4'));

    fireEvent.click(screen.getByText('Blue Team (1)'));
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
