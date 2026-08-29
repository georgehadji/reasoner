import * as React from 'react';
import { cn } from '@/lib/utils';
import { Spinner } from './Spinner';

/* ────────────────────────────────────────────────────────────────────────────
   Button Variant Styles
   -------------------------------------------------------------------------- */

const buttonVariants = {
  primary:
    'bg-[var(--accent)] text-[var(--accent-text)] ' +
    'hover:bg-[var(--accent-hover)] hover:-translate-y-px ' +
    'active:translate-y-0 active:shadow-none',

  secondary:
    'bg-[var(--surface-2)] text-[var(--text)] border border-[var(--border)] ' +
    'hover:bg-[var(--surface-3)] hover:border-[var(--border-strong)] ' +
    'active:bg-[var(--surface-hover)]',

  outline:
    'bg-transparent text-[var(--text-2)] border border-[var(--border)] ' +
    'hover:bg-[var(--surface)] hover:text-[var(--text)] hover:border-[var(--border-strong)] ' +
    'active:bg-[var(--surface-hover)]',

  ghost:
    'bg-transparent text-[var(--text-2)] ' +
    'hover:bg-[var(--surface-hover)] hover:text-[var(--text)] ' +
    'active:bg-[var(--surface)]',

  link:
    'bg-transparent text-[var(--text-muted)] underline-offset-4 hover:underline hover:text-[var(--text)] ' +
    'active:text-[var(--text-subtle)]',

  danger:
    'bg-[var(--red-bg)] text-[var(--red)] border border-[var(--red-border)] ' +
    'hover:bg-[var(--red-border)] hover:text-[var(--text)] ' +
    'active:opacity-80',
} as const;

const buttonSizes = {
  sm: 'h-8 px-2.5 gap-1 text-xs',
  md: 'h-10 px-4 gap-1.5 text-sm',
  lg: 'h-12 px-6 gap-2 text-base',
} as const;

/* ────────────────────────────────────────────────────────────────────────────
   Types
   -------------------------------------------------------------------------- */

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof buttonVariants;
  size?: keyof typeof buttonSizes;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

/* ────────────────────────────────────────────────────────────────────────────
   Component
   -------------------------------------------------------------------------- */

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      variant = 'primary',
      size = 'md',
      loading = false,
      leftIcon,
      rightIcon,
      disabled,
      className,
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={cn(
          // Layout
          'inline-flex items-center justify-center whitespace-nowrap',
          // Shape
          'rounded-xl',
          // Typography
          'font-medium',
          // Transition
          'transition-all duration-200 ease-out',
          'active:scale-[0.97] active:duration-100',
          // Focus is not styled here. globals.css already gives every button an
          // accent outline with a transparent 2px offset, which reads correctly
          // on --bg, --surface and --surface-2 alike, and thickens to 3px under
          // prefers-contrast: more. The ring this used to draw hardcoded a --bg
          // offset — a page-coloured gap painted over every card — and its
          // outline-none opted out of the contrast bump entirely.
          // Disabled / Loading
          isDisabled && 'cursor-not-allowed opacity-60',
          // Size
          buttonSizes[size],
          // Variant
          buttonVariants[variant],
          className
        )}
        {...props}
      >
        {loading && (
          <Spinner
            className={cn(
              size === 'sm' && 'h-3.5 w-3.5',
              size === 'md' && 'h-4 w-4',
              size === 'lg' && 'h-5 w-5'
            )}
          />
        )}
        {!loading && leftIcon}
        {children}
        {!loading && rightIcon}
      </button>
    );
  }
);

Button.displayName = 'Button';
