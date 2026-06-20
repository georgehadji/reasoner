# Reasoner Prompting Guide: Examples by Method

This document provides a comprehensive list of example prompts for each of the specialized reasoning methods available in the Reasoner pipeline.

---

## 1. Multi-Perspective
*Analyzes a topic from multiple, predefined angles (e.g., constructive, destructive, systemic).*

**Prompt 1 (Business Strategy):**
```
Analyze the strategic implications for a traditional publishing house of launching a direct-to-consumer subscription service for audiobooks and e-books, considering both opportunities and threats.
```

**Prompt 2 (Social Policy):**
```
Evaluate the potential societal impact of implementing a four-day work week in the tech industry in Greece, from the perspectives of employee well-being, company productivity, economic competitiveness, and urban planning.
```

---

## 2. Debate
*Creates a structured debate between two opposing views, with opening statements, rebuttals, and closing remarks.*

**Prompt 1 (Technology):**
```
Resolved: AI-powered code generation tools will ultimately devalue the role of human software developers. Generate a debate for and against this motion.
```

**Prompt 2 (Ethics):**
```
Stage a formal debate on the ethical proposition: 'Is it justifiable for governments to use AI-driven predictive policing algorithms to allocate law enforcement resources?'
```

---

## 3. Research
*Performs an in-depth web search, synthesizing information from academic and authoritative sources to answer a question.*

**Prompt 1 (History):**
```
Conduct a research report on the economic and cultural factors that led to the Cretan Renaissance in the 16th and 17th centuries, citing primary and secondary sources.
```

**Prompt 2 (Science):**
```
Investigate the current state of research into solid-state batteries for electric vehicles. What are the primary technical hurdles, who are the key players, and what is the projected timeline for commercial viability?
```

---

## 4. Brainstorming (Verbalized Sampling)
*Generates a diverse list of ideas, including less obvious "tail ideas," then clusters and develops the best ones.*

**Prompt 1 (Startup):**
```
Generate a list of innovative SaaS business ideas that leverage generative AI to solve niche problems for freelance graphic designers.
```

**Prompt 2 (Socio-Cultural):**
```
Brainstorm a series of high-impact, low-cost community initiatives to revitalize the historic commercial center of Athens, focusing on increasing foot traffic and local engagement.
```

---

## 5. Socratic
*Investigates a topic through a series of questions and answers, revealing deeper assumptions and logical connections.*

**Prompt 1 (Philosophy):**
```
Using the Socratic method, explore the statement: 'True creativity can only exist within constraints'.
```

**Prompt 2 (Personal Development):**
```
I want to improve my public speaking skills but I feel a lot of anxiety. Initiate a Socratic dialogue to help me understand the root cause of this fear and identify actionable steps.
```

---

## 6. Pre-Mortem
*Imagines a project has already failed and analyzes the likely reasons retroactively to proactively identify risks.*

**Prompt 1 (Project Management):**
```
We are planning to launch a new mobile banking app in six months. Conduct a pre-mortem analysis assuming the launch was a complete failure. What went wrong?
```

**Prompt 2 (Career):**
```
I am about to accept a job offer as a product manager at a fast-growing but chaotic startup. Imagine it's a year from now and I've resigned, completely burned out and disappointed. Perform a pre-mortem on why this career move failed.
```

---

## 7. Jury
*An advanced orchestral method that combines other methods. It generates perspectives, debates them, and uses a final "jury" to evaluate everything and deliver a reasoned verdict.*

**Prompt 1 (Investment Decision):**
```
A venture capital firm is considering a $5 million investment in a startup that uses AI for drug discovery. Orchestrate a jury analysis to determine whether they should proceed. Include expert perspectives on technology, market, and finance, a debate on the risks, and a final jury verdict.
```

**Prompt 2 (Policy Decision):**
```
The city of Thessaloniki must decide whether to invest in a new metro line or expand its electric bus network to combat traffic congestion. Use the Jury method to arrive at a final recommendation, weighing economic, environmental, and social factors.
```

---

## 8. Scientific
*Follows the classic scientific method: formulates hypotheses, proposes falsification tests, and interprets potential outcomes.*

**Prompt 1 (Marketing):**
```
Our e-commerce site has high traffic but low conversion rates. Apply the scientific method to identify and test potential reasons for this drop-off in the sales funnel.
```

**Prompt 2 (Product Optimization):**
```
Users are not engaging with our app's new 'social feed' feature. Formulate a set of hypotheses explaining this behavior and design experiments (A/B tests, user interviews) to validate them.
```

---

## 9. Dialectical
*Based on Thesis -> Antithesis -> Synthesis. It starts with a position, develops its opposition to find internal contradictions, and arrives at a higher-level synthesis (Aufhebung).*

**Prompt 1 (Organizational Change):**
```
Explore the tension between 'maintaining company culture' (Thesis) and 'rapidly scaling our remote workforce' (Antithesis). Use the dialectical method to arrive at a synthesized strategy for growth.
```

**Prompt 2 (Creative Process):**
```
Apply a dialectical analysis to the creative conflict between 'artistic integrity' and 'commercial viability' for a documentary filmmaker. What is the resulting synthesis?
```

---

## 10. Analogical
*Solves a problem by finding a structural analogy from a completely different domain and transferring the solution.*

**Prompt 1 (Problem Solving):**
```
The city's public transport system is inefficient and poorly coordinated. Use analogical reasoning, drawing from how data packets are routed on the internet, to propose a new model for urban mobility.
```

