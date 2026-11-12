import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const FILE_PATH = path.resolve(__dirname, 'NeuroPanel.tsx');
const src = fs.readFileSync(FILE_PATH, 'utf-8');

describe('NeuroPanel patterns (BUG-008 regression)', () => {
  it('declares an isMounted ref to guard async state updates', () => {
    expect(src).toContain('const isMounted = useRef(true);');
  });

  it('sets isMounted to true on mount and false on unmount', () => {
    expect(src).toContain('isMounted.current = true;');
    expect(src).toContain('isMounted.current = false;');
  });

  it('checks isMounted before setState calls in loadRecent', () => {
    // Find the loadRecent function block
    const loadRecentMatch = src.match(
      /const loadRecent = useCallback\(async \(offset = 0\) => \{([\s\S]*?)\}, \[conversationId\]\);/,
    );
    expect(loadRecentMatch).toBeTruthy();
    const loadRecentBody = loadRecentMatch![1];

    // Must check isMounted after the async call and before state updates
    expect(loadRecentBody).toContain('if (!isMounted.current) return;');

    // Must check isMounted in catch block
    expect(loadRecentBody).toMatch(/catch\s*\([^)]*\)\s*\{[\s\S]*?if \(!isMounted\.current\) return;/);

    // The settled status (ok / error) is written only after an isMounted guard,
    // and there is no unguarded `finally` left to write it.
    expect(loadRecentBody).not.toContain('finally');
    expect(loadRecentBody.indexOf('setRecent(READY)')).toBeGreaterThan(loadRecentBody.indexOf('if (!isMounted.current) return;'));
  });
});
