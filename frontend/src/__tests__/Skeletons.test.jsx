import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { SkeletonRows, SkeletonDashboard } from '../components/ui/Skeletons';

describe('Skeletons', () => {
  it('renderiza SkeletonRows con el número correcto de filas', () => {
    const { container } = render(<SkeletonRows count={3} cols={2} />);
    // Debe haber 3 filas principales
    expect(container.querySelectorAll('.skeleton-line').length).toBeGreaterThan(0);
  });

  it('renderiza SkeletonDashboard', () => {
    const { container } = render(<SkeletonDashboard />);
    expect(container.querySelectorAll('.skeleton-line').length).toBeGreaterThan(0);
  });
});
