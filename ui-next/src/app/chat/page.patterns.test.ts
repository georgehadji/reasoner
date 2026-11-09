import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const PAGE_PATH = path.resolve(__dirname, 'page.tsx');
const src = fs.readFileSync(PAGE_PATH, 'utf-8');

describe('chat/page.tsx patterns (BUG-002 & BUG-005 regression)', () => {
  it('does not mutate phases arrays via .push()', () => {
    // Before fix, phases.push(renderedPhase) and resumePhases.push(renderedPhase) existed
    const pushMatches = src.match(/phases\.push\(/g) || [];
    const resumePushMatches = src.match(/resumePhases\.push\(/g) || [];

    expect(pushMatches).toHaveLength(0);
    expect(resumePushMatches).toHaveLength(0);
  });

  it('uses immutable spread for phase accumulation', () => {
    // After fix: phases = [...phases, renderedPhase];
    expect(src).toContain('phases = [...phases, renderedPhase]');
    expect(src).toContain('resumePhases = [...resumePhases, renderedPhase]');
  });

  it('declares phases as let (reassignable) instead of const', () => {
    // After fix: let phases: RenderedPhase[] = [];
    expect(src).toContain('let phases: RenderedPhase[] = []');
    expect(src).toContain('let resumePhases: RenderedPhase[] = []');
  });

  it('includes RAF cleanup useEffect on unmount (BUG-005)', () => {
    // After fix: useEffect(() => { return () => { if (chunkFlushRafRef.current !== null) { cancelAnimationFrame(...) } } }, [])
    expect(src).toContain('cancelAnimationFrame(chunkFlushRafRef.current)');
    expect(src).toContain("useEffect(() => {\n    return () => {\n      if (chunkFlushRafRef.current !== null) {\n        cancelAnimationFrame(chunkFlushRafRef.current);\n        chunkFlushRafRef.current = null;\n      }\n    };\n  }, []);");
  });
});

describe('chat/page.tsx image-mode errors are shown', () => {
  // Image mode adds the reply bubble only after prompt enhancement succeeds. An
  // error before that (a 401 from /api/generate-image when signed out) was sent
  // as UPDATE_MESSAGE to a bubble that did not exist yet, so the user saw nothing.
  const start = src.indexOf('// ── Image Generation mode ──');
  const end = src.indexOf('} finally {', start);
  const imageBlock = src.slice(start, end);

  it('tracks whether the reply bubble has been added', () => {
    expect(imageBlock).toContain('let replyAdded = false;');
    expect(imageBlock).toContain('replyAdded = true;');
  });

  it('adds the bubble with the error when it does not exist yet', () => {
    expect(imageBlock).toContain('showImageResult(');
    expect(src).toMatch(/const showImageResult = \(added: boolean[\s\S]*?type: 'ADD_MESSAGES'[\s\S]*?type: 'UPDATE_MESSAGE'/);
  });
});

describe('WebSocket side channel is signed-in only', () => {
  // A ticket needs an authenticated user (POST /api/websocket/ticket), so an
  // anonymous run got a 401 and the header dot turned red with "Could not
  // obtain a connection ticket (401)". The run itself streams over SSE and
  // Stop has an HTTP fallback, so anonymous runs skip the socket.
  it('connects only when a user is signed in', () => {
    expect(src).toMatch(/if \(user\) wsConnect\(clientRunId/);
    expect(src).not.toMatch(/^\s*wsConnect\(clientRunId/m);
  });
});
