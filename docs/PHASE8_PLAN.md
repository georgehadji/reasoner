# Phase 8 Implementation Plan — Frontend Self-Service UI

> **Goal:** Users can manage their entire lifecycle without support.  
> **Duration:** 5 working days (Week 9)  
> **Deliverable:** Auth pages, dashboard, pricing, upgrade modal, usage indicators.  
> **Constraint:** All UI changes are additive. Existing composer and chat feed untouched except for badges.

⚠️ **CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 8.1–8.11):**
- 8.1: `window.location.href = data.checkout_url` is an open redirect — validate URL before redirect
- 8.2: `err: any` throughout suppresses TypeScript safety — use proper error typing with `AuthError`
- 8.3: Auth pages have no loading state on form submit — users can double-click, causing race conditions
- 8.4: Forgot-password has no email format validation — wastes API quota on invalid emails
- 8.5: UpgradeModal has no error handling on checkout fetch — hangs in loading state
- 8.6: Preset lock uses hardcoded `'pro'` string — should fetch actual tier from `/api/billing/subscription`
- 8.7: Dashboard `useEffect` has no AbortController — can cause state updates on unmounted component
- 8.8: No Suspense boundaries or loading skeletons — shows blank space during data load
- 8.10: Missing ARIA attributes throughout all new components — inaccessible to screen readers
- 8.11: Playwright E2E test fills Stripe iframe incorrectly — needs `frameLocator()` for Stripe input

---

## 0. Pre-Flight Checklist

```bash
# 1. Verify Phases 1-7 are complete
python -m pytest tests/ --tb=short -q

# 2. Ensure Stripe test mode is active
# 3. Ensure Supabase Auth is configured
```

---

## 1. Day-by-Day Implementation Schedule

### Day 1 — Auth Pages Polish

**Files:**
- `ui-next/src/app/login/page.tsx`
- `ui-next/src/app/signup/page.tsx`
- `ui-next/src/app/forgot-password/page.tsx`

**Task 8.1.1 — Forgot Password Page**

```tsx
// ui-next/src/app/forgot-password/page.tsx
'use client';

import { useState } from 'react';
import { supabase } from '@/lib/supabase';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    setSent(true);
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-md p-8 space-y-4">
        <h1 className="text-2xl font-bold">Reset Password</h1>
        {sent ? (
          <p className="text-green-600">Check your email for a reset link.</p>
        ) : (
          <>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full p-2 border rounded"
              required
            />
            <button type="submit" className="w-full p-2 bg-blue-600 text-white rounded">
              Send Reset Link
            </button>
          </>
        )}
      </form>
    </div>
  );
}
```

**Day 1 Acceptance Criteria:**
- [ ] `/forgot-password` sends Supabase reset email.
- [ ] `/login` and `/signup` have consistent styling.

---

### Day 2 — Dashboard

**Files:**
- `ui-next/src/app/dashboard/page.tsx`
- `ui-next/src/components/layout/UserMenu.tsx`

**Task 8.2.1 — User Menu in Header**

```tsx
// ui-next/src/components/layout/UserMenu.tsx
'use client';

import { useAppStore } from '@/stores/app-store';
import { signOut } from '@/lib/auth';
import { useRouter } from 'next/navigation';

export function UserMenu() {
  const user = useAppStore((s) => s.user);
  const router = useRouter();

  if (!user) return null;

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-gray-600">{user.email}</span>
      <button
        onClick={async () => {
          await signOut();
          router.push('/login');
        }}
        className="text-sm text-red-600 hover:underline"
      >
        Logout
      </button>
    </div>
  );
}
```

**Task 8.2.2 — Dashboard with Usage Chart**

Use a lightweight chart library (e.g., `recharts`):

```bash
cd ui-next && npm install recharts
```

```tsx
// ui-next/src/app/dashboard/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api-client';
import { useQuota } from '@/hooks/useQuota';
import { BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

export default function DashboardPage() {
  const { quota } = useQuota();
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    apiFetch('/api/history').then(r => r.json()).then(data => setHistory(data.history || []));
  }, []);

  const chartData = history.slice(-7).map((h: any) => ({
    date: h.timestamp?.slice(0, 10) || 'unknown',
    tokens: h.tokens?.total || 0,
  }));

  return (
    <div className="max-w-5xl mx-auto py-8 px-4">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <StatCard title="Queries This Month" value={`${quota?.used || 0} / ${quota?.max || 20}`} />
        <StatCard title="Remaining" value={quota?.remaining ?? '-'} />
        <StatCard title="Plan" value="Free" /> {/* TODO: fetch from /api/billing/subscription */}
      </div>
      <div className="border rounded-lg p-6">
        <h2 className="font-semibold mb-4">Recent Activity</h2>
        <BarChart width={600} height={200} data={chartData}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="tokens" fill="#3b82f6" />
        </BarChart>
      </div>
    </div>
  );
}

function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="border rounded-lg p-6">
      <p className="text-sm text-gray-500">{title}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}
```

