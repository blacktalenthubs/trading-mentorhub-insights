/** Privacy Policy — required for App Store / TestFlight external testing.
 *  Public static page at /privacy. Plain, honest, covers what the app collects.
 */
import { Link } from "react-router-dom";

const UPDATED = "June 16, 2026";
const CONTACT = "vbolofinde@gmail.com";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-bold text-text-primary">{title}</h2>
      <div className="mt-2 space-y-2 text-sm leading-relaxed text-text-secondary">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <Link to="/" className="text-sm text-accent hover:underline">← BusyTradersDesk</Link>
        <h1 className="mt-6 text-3xl font-bold">Privacy Policy</h1>
        <p className="mt-2 text-sm text-text-faint">Last updated: {UPDATED}</p>

        <p className="mt-6 text-sm leading-relaxed text-text-secondary">
          BusyTradersDesk ("we", "us") provides trading-setup alerts and market research
          tools for educational and informational purposes. This policy explains what we
          collect, why, and your choices. We do not sell your personal information.
        </p>

        <Section title="Information we collect">
          <p><strong>Account information</strong> — your email address and password (stored hashed) when you register.</p>
          <p><strong>Preferences</strong> — your watchlists, alert-type settings, and Telegram chat ID if you link Telegram for notifications.</p>
          <p><strong>Usage data</strong> — pages visited, features used, and alerts viewed, to operate and improve the product.</p>
          <p><strong>Device &amp; log data</strong> — IP address, browser/app version, and basic diagnostics. The iOS app is a secure wrapper around our website and collects the same data as the website.</p>
          <p>We do <strong>not</strong> collect financial-account credentials, and we are not a broker — we never place trades or touch your money.</p>
        </Section>

        <Section title="How we use it">
          <p>To create and secure your account; deliver alerts and notifications you opt into; show your watchlists and reports; operate, maintain, and improve the service; and respond to support requests.</p>
        </Section>

        <Section title="Third parties we use">
          <p>We share the minimum necessary with service providers that run the product: cloud hosting and database, a market-data provider, Telegram (only if you link it, to deliver your alerts), and Apple (for the iOS app and TestFlight). We do not sell or rent your data to advertisers.</p>
        </Section>

        <Section title="Data retention">
          <p>We keep account data while your account is active. You can request deletion at any time (see Contact); we remove your personal data except where we must retain limited records for legal or security reasons.</p>
        </Section>

        <Section title="Security">
          <p>We use industry-standard measures — encrypted transport (HTTPS), hashed passwords, and access controls. No method is perfectly secure, but we work to protect your data.</p>
        </Section>

        <Section title="Your choices &amp; rights">
          <p>You can update your preferences in Settings, unlink Telegram, or request access to or deletion of your data by emailing us. Notifications are opt-in and can be turned off at any time.</p>
        </Section>

        <Section title="Children">
          <p>BusyTradersDesk is not directed to anyone under 18, and we do not knowingly collect data from children.</p>
        </Section>

        <Section title="Not financial advice">
          <p>All content and alerts are for educational and informational purposes only and are not financial, investment, or trading advice. You are solely responsible for your own decisions. Trading involves risk of loss.</p>
        </Section>

        <Section title="Changes to this policy">
          <p>We may update this policy; we'll revise the "Last updated" date above and, for material changes, notify you in the app.</p>
        </Section>

        <Section title="Contact">
          <p>Questions or data requests: <a href={`mailto:${CONTACT}`} className="text-accent hover:underline">{CONTACT}</a></p>
        </Section>
      </div>
    </div>
  );
}
