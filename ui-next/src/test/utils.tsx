import React, { ReactElement } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { ThemeProvider } from 'next-themes';

// Simple auth provider mock for tests
function MockAuthProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
) {
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
        <MockAuthProvider>{children}</MockAuthProvider>
      </ThemeProvider>
    );
  }
  return render(ui, { wrapper: Wrapper, ...options });
}

// Factory functions for mock data
export function createMockQuota(overrides?: Partial<{
  used: number;
  max: number;
  remaining: number;
  reset_date: string;
}>) {
  return {
    used: 10,
    max: 100,
    remaining: 90,
    reset_date: '2026-05-01',
    ...overrides,
  };
}

export function createMockPipelineState(overrides?: Partial<{
  problem: string;
  preset: string;
  method: string;
  language: string;
}>) {
  return {
    problem: 'What is the capital of France?',
    preset: 'multi-perspective-budget',
    method: 'multi-perspective',
    language: 'English',
    ...overrides,
  };
}

export function createMockPhase(
  overrides?: Partial<{
    name: string;
    status: 'pending' | 'running' | 'completed' | 'error';
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    result: any;
  }>,
) {
  return {
    name: 'classification',
    status: 'completed' as const,
    result: { task_type: 'analytical' },
    ...overrides,
  };
}

export function createMockMessage(
  overrides?: Partial<{
    role: 'user' | 'assistant';
    content: string;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    phases: any[];
  }>,
) {
  return {
    role: 'user' as const,
    content: 'Hello',
    phases: [],
    ...overrides,
  };
}
