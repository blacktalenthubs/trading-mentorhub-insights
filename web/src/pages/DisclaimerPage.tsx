import { Link } from "react-router-dom";

export default function DisclaimerPage() {
  return (
    <div className="min-h-screen bg-surface-0 text-text-primary px-6 py-16">
      <div className="max-w-3xl mx-auto">
        <Link to="/" className="text-sm text-text-muted hover:text-text-primary mb-8 inline-block">
          ← Back to home
        </Link>
        <h1 className="font-display text-4xl font-bold mb-2">Disclaimer</h1>
        <p className="text-sm text-text-muted mb-8">Last updated: 2026-05-12</p>

        <div className="prose prose-invert max-w-none space-y-6 text-text-secondary">
          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">Educational content. Not investment advice.</h2>
            <p>
              tradingwithai.ai is an educational platform that teaches trading methodology
              and surfaces real-time pattern detections using publicly available technical
              analysis frameworks. The content published here — including lessons, alerts,
              strategy explanations, system statistics, and historical examples — is for
              <strong> educational and informational purposes only</strong>. It is not, and
              should not be construed as, investment advice, a recommendation to buy or sell
              any security, or a solicitation of any offer.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">No guarantee of outcomes</h2>
            <p>
              The platform detects patterns and structural levels using rule-based indicators
              and an AI triage layer that adds contextual metadata (sector confluence, volume,
              order-flow proxy). <strong>Pattern detection is descriptive, not predictive.</strong>
              The fact that a pattern was detected, that the system tagged an alert as "HIGH
              conviction", or that historical examples are shown in lessons,
              <strong> does not guarantee that any future trade based on similar patterns will
              be profitable, or even break even</strong>. Past pattern detection does not
              guarantee future outcomes.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">You are responsible for your own decisions</h2>
            <p>
              Trading securities, cryptocurrencies, options, and other financial instruments
              involves substantial risk of loss and is not suitable for every investor. The
              valuation of those instruments may fluctuate, and you may lose more than your
              initial investment. Before deciding to trade based on anything you see on this
              platform, you should carefully consider your investment objectives, level of
              experience, and risk appetite. You should seek independent advice from a
              licensed financial advisor if you have any doubts.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">No client / advisory relationship</h2>
            <p>
              Using this platform does not create a fiduciary, advisory, broker-dealer, or
              investment-adviser relationship between you and tradingwithai.ai or its
              operators. We do not know your individual financial situation, risk tolerance,
              tax bracket, or investment goals, and the platform's content is not
              personalized to any individual subscriber.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">No live trade execution</h2>
            <p>
              The platform does not execute trades on your behalf. All trades you choose to
              make based on platform content are entirely at your own discretion and
              responsibility, executed through your own brokerage account.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">Historical examples</h2>
            <p>
              Where the platform displays historical alerts, screenshots, or annotated charts,
              those are
              <strong> real archived detections shown for educational illustration</strong>.
              They are not simulated or backtested results, but they also do not represent
              the realized outcome of a trade — only what the system detected and the
              structural data attached to that detection. Hypothetical or simulated
              performance has inherent limitations and may not reflect actual trading conditions.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">Forward-looking statements</h2>
            <p>
              Any opinions, projections, or strategy descriptions on this platform may not
              prove to be accurate. Forward-looking statements involve known and unknown risks
              and uncertainties.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">Cryptocurrency-specific notice</h2>
            <p>
              Cryptocurrency markets are highly volatile, operate 24/7, and are subject to
              regulatory uncertainty in many jurisdictions. The same disclaimers above apply
              with even greater emphasis to crypto-related content on this platform.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">Liability</h2>
            <p>
              To the maximum extent permitted by law, tradingwithai.ai and its operators
              disclaim all liability for any loss or damage of any kind arising from your use
              of this platform, including but not limited to direct, indirect, consequential,
              or incidental damages.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-text-primary mb-3">Contact</h2>
            <p>
              Questions about this disclaimer or the platform's positioning can be sent to
              the platform operator via the support channel inside your account.
            </p>
          </section>
        </div>

        <div className="mt-16 text-center">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-text-primary"
          >
            ← Back to home
          </Link>
        </div>
      </div>
    </div>
  );
}
