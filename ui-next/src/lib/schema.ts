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
