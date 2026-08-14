/**
 * Emits a JSON-LD block into the server-rendered HTML.
 *
 * Structured data is how search engines and AI answer engines learn what a
 * page *is* rather than guessing from prose. It has to be present in the first
 * response, so this is a server component with no client runtime.
 */

interface JsonLdProps {
  /** A schema.org object, or an array of them. */
  data: Record<string, unknown> | Record<string, unknown>[];
}

export function JsonLd({ data }: JsonLdProps) {
  // JSON.stringify already escapes quotes; `<` is escaped so the payload can
  // never terminate the script element early.
  const json = JSON.stringify(data).replace(/</g, '\\u003c');
  return (
    <script
      type="application/ld+json"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: json }}
    />
  );
}
