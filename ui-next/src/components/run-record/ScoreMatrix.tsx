import { RUN, SCORE_AXES, type RunScore } from '@/lib/demo-record';

/**
 * The page's signature figure: the critique phase's actual score matrix.
 *
 * A real `<table>`, not a picture of one — it keeps its meaning with CSS off,
 * in a screen reader, and on paper. Four rival positions across the columns,
 * the four axes the critique agent scores down the rows, and the two positions
 * the run threw away shown in place rather than quietly omitted. Showing the
 * dissent it rejected is the least imitable thing this product does; hiding it
 * would leave the page indistinguishable from a feature grid.
 */

/** Columns run best-first — the order a reader of any results table expects. */
const COLUMNS: RunScore[] = [...RUN.scores].sort((a, b) => b.total - a.total);

const FLAGGED = COLUMNS.filter((c) => c.biasFlags.length > 0);

function cellClass(retained: boolean): string {
  return `nums-tabular border-b border-[var(--border)] px-[var(--space-4)] py-[var(--space-3)] text-right font-mono text-[length:var(--text-sm)] ${
    retained ? 'text-[var(--text)]' : 'text-[var(--text-subtle)]'
  }`;
}

export function ScoreMatrix() {
  return (
    <figure className="m-0">
      {/* Wide content scrolls inside its own box; the page body never does. */}
      <div className="-mx-[var(--gutter)] overflow-x-auto px-[var(--gutter)]">
        <table className="w-full min-w-[34rem] border-collapse text-left">
          <caption className="mb-[var(--space-4)] text-left font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
            Critique &amp; Pruning — independent scoring of all four positions, 0–10 per axis.
          </caption>

          <thead>
            <tr>
              <th
                scope="col"
                className="border-b border-[var(--border-strong)] py-[var(--space-3)] pr-[var(--space-4)] font-sans text-[length:var(--text-2xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]"
              >
                Axis
              </th>
              {COLUMNS.map((column) => (
                <th
                  key={column.position}
                  scope="col"
                  className={`border-b border-[var(--border-strong)] px-[var(--space-4)] py-[var(--space-3)] text-right font-sans text-[length:var(--text-xs)] font-semibold leading-[var(--lh-ui)] ${
                    column.retained ? 'text-[var(--text)]' : 'text-[var(--text-subtle)]'
                  }`}
                >
                  {column.position}
                  {column.biasFlags.length > 0 && (
                    <sup className="ml-[2px] font-mono text-[var(--warn)]">†</sup>
                  )}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {SCORE_AXES.map(({ key, label }) => (
              <tr key={key}>
                <th
                  scope="row"
                  className="border-b border-[var(--border)] py-[var(--space-3)] pr-[var(--space-4)] font-sans text-[length:var(--text-sm)] font-normal leading-[var(--lh-ui)] text-[var(--text-muted)]"
                >
                  {label}
                </th>
                {COLUMNS.map((column) => (
                  <td key={column.position} className={cellClass(column.retained)}>
                    {(column[key] as number).toFixed(1)}
                  </td>
                ))}
              </tr>
            ))}

            <tr>
              <th
                scope="row"
                className="border-b border-[var(--border-strong)] py-[var(--space-3)] pr-[var(--space-4)] font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]"
              >
                Total
              </th>
              {COLUMNS.map((column) => (
                <td
                  key={column.position}
                  className={`${cellClass(column.retained)} border-[var(--border-strong)] font-semibold`}
                >
                  {column.total.toFixed(1)}
                  {/* Bar width is the score. The figure above is exact; this
                      makes the gap between 8.5 and 0.0 legible at a glance. */}
                  <span
                    aria-hidden="true"
                    className="mt-[var(--space-1)] block h-[2px] w-full bg-[var(--border)]"
                  >
                    <span
                      className={`block h-full ${column.retained ? 'bg-[var(--accent)]' : 'bg-[var(--border-strong)]'}`}
                      style={{ width: `${column.total * 10}%` }}
                    />
                  </span>
                </td>
              ))}
            </tr>

            <tr>
              <th
                scope="row"
                className="py-[var(--space-3)] pr-[var(--space-4)] font-sans text-[length:var(--text-sm)] font-normal leading-[var(--lh-ui)] text-[var(--text-muted)]"
              >
                Outcome
              </th>
              {COLUMNS.map((column) => (
                <td
                  key={column.position}
                  className="px-[var(--space-4)] py-[var(--space-3)] text-right font-sans text-[length:var(--text-2xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]"
                >
                  <span className={column.retained ? 'text-[var(--ok)]' : 'text-[var(--text-subtle)]'}>
                    {column.retained ? 'Carried forward' : 'Pruned'}
                  </span>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <figcaption className="mt-[var(--space-6)] font-sans text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-subtle)]">
        {FLAGGED.map((column) => (
          <span key={column.position} className="mb-[var(--space-2)] block">
            <span className="font-mono text-[var(--warn)]">†</span> {column.position} —{' '}
            {column.biasFlags.join('; ')}
          </span>
        ))}
        <span className="block">
          Total is the critique agent&apos;s score after penalties, not the mean of the four axes
          above — a position can score respectably on every axis and still be pruned.
        </span>
      </figcaption>
    </figure>
  );
}
