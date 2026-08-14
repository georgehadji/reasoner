/**
 * FAQ content.
 *
 * Shared by the FAQ page and its FAQPage structured data, so the answer a
 * crawler is given is always byte-identical to the answer a person reads.
 */

export interface FaqEntry {
  q: string;
  a: string;
}

export const FAQS: readonly FaqEntry[] = [
  {
    q: 'What is Reasoner?',
    a: 'Reasoner is a multi-method AI reasoning engine. It classifies your question, decomposes it into sub-problems, answers them in parallel using models from different labs, independently critiques and scores the candidates, stress-tests the survivors, and synthesises a final answer in which every claim is labelled VERIFIED, HYPOTHESIS, or UNKNOWN.',
  },
  {
    q: 'How is Reasoner different from a chatbot?',
    a: 'A chatbot produces one model’s first response. Reasoner runs a structured pipeline in which generation, critique, and stress-testing are performed by different models from different labs, so mistakes have to survive review by a model that does not share the failure modes of the one that made them.',
  },
  {
    q: 'How does billing work?',
    a: 'Usage is metered in credits, where 1,000 credits equal $1.00 of underlying model spend. Each plan grants a monthly allowance — 500 credits on Free, 25,000 on Pro, 250,000 on Enterprise. You are charged after a run completes, based on what the models actually cost, so a failed run or a cache hit costs nothing.',
  },
  {
    q: 'What happens when I run out of credits?',
    a: 'The next run returns HTTP 402 and the app prompts you to top up. Because runs settle after they complete, the run that exhausted your balance still finished and was charged. Your balance refills automatically at the start of the next billing period.',
  },
  {
    q: 'Can I use Reasoner from my own code?',
    a: 'Yes. Create an API key in Settings, then send it as a bearer token to the REST API. POST /api/run streams results as Server-Sent Events, and the terminal event reports the exact token counts and cost of the run. Keys are scoped and can be given an expiry, and are revocable at any time.',
  },
  {
    q: 'Which AI models does Reasoner use?',
    a: 'Reasoner routes across 28 directly registered models and more than 350 through OpenRouter, including models from Anthropic, OpenAI, Google, DeepSeek, Mistral, xAI, Qwen, Moonshot, Zhipu, MiniMax, and Perplexity, plus locally hosted Ollama models. Routing is by role and preset rather than by a fixed favourite.',
  },
  {
    q: 'Why does Reasoner use models from different companies?',
    a: 'Models trained on overlapping data with overlapping methods share blind spots. Asking one model family five times returns one opinion repeated five times, and the apparent agreement reads as confidence. Reasoner requires at least three labs during generation — four on Premium presets — and forces the critiquing model to come from a different ecosystem than the generators.',
  },
  {
    q: 'What is Neuro Memory?',
    a: 'Neuro Memory is the tiered long-term memory layer. It stores prior conversations across in-memory, on-disk, and embedding-searchable tiers, and surfaces relevant fragments in later runs without spending the whole context window. It is isolated per account and can be cleared at any time.',
  },
  {
    q: 'Is my data used for training?',
    a: 'No. Your queries and results are not used to train models. You control retention in Settings — keep forever, 30 days, 7 days, or 24 hours — and zero-retention mode stores nothing at all. Data is encrypted with AES-256-GCM at rest and TLS 1.3 in transit.',
  },
  {
    q: 'Can I cancel my subscription?',
    a: 'Yes, at any time from the billing portal in your Dashboard. Premium access and your credit allowance remain active until the end of the current billing period.',
  },
] as const;
