import { vi, describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ResourceDashboard from '../components/ResourceDashboard';

// Return null for team-health so teamHealth state stays null (avoids .toFixed crash)
// Return [] for load-scoring so filteredUsers is an empty array
vi.mock('../services/api', () => ({
  default: {
    get: vi.fn().mockImplementation((url) => {
      if (url.includes('team-health')) return Promise.resolve({ data: null });
      return Promise.resolve({ data: [] });
    }),
  },
}));

describe('ResourceDashboard', () => {
  it('renderiza el dashboard de recursos', async () => {
    render(<ResourceDashboard />);
    // Loading state shown initially; wait until component finishes loading
    await waitFor(() =>
      expect(screen.getByText(/Resource Load Ranking/i)).toBeInTheDocument()
    );
  });
});
