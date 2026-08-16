import { ReactNode, useId } from 'react';

interface TooltipProps {
  text: string;
  children: ReactNode;
  as?: 'span' | 'div';
}

/**
 * Hover/focus tooltip.
 *
 * The wrapper is focusable and the bubble is wired up with `aria-describedby`
 * rather than left as decorative text. Previously it revealed only on
 * `group-hover` around non-focusable children, so the full model id, the
 * subagent roster and the quality-score explanation were mouse-only — the
 * content was unreachable by keyboard and invisible to screen readers.
 */
export function Tooltip({ text, children, as: Component = 'span' }: TooltipProps) {
  const id = useId();

  return (
    <Component className="group relative inline-block">
      <span tabIndex={0} aria-describedby={id} className="rounded-[var(--radius-sm)] outline-none">
        {children}
      </span>
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-max max-w-[220px] -translate-x-1/2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[length:var(--text-2xs)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] opacity-0 shadow-[var(--shadow)] transition-opacity duration-[var(--dur-micro)] group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {text}
        <span className="absolute left-1/2 top-full -mt-0.5 h-2 w-2 -translate-x-1/2 rotate-45 border-b border-r border-[var(--border)] bg-[var(--surface)]" />
      </span>
    </Component>
  );
}