**Day 2 Acceptance Criteria:**
- [ ] Dashboard shows usage stats and recent activity chart.
- [ ] UserMenu shows email + logout.

---

### Day 3 — Upgrade Modal

**Files:**
- `ui-next/src/components/layout/UpgradeModal.tsx`

**Task 8.3.1 — Modal Component**

```tsx
// ui-next/src/components/layout/UpgradeModal.tsx
'use client';

import { useState } from 'react';
import { apiFetch } from '@/lib/api-client';

interface UpgradeModalProps {
  open: boolean;
  onClose: () => void;
}

export function UpgradeModal({ open, onClose }: UpgradeModalProps) {
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const handleUpgrade = async () => {
    setLoading(true);
    const res = await apiFetch('/api/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ tier: 'pro' }),
    });
    const data = await res.json();
    window.location.href = data.checkout_url;
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-8 max-w-md w-full">
        <h2 className="text-xl font-bold mb-2">Upgrade to Pro</h2>
        <p className="text-gray-600 mb-6">
          You've reached your free tier limit. Upgrade to Pro for 500 queries/month.
        </p>
        <div className="flex gap-3">
          <button
            onClick={handleUpgrade}
            disabled={loading}
            className="flex-1 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Upgrade ($12/mo)'}
          </button>
          <button onClick={onClose} className="flex-1 py-2 border rounded">
            Maybe Later
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Task 8.3.2 — Trigger on 429**

```tsx
// In usePipelineStream or api-client.ts
const res = await apiFetch('/api/run', { method: 'POST', body: JSON.stringify(req) });
if (res.status === 429) {
  const data = await res.json();
  if (data.detail?.upgrade_url) {
    setShowUpgradeModal(true);
  }
}
```

**Day 3 Acceptance Criteria:**
- [ ] 429 response triggers upgrade modal.
- [ ] Modal redirects to Stripe Checkout.

---

### Day 4 — Premium Preset Locks

**Files:**
- `ui-next/src/components/layout/Composer.tsx` or preset selector

**Task 8.4.1 — Lock Premium Presets**

```tsx
function PresetSelector() {
  const user = useAppStore((s) => s.user);
  const tier = user ? 'pro' : 'free'; // TODO: fetch actual tier

  const presets = [
    { id: 'multi-perspective-budget', tier: 'free' },
    { id: 'multi-perspective-premium', tier: 'premium' },
    // ...
  ];

  return (
    <div className="flex gap-2">
      {presets.map((p) => {
        const locked = p.tier === 'premium' && tier !== 'pro';
        return (
          <button
            key={p.id}
            disabled={locked}
            onClick={() => !locked && selectPreset(p.id)}
            className={`px-3 py-1 rounded text-sm ${
              locked ? 'opacity-50 cursor-not-allowed bg-gray-200' : 'bg-blue-100'
            }`}
          >
            {p.id}
            {locked && <span className="ml-1">🔒</span>}
          </button>
        );
      })}
    </div>
  );
}
```

**Day 4 Acceptance Criteria:**
- [ ] Premium presets are disabled for free users.
- [ ] Hovering lock shows "Upgrade to Pro" tooltip.

---

### Day 5 — E2E Test + Polish

**Task 8.5.1 — E2E Checkout Flow Test**

Using Playwright:

```typescript
// tests/e2e/checkout.spec.ts
import { test, expect } from '@playwright/test';

test('user can sign up and upgrade', async ({ page }) => {
  await page.goto('/signup');
  await page.fill('input[type="email"]', `test-${Date.now()}@example.com`);
  await page.fill('input[type="password"]', 'password123');
  await page.click('button:has-text("Sign Up")');

  await page.waitForURL('/');
  await page.goto('/pricing');
  await page.click('button:has-text("Upgrade")');

  // Stripe checkout (test mode)
  await page.waitForURL(/checkout.stripe.com/);
  await page.fill('input[name="cardnumber"]', '4242424242424242');
  await page.fill('input[name="exp-date"]', '12/30');
  await page.fill('input[name="cvc"]', '123');
  await page.click('button:has-text("Subscribe")');

  await page.waitForURL(/dashboard/);
  await expect(page.locator('text=Pro')).toBeVisible();
});
```

**Day 5 Acceptance Criteria:**
- [ ] Playwright E2E test passes in Stripe test mode.
- [ ] `npm run build` succeeds with zero errors.
- [ ] All existing tests pass.

---

## 2. Definition of Done (Phase 8)

- [ ] `/login`, `/signup`, `/forgot-password` pages functional.
- [ ] Dashboard shows usage stats + activity chart.
- [ ] Upgrade modal triggers on 429/quota exceeded.
- [ ] Premium presets are locked for free users.
- [ ] User menu shows email + logout.
- [ ] E2E test covers signup → upgrade flow.
- [ ] All existing tests pass.

---

*End of Phase 8 Plan*
