import { vi, describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import TimerWidget from '../components/TimerWidget';

// TimerWidget uses useAuth() — mock to provide a user with hourly_rate
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', hourly_rate: 50 } }),
}));

// Mock api: return a running timer so the HH:MM:SS display is rendered.
// NOTE: mockTimer must be defined INSIDE vi.mock factory (not at module scope)
// because vi.mock() is hoisted to the top of the file by Vitest.
vi.mock('../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      data: {
        id: 'timer-1',
        project_id: 'proj-1',
        started_at: new Date().toISOString(),
        paused_at: null,
        paused_duration_secs: 0,
        total_elapsed_seconds: null,
      },
    }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

describe('TimerWidget', () => {
  it('renderiza el componente TimerWidget con el formato HH:MM:SS', async () => {
    render(<TimerWidget />);
    // After the API resolves, the running timer shows HH:MM:SS
    await waitFor(() =>
      expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
    );
  });
});
