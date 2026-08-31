import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';

export default function CookiesPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-16 flex-1 w-full">
      <h1 className="text-[length:var(--text-4xl)] font-bold mb-8">Cookie Policy</h1>
      <div className="prose prose-invert max-w-none text-[var(--text-2)]">
        <p className="mb-4">Last updated: {new Date().toLocaleDateString()}</p>
        
        <h2 className="text-[length:var(--text-2xl)] font-semibold mt-8 mb-4 text-[var(--text)]">What Are Cookies</h2>
        <p className="mb-4">Cookies are small text files that are placed on your computer or mobile device when you visit our website. They are widely used to make websites work more efficiently and provide a better user experience.</p>
        
        <h2 className="text-[length:var(--text-2xl)] font-semibold mt-8 mb-4 text-[var(--text)]">How We Use Cookies</h2>
        <p className="mb-4">We use cookies and similar tracking technologies for the following purposes:</p>
        <ul className="list-disc pl-6 mb-4 space-y-2">
          <li><strong>Authentication:</strong> To keep you signed in securely (via Supabase).</li>
          <li><strong>Security:</strong> To protect against CSRF attacks.</li>
          <li><strong>Preferences:</strong> To remember your UI choices like Dark/Light mode and sidebar state.</li>
        </ul>
        
        <h2 className="text-[length:var(--text-2xl)] font-semibold mt-8 mb-4 text-[var(--text)]">Managing Cookies</h2>
        <p className="mb-4">Most web browsers allow you to control cookies through their settings. However, if you disable strictly necessary cookies, you will not be able to log in or use the core Reasoner application.</p>
      </div>
      </main>
      <SiteFooter />
    </div>
  );
}
