import { vi, describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ResourceHeatmap from '../components/ResourceHeatmap';

// ResourceHeatmap uses useAppT() — mock the i18n hook
vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => (key: string) => key,
}));

// Mock the api service (useQuery internally calls api.get)
vi.mock('../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
  projectsApi: { get: vi.fn().mockResolvedValue({ data: [] }) },
  usersApi: { get: vi.fn().mockResolvedValue({ data: [] }) },
}));

vi.mock('../context/ConfirmContext', () => ({
  openConfirmGlobal: vi.fn().mockResolvedValue(true),
}));

vi.mock('../hooks/useFormValidation', () => ({
  useFormValidation: () => ({
    values: {},
    errors: {},
    handleChange: vi.fn(),
    validate: vi.fn().mockReturnValue(true),
    reset: vi.fn(),
    setValues: vi.fn(),
  }),
}));

describe('ResourceHeatmap', () => {
  it('monta el componente sin errores', () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <ResourceHeatmap />
      </QueryClientProvider>
    );
    expect(container.firstChild).not.toBeNull();
  });
});
