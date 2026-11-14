import { describe, it, expect } from 'vitest';
import { validateRunRequest, validateRunFollowupRequest, ValidationError } from './security-server';

describe('validateRunRequest', () => {
  const base = {
    problem: 'test',
    preset: 'multi-perspective-budget',
    top_k: 2,
    sequential: false,
    enhance_prompt: true,
  };

  it('passes through optional fields sent by frontend (H2 detection)', () => {
    const result = validateRunRequest({
      ...base,
      expert: true,
      web_search: false,
      smart_search: true,
      attachments: [{ id: '1', name: 'f.txt' }],
      client_run_id: 'run-123',
    });
    expect(result.expert).toBe(true);
    expect(result.web_search).toBe(false);
    expect(result.smart_search).toBe(true);
    expect(result.attachments).toEqual([{ id: '1', name: 'f.txt' }]);
    expect(result.client_run_id).toBe('run-123');
  });

  it('passes facts (max 3, <= 200 chars) and jurisdiction through', () => {
    const result = validateRunRequest({
      ...base,
      jurisdiction: 'GR',
      facts: { a: '1', b: '2', c: '3', d: '4', long: 'x'.repeat(201), bad: 5 },
    });
    expect(result.jurisdiction).toBe('GR');
    expect(Object.keys(result.facts ?? {})).toEqual(['a', 'b', 'c']);
  });

  it('ignores invalid-typed optional fields (boundary)', () => {
    const result = validateRunRequest({
      ...base,
      expert: 'not-bool',
      attachments: 'not-array',
      client_run_id: 123,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    expect(result.expert).toBeUndefined();
    expect(result.attachments).toBeUndefined();
    expect(result.client_run_id).toBeUndefined();
  });

  it('returns minimal object when no extras (state attack)', () => {
    const result = validateRunRequest(base);
    expect(Object.keys(result)).toEqual([
      'problem', 'preset', 'top_k', 'sequential', 'enhance_prompt',
    ]);
  });

  it('still validates required fields (regression)', () => {
    expect(() => validateRunRequest({ ...base, problem: '' })).toThrow(ValidationError);
    expect(() => validateRunRequest({ ...base, preset: '' })).toThrow(ValidationError);
    expect(() => validateRunRequest({ ...base, top_k: 99 })).toThrow(ValidationError);
  });
});

describe('validateRunFollowupRequest', () => {
  const base = {
    question: 'q',
    preset: 'multi-perspective-budget',
    top_k: 2,
    sequential: false,
    enhance_prompt: true,
    conversation_id: 'cid',
    history: [{ role: 'user' as const, content: 'hi' }],
    previous_synthesis: 'syn',
    agent_model: null,
  };

  it('passes through optional fields (H2 detection)', () => {
    const result = validateRunFollowupRequest({
      ...base,
      expert: true,
      attachments: [{ id: '1' }],
      client_run_id: 'run-456',
    });
    expect(result.expert).toBe(true);
    expect(result.attachments).toEqual([{ id: '1' }]);
    expect(result.client_run_id).toBe('run-456');
  });

  it('ignores bad-typed optional fields (boundary)', () => {
    const result = validateRunFollowupRequest({
      ...base,
      expert: 'nope',
      attachments: 'nope',
      client_run_id: 123,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    expect(result.expert).toBeUndefined();
    expect(result.attachments).toBeUndefined();
    expect(result.client_run_id).toBeUndefined();
  });
});
