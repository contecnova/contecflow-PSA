import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import OfflineIndicator from '../components/OfflineIndicator';

describe('OfflineIndicator', () => {
  it('renderiza el componente y muestra el estado online/offline', () => {
    render(<OfflineIndicator />);
    // El texto puede variar según el estado real, pero debe renderizar algo
    expect(screen.getByText(/offline|online/i)).toBeInTheDocument();
  });
});
