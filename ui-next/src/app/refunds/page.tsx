import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';

// The pricing page advertises a 14-day money-back guarantee. Advertising a
// guarantee with no policy behind it is a consumer-law exposure, so the terms
// of that guarantee live here and the pricing page links to them.
export default function RefundsPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-16 flex-1 w-full">
        <h1 className="text-4xl font-bold mb-8">Refund Policy</h1>
        <div className="prose prose-invert max-w-none text-[var(--text-2)]">
          <h2 className="text-2xl font-semibold mt-8 mb-4 text-[var(--text)]">
            14-day money-back guarantee
          </h2>
          <p className="mb-4">
            If you are not satisfied with a paid Reasoner plan, you can request a full refund
            within 14 days of the charge you want refunded. This applies to your first payment on
            a plan and to any subsequent renewal, and you do not need to give a reason.
          </p>

          <h2 className="text-2xl font-semibold mt-8 mb-4 text-[var(--text)]">
            How to request a refund
          </h2>
          <p className="mb-4">
            Use the <a href="/contact" className="text-[var(--accent)] hover:underline">contact form</a>{' '}
            and choose &quot;Billing Issue&quot;. Include the email address on the account. We aim to
            respond within 3 business days.
          </p>
          <p className="mb-4">
            Approved refunds are returned to the original payment method. Card refunds are issued
            immediately on our side; how quickly they appear on your statement depends on your bank
            or card issuer, and typically takes 5–10 business days. PayPal refunds usually appear
            sooner.
          </p>

          <h2 className="text-2xl font-semibold mt-8 mb-4 text-[var(--text)]">
            After the 14 days
          </h2>
          <p className="mb-4">
            Outside the 14-day window, payments already made are non-refundable. You can cancel at
            any time from your account settings; cancellation stops future renewals and your plan
            stays active until the end of the period you have already paid for. We do not
            pro-rate partial periods.
          </p>

          <h2 className="text-2xl font-semibold mt-8 mb-4 text-[var(--text)]">Exceptions</h2>
          <p className="mb-4">
            We may decline a refund where an account has been used in breach of the{' '}
            <a href="/terms" className="text-[var(--accent)] hover:underline">Terms of Service</a>, or
            where refunds have been repeatedly requested and re-purchased on the same account. If we
            decline, we will tell you why.
          </p>

          <h2 className="text-2xl font-semibold mt-8 mb-4 text-[var(--text)]">Your statutory rights</h2>
          <p className="mb-4">
            This policy is offered in addition to any rights you have under the consumer protection
            law that applies where you live, including the EU/UK right of withdrawal. Nothing here
            limits those rights.
          </p>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
