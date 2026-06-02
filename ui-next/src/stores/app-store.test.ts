/**
 * State management tests for app-store.ts (Zustand store).
 *
 * Covers: state transitions, action side effects, attachment lifecycle,
 * active run management, auth state, recent commands, getAutoPreset.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useAppStore } from './app-store';

// Reset store before each test
beforeEach(() => {
  useAppStore.setState({
    running: false,
    tier: 'budget',
    isExpert: false,
    isImageMode: false,
    sidebarCollapsed: false,
    neuroPanelOpen: false,
    composerText: '',
    attachments: [],
    history: [],
    activeRun: null,
    recentCommands: [],
    user: null,
    isAuthenticated: false,
    isAuthLoading: true,
  });
});


describe('app-store — tier and mode toggles', () => {
  it('toggleTier switches budget ↔ premium', () => {
    expect(useAppStore.getState().tier).toBe('budget');
    useAppStore.getState().toggleTier();
    expect(useAppStore.getState().tier).toBe('premium');
    useAppStore.getState().toggleTier();
    expect(useAppStore.getState().tier).toBe('budget');
  });

  it('toggleExpert flips boolean', () => {
    expect(useAppStore.getState().isExpert).toBe(false);
    useAppStore.getState().toggleExpert();
    expect(useAppStore.getState().isExpert).toBe(true);
  });

  it('toggleImageMode flips boolean', () => {
    expect(useAppStore.getState().isImageMode).toBe(false);
    useAppStore.getState().toggleImageMode();
    expect(useAppStore.getState().isImageMode).toBe(true);
  });

  it('toggleSidebar flips boolean', () => {
    expect(useAppStore.getState().sidebarCollapsed).toBe(false);
    useAppStore.getState().toggleSidebar();
    expect(useAppStore.getState().sidebarCollapsed).toBe(true);
  });

  it('toggleNeuroPanel flips boolean', () => {
    expect(useAppStore.getState().neuroPanelOpen).toBe(false);
    useAppStore.getState().toggleNeuroPanel();
    expect(useAppStore.getState().neuroPanelOpen).toBe(true);
  });

  it('getAutoPreset returns correct string', () => {
    expect(useAppStore.getState().getAutoPreset()).toBe('auto-budget');
    useAppStore.getState().toggleTier();
    expect(useAppStore.getState().getAutoPreset()).toBe('auto-premium');
  });
});


describe('app-store — composer and attachments', () => {
  it('setComposerText updates text', () => {
    useAppStore.getState().setComposerText('Hello world');
    expect(useAppStore.getState().composerText).toBe('Hello world');
  });

  it('addAttachment adds a file', () => {
    const file = new File(['content'], 'test.txt', { type: 'text/plain' });
    useAppStore.getState().addAttachment(file);
    const attachments = useAppStore.getState().attachments;
    expect(attachments).toHaveLength(1);
    expect(attachments[0].name).toBe('test.txt');
    expect(attachments[0].size).toBe(7);
    expect(attachments[0].type).toBe('text/plain');
    expect(attachments[0].id).toMatch(/^att-/);
  });

  it('addAttachment generates unique IDs', () => {
    const file1 = new File(['a'], 'a.txt');
    const file2 = new File(['b'], 'b.txt');
    useAppStore.getState().addAttachment(file1);
    useAppStore.getState().addAttachment(file2);
    const attachments = useAppStore.getState().attachments;
    expect(attachments).toHaveLength(2);
    expect(attachments[0].id).not.toBe(attachments[1].id);
  });

  it('addAttachment enforces max limit', () => {
    for (let i = 0; i < 10; i++) {
      useAppStore.getState().addAttachment(new File([`${i}`], `f${i}.txt`));
    }
    // LIMITS.maxAttachments is 5
    expect(useAppStore.getState().attachments.length).toBe(5);
  });

  it('removeAttachment removes by ID', () => {
    const file = new File(['x'], 'x.txt');
    useAppStore.getState().addAttachment(file);
    const id = useAppStore.getState().attachments[0].id;
    useAppStore.getState().removeAttachment(id);
    expect(useAppStore.getState().attachments).toHaveLength(0);
  });

  it('removeAttachment is no-op for unknown ID', () => {
    const file = new File(['x'], 'x.txt');
    useAppStore.getState().addAttachment(file);
    useAppStore.getState().removeAttachment('nonexistent');
    expect(useAppStore.getState().attachments).toHaveLength(1);
  });

  it('clearAttachments removes all', () => {
    for (let i = 0; i < 3; i++) {
      useAppStore.getState().addAttachment(new File([`${i}`], `f${i}.txt`));
    }
    useAppStore.getState().clearAttachments();
    expect(useAppStore.getState().attachments).toHaveLength(0);
  });
});


describe('app-store — active run management', () => {
  it('setActiveRun sets the run', () => {
    useAppStore.getState().setActiveRun({
      progressId: 'run-1',
      problem: 'Test',
      phases: [],
      errors: [],
      preset: 'test-preset',
      autoSelectedMethod: null,
    });
    const run = useAppStore.getState().activeRun;
    expect(run?.progressId).toBe('run-1');
    expect(run?.problem).toBe('Test');
  });

  it('addPhaseToActiveRun appends phases', () => {
    useAppStore.getState().setActiveRun({
      progressId: 'run-1',
      problem: 'Test',
      phases: [],
      errors: [],
      preset: 'p',
      autoSelectedMethod: null,
    });
    useAppStore.getState().addPhaseToActiveRun({ phase: 1, name: 'Classify', data: {} });
    useAppStore.getState().addPhaseToActiveRun({ phase: 2, name: 'Analyze', data: {} });
    const phases = useAppStore.getState().activeRun?.phases;
    expect(phases).toHaveLength(2);
    expect(phases?.[0].name).toBe('Classify');
    expect(phases?.[1].name).toBe('Analyze');
  });

  it('addPhaseToActiveRun is no-op when no active run', () => {
    useAppStore.getState().addPhaseToActiveRun({ phase: 1, name: 'Test', data: {} });
    expect(useAppStore.getState().activeRun).toBeNull();
  });

  it('setActiveRunErrors updates errors', () => {
    useAppStore.getState().setActiveRun({
      progressId: 'run-1',
      problem: 'Test',
      phases: [],
      errors: [],
      preset: 'p',
      autoSelectedMethod: null,
    });
    useAppStore.getState().setActiveRunErrors(['Error 1', 'Error 2']);
    expect(useAppStore.getState().activeRun?.errors).toEqual(['Error 1', 'Error 2']);
  });

  it('clearActiveRun resets to null', () => {
    useAppStore.getState().setActiveRun({
      progressId: 'run-1',
      problem: 'Test',
      phases: [],
      errors: [],
      preset: 'p',
      autoSelectedMethod: null,
    });
    useAppStore.getState().clearActiveRun();
    expect(useAppStore.getState().activeRun).toBeNull();
  });

  it('setRunning updates running flag', () => {
    useAppStore.getState().setRunning(true);
    expect(useAppStore.getState().running).toBe(true);
    useAppStore.getState().setRunning(false);
    expect(useAppStore.getState().running).toBe(false);
  });
});


describe('app-store — auth management', () => {
  it('setUser updates auth state', () => {
    const mockUser = { id: 'user-1', email: 'test@test.com' } as any;
    useAppStore.getState().setUser(mockUser);
    expect(useAppStore.getState().user).toBe(mockUser);
    expect(useAppStore.getState().isAuthenticated).toBe(true);
  });

  it('setUser with null clears auth', () => {
    const mockUser = { id: 'user-1' } as any;
    useAppStore.getState().setUser(mockUser);
    useAppStore.getState().setUser(null);
    expect(useAppStore.getState().user).toBeNull();
    expect(useAppStore.getState().isAuthenticated).toBe(false);
  });

  it('logout clears user and sets authenticated false', () => {
    const mockUser = { id: 'user-1' } as any;
    useAppStore.getState().setUser(mockUser);
    useAppStore.getState().logout();
    expect(useAppStore.getState().user).toBeNull();
    expect(useAppStore.getState().isAuthenticated).toBe(false);
  });

  it('setAuthLoading toggles loading flag', () => {
    useAppStore.getState().setAuthLoading(true);
    expect(useAppStore.getState().isAuthLoading).toBe(true);
    useAppStore.getState().setAuthLoading(false);
    expect(useAppStore.getState().isAuthLoading).toBe(false);
  });
});


describe('app-store — recent commands', () => {
  it('addRecentCommand adds to front', () => {
    useAppStore.getState().addRecentCommand('cmd1');
    useAppStore.getState().addRecentCommand('cmd2');
    const commands = useAppStore.getState().recentCommands;
    expect(commands).toEqual(['cmd2', 'cmd1']);
  });

  it('addRecentCommand deduplicates', () => {
    useAppStore.getState().addRecentCommand('cmd1');
    useAppStore.getState().addRecentCommand('cmd2');
    useAppStore.getState().addRecentCommand('cmd1');
    const commands = useAppStore.getState().recentCommands;
    expect(commands).toEqual(['cmd1', 'cmd2']);
  });

  it('addRecentCommand enforces max limit', () => {
    for (let i = 0; i < 10; i++) {
      useAppStore.getState().addRecentCommand(`cmd${i}`);
    }
    // LIMITS.maxRecentCommands is 3
    expect(useAppStore.getState().recentCommands).toHaveLength(3);
  });
});


describe('app-store — history', () => {
  it('setHistory updates history', () => {
    const conversations = [
      {
        id: '1',
        conversation_id: 'conv-1',
        turn_number: 1,
        timestamp: new Date().toISOString(),
        problem: 'Test',
        phases: [],
        errors: [],
        preset: 'test',
        method: 'multi-perspective',
        total_tokens: null,
      },
    ];
    useAppStore.getState().setHistory(conversations);
    expect(useAppStore.getState().history).toEqual(conversations);
  });
});
