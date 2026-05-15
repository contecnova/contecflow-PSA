import { vi, describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import GanttChart from '../components/GanttChart';

// GanttChart uses useAppT() for translated labels
vi.mock('../i18n/AppLangContext', () => ({
  useAppT: () => (key) => key,
  useAppLang: () => ({ t: (key) => key, lang: 'es' }),
}));

describe('GanttChart', () => {
  it('renderiza el componente GanttChart', () => {
    const { container } = render(<GanttChart tasks={[]} />);
    expect(container.firstChild).toBeDefined();
  });
});
