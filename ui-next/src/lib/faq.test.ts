import { describe, expect, it } from 'vitest';
import { FAQS, faqAnchor } from './faq';

describe('faqAnchor', () => {
  it('turns a question into a lowercase, hyphenated id', () => {
    expect(faqAnchor('Can I use Reasoner from my own code?')).toBe('can-i-use-reasoner-from-my-own-code');
  });

  it('gives every question on /faq its own anchor', () => {
    const anchors = FAQS.map(({ q }) => faqAnchor(q));
    expect(new Set(anchors).size).toBe(anchors.length);
  });
});
