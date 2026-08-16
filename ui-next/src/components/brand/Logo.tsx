interface LogoProps {
  /** Show the wordmark text alongside the mark. */
  showWordmark?: boolean;
  /** Height of the mark in pixels. */
  size?: number;
  /** Override color — defaults to current text color. */
  color?: string;
  className?: string;
}

/**
 * Reasoner wordmark + geometric mark.
 *
 * The mark is a stylised letter "R" formed from a single closed path:
 * a vertical stem, a sharp diagonal bowl, and a leg — suggesting
 * structure, verified reasoning, and an architectural pipeline.
 */
export function Logo({
  showWordmark = true,
  size = 28,
  color = 'currentColor',
  className,
}: LogoProps) {
  const markWidth = size;
  const markHeight = size;

  return (
    <div className={`inline-flex items-center gap-2.5 ${className || ''}`}>
      <svg
        width={markWidth}
        height={markHeight}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        {/* Background shape — rounded square */}
        <rect
          x="1"
          y="1"
          width="30"
          height="30"
          rx="6"
          stroke={color}
          strokeWidth="2"
          fill="none"
        />
        {/* The "R" mark — stem + bowl + leg */}
        <path
          d="M10 8 h5.5 a4.5 4.5 0 0 1 0 9 h-2.5 l5.5 7"
          stroke={color}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        {/* Verification dot — the period of certainty */}
        <circle cx="23" cy="24" r="2" fill={color} />
      </svg>

      {showWordmark && (
        <span
          className="text-[17px] font-semibold tracking-[-0.02em]"
          style={{ color }}
        >
          Reasoner
        </span>
      )}
    </div>
  );
}

/** Icon-only version for favicons, app icons, etc. */
export function LogoMark({
  size = 32,
  color = 'currentColor',
  className,
  }: {
  size?: number;
  color?: string;
  className?: string;
  }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Reasoner"
    >
      <rect x="1" y="1" width="30" height="30" rx="6" fill={color} />
      <path
        d="M10 8 h5.5 a4.5 4.5 0 0 1 0 9 h-2.5 l5.5 7"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="23" cy="24" r="2" fill="currentColor" />
    </svg>
  );
}