**Prompt 2 (Innovation):**
```
A hospital's emergency room is overwhelmed by chaotic patient intake. Find an analogy in a different industry (e.g., airline logistics, restaurant kitchens) to redesign the patient flow and triage process.
```

---

## 11. Coding
*Specialized method for code generation. It analyzes the problem, writes code, suggests tests, and provides documentation.*

**Prompt 1 (Backend Development):**
```
Write a Python FastAPI endpoint that accepts a user ID, connects to a PostgreSQL database, retrieves the user's profile, and returns it as JSON. Include error handling for a user not found.
```

**Prompt 2 (Frontend Development):**
```
Generate a React component using TypeScript and Tailwind CSS that displays a user profile card. The component should take a user object (with name, avatar URL, and bio) as a prop and be fully responsive.
```

---

## 12. CoVE (Chain-of-Verification)
*Breaks down an answer into distinct claims, generates questions to verify each, and then rewrites the final answer, correcting any inaccuracies.*

**Prompt 1 (Fact-Checking):**
```
Generate a brief history of the discovery of penicillin, and then apply the Chain-of-Verification method to fact-check the generated text for historical accuracy regarding dates, names, and key events.
```

**Prompt 2 (Content Correction):**
```
Here is a blog post about the health benefits of the Mediterranean diet. Use the CoVE method to verify its central claims and produce a revised, more accurate version.
```

---

## 13. ToT (Tree-of-Thoughts)
*Explores a problem as a tree of thought, where each branch is a different reasoning path. It evaluates paths and can backtrack from dead ends.*

**Prompt 1 (Complex Puzzle):**
```
Use the Tree-of-Thoughts method to solve this logic puzzle: There are three boxes, one with apples, one with oranges, and one with a mix of both. All boxes are mislabeled. You can only pick one fruit from one box to determine the correct labels for all three. How do you do it?
```

**Prompt 2 (Strategy):**
```
Develop a strategy for a chess endgame where you have a king and a rook against a king and a queen. Explore multiple lines of play using the Tree-of-Thoughts approach to find the optimal path to a draw or win.
```

---

## 14. SoT (Skeleton-of-Thought)
*First creates a structured outline (a "skeleton") of the answer and then expands each section in parallel for a more coherent result.*

**Prompt 1 (Article Writing):**
```
I need to write a comprehensive guide on 'Getting Started with Kubernetes for Beginners'. Use the Skeleton-of-Thought method to first create a detailed outline and then expand it into a full article.
```

**Prompt 2 (Business Plan):**
```
Draft a business plan for a new specialty coffee shop. Apply the SoT method to first structure the plan (Executive Summary, Market Analysis, Products, Marketing, Financials) and then flesh out each section.
```

---

## 15. PoT (Program-of-Thought)
*Translates a problem into code (e.g., Python), executes it, and interprets the result to provide a highly accurate answer, especially for quantitative problems.*

**Prompt 1 (Mathematics):**
```
A train leaves Athens at 3 PM traveling towards Thessaloniki at 120 km/h. Another train leaves Thessaloniki at 4 PM traveling towards Athens at 150 km/h. If the distance is 510 km, at what time will they meet? Solve this using the Program-of-Thought method.
```

**Prompt 2 (Data Analysis):**
```
Given the following list of monthly sales figures for a product [150, 175, 160, 190, 210, 200], use the PoT method to calculate the month-over-month percentage growth for each month.
```

---

## 16. Self-Discover
*Acts as an internal architect, selecting the best "reasoning modules" for a problem and composing them into a dynamic plan to find the solution.*

**Prompt 1 (Complex Question):**
```
What are the most significant long-term ethical, economic, and social implications of fully autonomous transportation? Use the Self-Discover method to structure your reasoning.
```

**Prompt 2 (Open-Ended Problem):**
```
How can a small, non-profit organization effectively use social media to double its volunteer base within a year? Let the Self-Discover method determine the best reasoning path to construct a strategy.
```

---

## 17. Delphi
*Simulates a panel of experts reaching a consensus. It generates independent estimates, provides an anonymous summary to all "experts," and allows them to revise their estimates until they converge.*

**Prompt 1 (Forecasting):**
```
Using the Delphi method, provide a consensus forecast on the global market share of electric vehicles by the year 2035, including quantitative estimates and rationales from multiple simulated experts.
```

**Prompt 2 (Risk Assessment):**
```
What are the top 5 most critical security risks for a fully remote company in the finance sector? Use the Delphi method to achieve a prioritized list based on a simulated panel of cybersecurity experts.
```

---

## 18. Bayesian
*Applies Bayesian reasoning. It starts with prior beliefs, updates them with new evidence, and arrives at stronger posterior beliefs. Ideal for problems with evolving information.*

**Prompt 1 (Diagnostic Problem):**
```
A user reports that our web application is 'slow'. Given the following pieces of evidence that arrive sequentially: [1] 'The user is on a mobile network', [2] 'The database CPU usage is at 90%', [3] 'A new marketing campaign just launched'. Use Bayesian reasoning to update the probability of the most likely root cause at each step.
```

**Prompt 2 (Scientific Inquiry):**
```
A new exoplanet is discovered. Initial data suggests it has a water-rich atmosphere (Hypothesis A) but is likely too close to its star for liquid water (Hypothesis B). As new telescopic data arrives showing unexpected atmospheric density, use the Bayesian method to update your belief in each hypothesis.
```
