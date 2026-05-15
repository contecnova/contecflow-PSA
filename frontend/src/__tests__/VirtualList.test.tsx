import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import VirtualList from '../components/ui/VirtualList';

describe('VirtualList', () => {
  it('renderiza la lista virtual con los elementos visibles', () => {
    const items = Array.from({ length: 20 }, (_, i) => `Item ${i + 1}`);
    render(
      <VirtualList
        items={items}
        renderRow={item => <div>{item}</div>}
        rowHeight={20}
        height={100}
      />
    );
    // Debe renderizar al menos un elemento visible
    expect(document.body.textContent).toMatch(/Item/);
  });
});
