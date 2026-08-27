/**
 * schema.org builders for the site's structured data.
 *
 * Kept in one module so every page describes the same organisation and product
 * — inconsistent entity data across pages is worse than none, because crawlers
 * cannot tell which description is authoritative.
 */

import { SITE, absoluteUrl } from './site';

export function organizationSchema(): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    '@id': absoluteUrl('/#organization'),
    name: SITE.name,
    legalName: SITE.legalName,
    url: SITE.url,
    logo: absoluteUrl('/logo.svg'),
    description: SITE.description,
    sameAs: [] as string[],
  };
}

export function websiteSchema(): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': absoluteUrl('/#website'),
    name: SITE.name,
    url: SITE.url,
    description: SITE.description,
    inLanguage: 'en',
    publisher: { '@id': absoluteUrl('/#organization') },
  };
}

export function softwareApplicationSchema(): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    '@id': absoluteUrl('/#software'),
    name: SITE.name,
    applicationCategory: 'BusinessApplication',
    applicationSubCategory: 'AI reasoning engine',
    operatingSystem: 'Web',
    url: SITE.url,
    description: SITE.description,
    featureList: [
      '19 reasoning methods including debate, jury, Bayesian, and chain-of-verification',
      'Cross-lab model routing across 350+ models',
      'Independent critique and adversarial stress testing of every candidate answer',
      'VERIFIED / HYPOTHESIS / UNKNOWN epistemic labelling',
      'Web-grounded research with citations',
      'Streaming REST API with scoped API keys',
    ],
    offers: [
      {
        '@type': 'Offer',
        name: 'Free',
        price: '0',
        priceCurrency: 'USD',
        description: '500 credits per month',
      },
      {
        '@type': 'Offer',
        name: 'Pro',
        priceCurrency: 'USD',
        description: '25,000 credits per month, premium presets, priority routing',
      },
    ],
    publisher: { '@id': absoluteUrl('/#organization') },
  };
}

export function breadcrumbSchema(
  trail: Array<{ name: string; path: string }>,
): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((crumb, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: crumb.name,
      item: absoluteUrl(crumb.path),
    })),
  };
}

export function faqSchema(
  entries: ReadonlyArray<{ q: string; a: string }>,
): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: entries.map(({ q, a }) => ({
      '@type': 'Question',
      name: q,
      acceptedAnswer: { '@type': 'Answer', text: a },
    })),
  };
}

export function techArticleSchema(doc: {
  title: string;
  description: string;
  slug: string;
  keywords: string[];
  minutes: number;
}): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: doc.title,
    description: doc.description,
    url: absoluteUrl(`/docs/${doc.slug}`),
    mainEntityOfPage: { '@type': 'WebPage', '@id': absoluteUrl(`/docs/${doc.slug}`) },
    keywords: doc.keywords.join(', '),
    timeRequired: `PT${doc.minutes}M`,
    inLanguage: 'en',
    isPartOf: { '@id': absoluteUrl('/#website') },
    author: { '@id': absoluteUrl('/#organization') },
    publisher: { '@id': absoluteUrl('/#organization') },
  };
}

/**
 * The programmatic surface, as an entity in its own right.
 *
 * Answer engines asked "how do I call Reasoner from an agent?" need something
 * to cite that is not a paragraph of marketing prose. A WebAPI node with its
 * documentation, its terms, and its entry points named is the machine-readable
 * form of that answer, and it is what makes /developers extractable rather
 * than merely indexable.
 */
export function webApiSchema(): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebAPI',
    '@id': absoluteUrl('/#api'),
    name: `${SITE.name} API`,
    description:
      'Run multi-model reasoning pipelines from software: an MCP server, a synchronous and a streaming HTTP endpoint, and a command-line entry point. Every claim in a result is labelled VERIFIED, HYPOTHESIS, or UNKNOWN.',
    url: absoluteUrl('/developers'),
    documentation: absoluteUrl('/docs/api-reference'),
    termsOfService: absoluteUrl('/terms'),
    provider: { '@id': absoluteUrl('/#organization') },
    isPartOf: { '@id': absoluteUrl('/#software') },
    potentialAction: [
      {
        '@type': 'ConsumeAction',
        name: 'Call the Model Context Protocol server',
        target: {
          '@type': 'EntryPoint',
          urlTemplate: absoluteUrl('/docs/mcp'),
          actionPlatform: 'https://modelcontextprotocol.io',
        },
      },
      {
        '@type': 'ConsumeAction',
        name: 'Run a pipeline over HTTP',
        target: {
          '@type': 'EntryPoint',
          urlTemplate: `${SITE.url}/api/agent/run/sync`,
          httpMethod: 'POST',
          contentType: 'application/json',
        },
      },
      {
        '@type': 'ConsumeAction',
        name: 'Fetch the live tool definitions',
        target: {
          '@type': 'EntryPoint',
          urlTemplate: `${SITE.url}/api/agent/tools`,
          httpMethod: 'GET',
          contentType: 'application/json',
        },
      },
    ],
  };
}

/**
 * A procedure, in the form answer engines quote back as steps.
 *
 * Used for the MCP setup on /developers: a reader who arrives from a generated
 * answer should get the three real steps, not a summary of a page that has
 * them.
 */
export function howToSchema(howTo: {
  name: string;
  description: string;
  url: string;
  steps: ReadonlyArray<{ name: string; text: string }>;
}): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'HowTo',
    name: howTo.name,
    description: howTo.description,
    url: absoluteUrl(howTo.url),
    inLanguage: 'en',
    publisher: { '@id': absoluteUrl('/#organization') },
    step: howTo.steps.map((step, index) => ({
      '@type': 'HowToStep',
      position: index + 1,
      name: step.name,
      text: step.text,
      url: `${absoluteUrl(howTo.url)}#mcp`,
    })),
  };
}
