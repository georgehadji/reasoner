import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { MarkdownRenderer } from './MarkdownRenderer';

/**
 * Tier F1: the frontend trust boundary. This component is where model-authored
 * text becomes DOM, so every guard between the two has to be a fact rather than
 * an assumption.
 *
 * Three things make that worth pinning:
 *
 *   1. `ui-next` declares no sanitizer at all — no `dompurify`, no
 *      `rehype-sanitize`, no `sanitize-html`. The whole defence is whatever
 *      `react-markdown` does by default.
 *   2. The custom anchor at `MarkdownRenderer.tsx:63` passes `href` straight to
 *      the DOM with no scheme check of its own.
 *   3. `security-csp.ts:30-63` states `script-src` must permit `'unsafe-inline'`
 *      in every environment, and names "the markdown renderer's allowlist" as a
 *      compensating control. That makes this file the control it names.
 *
 * The existing `MarkdownRenderer.patterns.test.ts` reads this component's SOURCE
 * TEXT with `fs.readFileSync` and regexes it. That cannot see behaviour: it would
 * pass unchanged if `react-markdown` shipped a major version that dropped URL
 * sanitising, which is precisely the regression that matters here. These tests
 * render the real component and assert on the real DOM instead.
 */
describe('MarkdownRenderer — untrusted URL schemes', () => {
  const dangerous = [
    ['javascript', '[click](javascript:alert(1))'],
    ['mixed-case javascript', '[click](JaVaScRiPt:alert(1))'],
    ['javascript with an entity', '[click](java&#115;cript:alert(1))'],
    ['vbscript', '[click](vbscript:msgbox(1))'],
    ['data with html', '[click](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)'],
  ] as const;

  it.each(dangerous)('strips a %s: href', (_label, markdown) => {
    const { container } = render(<MarkdownRenderer>{markdown}</MarkdownRenderer>);

    const anchor = container.querySelector('a');
    expect(anchor, 'the link should still render, just not be executable').not.toBeNull();

    const href = anchor?.getAttribute('href') ?? '';
    expect(href.toLowerCase()).not.toMatch(/^\s*(javascript|vbscript|data):/);
  });

  it('leaves an ordinary https link intact', () => {
    const { container } = render(
      <MarkdownRenderer>{'[ok](https://example.com/a?b=c#d)'}</MarkdownRenderer>,
    );

    // The negative cases above pass trivially against a renderer that drops
    // every href. This is what separates sanitising from breaking links.
    expect(container.querySelector('a')?.getAttribute('href')).toBe(
      'https://example.com/a?b=c#d',
    );
  });

  it('keeps relative and anchor links usable', () => {
    const { container } = render(
      <MarkdownRenderer>{'[rel](/docs/x) and [frag](#section)'}</MarkdownRenderer>,
    );

    const hrefs = Array.from(container.querySelectorAll('a')).map((a) =>
      a.getAttribute('href'),
    );
    expect(hrefs).toEqual(['/docs/x', '#section']);
  });
});

describe('MarkdownRenderer — raw HTML in model output', () => {
  it('does not execute an inline event handler', () => {
    const { container } = render(
      <MarkdownRenderer>{'<img src=x onerror="alert(1)">'}</MarkdownRenderer>,
    );

    // No rehype-raw is in the plugin chain, so this must arrive as text.
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('onerror');
  });

  it('does not mount a script tag', () => {
    const { container } = render(
      <MarkdownRenderer>{'<script>window.__pwned = true;</script>'}</MarkdownRenderer>,
    );

    expect(container.querySelector('script')).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it('does not honour an injected iframe', () => {
    const { container } = render(
      <MarkdownRenderer>{'<iframe src="https://evil.example"></iframe>'}</MarkdownRenderer>,
    );

    expect(container.querySelector('iframe')).toBeNull();
  });
});

describe('MarkdownRenderer — link target hardening', () => {
  it('gives every external link noopener noreferrer', () => {
    const { container } = render(
      <MarkdownRenderer>{'[ok](https://example.com)'}</MarkdownRenderer>,
    );

    const anchor = container.querySelector('a');
    // target="_blank" without noopener hands the opener window to the
    // destination through window.opener.
    expect(anchor?.getAttribute('target')).toBe('_blank');
    expect(anchor?.getAttribute('rel')).toContain('noopener');
    expect(anchor?.getAttribute('rel')).toContain('noreferrer');
  });
});
