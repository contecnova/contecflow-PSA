import { vi, describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import OfflineIndicator from '../components/OfflineIndicator';

// Mock any i18n/context dependencies that OfflineIndicator may pull in transitively
vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => (key) => key,
  useAppLang: () => ({ t: (key) => key, lang: 'es' }),
}));

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

vi.mock('../services/offlineQueue', () => ({
  pendingCount: vi.fn().mockReturnValue(0),
  syncPending: vi.fn().mockResolvedValue(undefined),
}));

describe('OfflineIndicator', () => {
  it('renderiza el componente sin errores', () => {
    const { container } = render(<OfflineIndicator />);
    // Component renders (online state shows no visible indicator, or shows status)
    expect(container.firstChild).toBeDefined();
  });
});
