import Link from "next/link";

// Faithful port of the previous workzap.ai page (snapshot taken 2026-10-03).
// Text and layout are unchanged. Only the contact links differ: every contact
// touch point now goes to pi (owner decision, 2026-10-03).
export function RetailPage() {
  return (
    <div
      style={{
        background: "var(--bg-app)",
        color: "var(--text-primary)",
        minHeight: "100vh",
      }}
    >
      <header
        style={{
          position: "sticky",
          top: "0",
          zIndex: "50",
          backdropFilter: "blur(10px)",
          background: "color-mix(in srgb, var(--bg-app) 82%, transparent)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <nav
          style={{
            maxWidth: "1080px",
            margin: "0 auto",
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            height: "62px",
          }}
        >
          <Link
            href="/"
            aria-label="WorkZap home"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              textDecoration: "none",
              color: "inherit",
            }}
          >
            <div className="wz-logo">W</div>
            <div
              style={{
                fontWeight: "800",
                fontSize: "16px",
                letterSpacing: "-0.3px",
              }}
            >
              WorkZap
            </div>
          </Link>
          <div style={{ display: "flex", alignItems: "center", gap: "22px" }}>
            <span
              className="wz-landing-links"
              style={{ display: "flex", alignItems: "center", gap: "22px" }}
            >
              <a
                href="#modules"
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-secondary)",
                  textDecoration: "none",
                }}
                className="wz-navlink"
              >
                Modules
              </a>
              <a
                href="#how"
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-secondary)",
                  textDecoration: "none",
                }}
                className="wz-navlink"
              >
                How it works
              </a>
              <a
                href="#pricing"
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-secondary)",
                  textDecoration: "none",
                }}
                className="wz-navlink"
              >
                Pricing
              </a>
              <a
                href="https://app.workzap.ai"
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-secondary)",
                  textDecoration: "none",
                }}
                className="wz-navlink"
              >
                Sign in
              </a>
            </span>
            <a
              href="https://app.workzap.ai"
              className="wz-btn wz-btn-primary"
              style={{ padding: "8px 15px", whiteSpace: "nowrap" }}
            >
              Get started
            </a>
          </div>
        </nav>
      </header>
      <section
        style={{
          maxWidth: "1080px",
          margin: "0 auto",
          padding: "0 24px",
          paddingTop: "72px",
          paddingBottom: "40px",
          textAlign: "center",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "12.5px",
            fontWeight: "700",
            letterSpacing: "0.5px",
            textTransform: "uppercase",
            color: "var(--accent-strong)",
            background: "var(--accent-soft)",
            border: "1px solid var(--border-accent)",
            padding: "6px 12px",
            borderRadius: "999px",
          }}
        >
          ✦ The AI Operating System for Retail
        </span>
        <h1
          style={{
            fontSize: "clamp(34px, 5.5vw, 56px)",
            fontWeight: "850",
            letterSpacing: "-1.5px",
            lineHeight: "1.05",
            margin: "22px auto 0",
            maxWidth: "820px",
          }}
        >
          Every outlet. Every number.
          <br />
          One AI that tells you{" "}
          <span style={{ color: "var(--accent)" }}>what to do next.</span>
        </h1>
        <p
          style={{
            fontSize: "clamp(15px, 2vw, 18px)",
            color: "var(--text-secondary)",
            lineHeight: "1.6",
            margin: "22px auto 0",
            maxWidth: "620px",
          }}
        >
          WorkZap plugs into your POS and sales data and works like an AI
          management team — surfacing what happened, why, what matters, and the
          exact action to take. Not another dashboard. A decision engine for
          your whole business.
        </p>
        <div
          style={{
            display: "flex",
            gap: "12px",
            justifyContent: "center",
            marginTop: "30px",
            flexWrap: "wrap",
          }}
        >
          <a
            href="https://app.workzap.ai"
            className="wz-btn wz-btn-primary"
            style={{ padding: "12px 22px", fontSize: "15px" }}
          >
            See it on your data →
          </a>
          <Link
            href="/pi/talk-to-pi"
            className="wz-btn wz-btn-secondary"
            style={{ padding: "12px 22px", fontSize: "15px" }}
          >
            Book a demo
          </Link>
        </div>
        <div
          style={{
            fontSize: "12.5px",
            color: "var(--text-muted)",
            marginTop: "14px",
          }}
        >
          Live in ~3 minutes · works with any POS or Excel export · your data
          stays private
        </div>
        <div
          className="wz-card"
          style={{
            marginTop: "48px",
            padding: "20px",
            textAlign: "left",
            boxShadow: "var(--shadow-card)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "14px",
              flexWrap: "wrap",
              gap: "8px",
            }}
          >
            <div style={{ fontWeight: "750", fontSize: "14px" }}>
              Today · War Room{" "}
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--text-muted)",
                  fontWeight: "500",
                }}
              >
                · illustrative
              </span>
            </div>
            <span
              className="wz-pill"
              style={{
                background: "var(--accent-soft)",
                color: "var(--accent-strong)",
              }}
            >
              ✦ AI brief updated 6:00 AM
            </span>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
              gap: "12px",
              marginBottom: "14px",
            }}
          >
            <div className="wz-kpi" style={{ margin: "0" }}>
              <div className="wz-kpi-label">Net Sales</div>
              <div className="wz-kpi-val" style={{ fontSize: "21px" }}>
                PKR 4.7M
              </div>
              <div
                style={{
                  fontSize: "11.5px",
                  color: "var(--good)",
                  marginTop: "2px",
                }}
              >
                +12% vs last wk
              </div>
            </div>
            <div className="wz-kpi" style={{ margin: "0" }}>
              <div className="wz-kpi-label">Gross Margin</div>
              <div className="wz-kpi-val" style={{ fontSize: "21px" }}>
                52.1%
              </div>
              <div
                style={{
                  fontSize: "11.5px",
                  color: "var(--good)",
                  marginTop: "2px",
                }}
              >
                on target
              </div>
            </div>
            <div className="wz-kpi" style={{ margin: "0" }}>
              <div className="wz-kpi-label">Net Profit</div>
              <div className="wz-kpi-val" style={{ fontSize: "21px" }}>
                PKR 1.1M
              </div>
              <div
                style={{
                  fontSize: "11.5px",
                  color: "var(--warn)",
                  marginTop: "2px",
                }}
              >
                pace 96%
              </div>
            </div>
            <div className="wz-kpi" style={{ margin: "0" }}>
              <div className="wz-kpi-label">Outlets</div>
              <div className="wz-kpi-val" style={{ fontSize: "21px" }}>
                8
              </div>
              <div
                style={{
                  fontSize: "11.5px",
                  color: "var(--warn)",
                  marginTop: "2px",
                }}
              >
                1 needs attention
              </div>
            </div>
          </div>
          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
              padding: "14px",
              background: "var(--accent-soft)",
              border: "1px solid var(--border-accent)",
              borderRadius: "12px",
            }}
          >
            <div style={{ fontSize: "18px" }} aria-hidden="true">
              ✦
            </div>
            <div
              style={{
                fontSize: "13px",
                color: "var(--text-secondary)",
                lineHeight: "1.6",
              }}
            >
              <strong style={{ color: "var(--text-primary)" }}>
                One outlet is dragging the group.
              </strong>{" "}
              Its margin slipped to 44% this week vs 52% for the group —
              markdown on one category is the driver. Recommended: cap the
              discount and review with the store manager.{" "}
              <span
                style={{ color: "var(--accent-strong)", fontWeight: "700" }}
              >
                Approve →
              </span>
            </div>
          </div>
        </div>
      </section>
      <section
        style={{
          maxWidth: "1080px",
          margin: "0 auto",
          padding: "0 24px",
          paddingTop: "40px",
          paddingBottom: "40px",
        }}
      >
        <h2
          style={{
            fontSize: "clamp(24px, 3.5vw, 34px)",
            fontWeight: "820",
            letterSpacing: "-0.8px",
            textAlign: "center",
            margin: "0 0 8px",
          }}
        >
          Running retail today feels like flying blind
        </h2>
        <p
          style={{
            textAlign: "center",
            color: "var(--text-secondary)",
            fontSize: "15px",
            margin: "0 auto 28px",
            maxWidth: "560px",
          }}
        >
          You have more data than ever — and less clarity. Sound familiar?
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
            gap: "16px",
          }}
        >
          <div style={{ padding: "4px" }}>
            <div
              style={{ fontSize: "24px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              🧩
            </div>
            <div
              style={{
                fontSize: "15.5px",
                fontWeight: "750",
                marginBottom: "5px",
              }}
            >
              Your numbers live in five places
            </div>
            <p
              style={{
                fontSize: "13px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              POS here, Excel there, WhatsApp updates from stores. Nothing adds
              up in one view.
            </p>
          </div>
          <div style={{ padding: "4px" }}>
            <div
              style={{ fontSize: "24px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              🐌
            </div>
            <div
              style={{
                fontSize: "15.5px",
                fontWeight: "750",
                marginBottom: "5px",
              }}
            >
              By the time the report lands, the week is gone
            </div>
            <p
              style={{
                fontSize: "13px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              Manual reporting means you&apos;re always looking at what already
              happened — too late to act.
            </p>
          </div>
          <div style={{ padding: "4px" }}>
            <div
              style={{ fontSize: "24px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              ❓
            </div>
            <div
              style={{
                fontSize: "15.5px",
                fontWeight: "750",
                marginBottom: "5px",
              }}
            >
              Nobody actually knows today&apos;s margin
            </div>
            <p
              style={{
                fontSize: "13px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              Sales you can see. True margin after discounts, GST and cost?
              Rarely, and never live.
            </p>
          </div>
          <div style={{ padding: "4px" }}>
            <div
              style={{ fontSize: "24px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              🎲
            </div>
            <div
              style={{
                fontSize: "15.5px",
                fontWeight: "750",
                marginBottom: "5px",
              }}
            >
              Decisions get made on gut, not data
            </div>
            <p
              style={{
                fontSize: "13px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              Which outlet to push, what to reorder, where margin is leaking —
              mostly guesswork.
            </p>
          </div>
        </div>
      </section>
      <section
        style={{
          background: "var(--bg-card)",
          borderTop: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
          padding: "56px 0",
        }}
      >
        <div
          style={{ maxWidth: "1080px", margin: "0 auto", padding: "0 24px" }}
        >
          <div style={{ textAlign: "center", marginBottom: "34px" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                fontSize: "12.5px",
                fontWeight: "700",
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                color: "var(--accent-strong)",
                background: "var(--accent-soft)",
                border: "1px solid var(--border-accent)",
                padding: "6px 12px",
                borderRadius: "999px",
              }}
            >
              The difference
            </span>
            <h2
              style={{
                fontSize: "clamp(24px, 3.5vw, 34px)",
                fontWeight: "820",
                letterSpacing: "-0.8px",
                margin: "16px 0 8px",
              }}
            >
              Never a chart without a decision
            </h2>
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "15px",
                margin: "0 auto",
                maxWidth: "560px",
              }}
            >
              Most tools stop at the number. WorkZap takes you all the way to
              the action.
            </p>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
              gap: "16px",
            }}
          >
            <div className="wz-card" style={{ padding: "22px" }}>
              <div
                style={{
                  fontSize: "12px",
                  fontWeight: "800",
                  color: "var(--accent-strong)",
                  letterSpacing: "0.4px",
                  textTransform: "uppercase",
                }}
              >
                What happened
              </div>
              <div
                style={{
                  fontSize: "17px",
                  fontWeight: "750",
                  margin: "8px 0 6px",
                  letterSpacing: "-0.3px",
                }}
              >
                Live, to the rupee
              </div>
              <p
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-secondary)",
                  lineHeight: "1.6",
                  margin: "0",
                }}
              >
                Every KPI across every outlet and channel, reconciled against
                your source system and refreshed automatically.
              </p>
            </div>
            <div className="wz-card" style={{ padding: "22px" }}>
              <div
                style={{
                  fontSize: "12px",
                  fontWeight: "800",
                  color: "var(--accent-strong)",
                  letterSpacing: "0.4px",
                  textTransform: "uppercase",
                }}
              >
                Why it happened
              </div>
              <div
                style={{
                  fontSize: "17px",
                  fontWeight: "750",
                  margin: "8px 0 6px",
                  letterSpacing: "-0.3px",
                }}
              >
                The driver, not just the number
              </div>
              <p
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-secondary)",
                  lineHeight: "1.6",
                  margin: "0",
                }}
              >
                The AI explains what moved — which outlet, SKU, discount or day
                — so you understand the cause in plain language.
              </p>
            </div>
            <div className="wz-card" style={{ padding: "22px" }}>
              <div
                style={{
                  fontSize: "12px",
                  fontWeight: "800",
                  color: "var(--accent-strong)",
                  letterSpacing: "0.4px",
                  textTransform: "uppercase",
                }}
              >
                What matters
              </div>
              <div
                style={{
                  fontSize: "17px",
                  fontWeight: "750",
                  margin: "8px 0 6px",
                  letterSpacing: "-0.3px",
                }}
              >
                Signal over noise
              </div>
              <p
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-secondary)",
                  lineHeight: "1.6",
                  margin: "0",
                }}
              >
                It flags the handful of risks and opportunities worth your
                attention today, and stays quiet about the rest.
              </p>
            </div>
            <div className="wz-card" style={{ padding: "22px" }}>
              <div
                style={{
                  fontSize: "12px",
                  fontWeight: "800",
                  color: "var(--accent-strong)",
                  letterSpacing: "0.4px",
                  textTransform: "uppercase",
                }}
              >
                What to do
              </div>
              <div
                style={{
                  fontSize: "17px",
                  fontWeight: "750",
                  margin: "8px 0 6px",
                  letterSpacing: "-0.3px",
                }}
              >
                A recommended action
              </div>
              <p
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-secondary)",
                  lineHeight: "1.6",
                  margin: "0",
                }}
              >
                Every insight arrives with a specific next step you can assign
                or approve in one tap — turning analysis into action.
              </p>
            </div>
          </div>
        </div>
      </section>
      <section
        id="modules"
        style={{ maxWidth: "1080px", margin: "0 auto", padding: "56px 24px" }}
      >
        <div style={{ textAlign: "center", marginBottom: "34px" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "12.5px",
              fontWeight: "700",
              letterSpacing: "0.5px",
              textTransform: "uppercase",
              color: "var(--accent-strong)",
              background: "var(--accent-soft)",
              border: "1px solid var(--border-accent)",
              padding: "6px 12px",
              borderRadius: "999px",
            }}
          >
            One platform, your modules
          </span>
          <h2
            style={{
              fontSize: "clamp(24px, 3.5vw, 34px)",
              fontWeight: "820",
              letterSpacing: "-0.8px",
              margin: "16px 0 8px",
            }}
          >
            Start with the core. Switch on what you need.
          </h2>
          <p
            style={{
              color: "var(--text-secondary)",
              fontSize: "15px",
              margin: "0 auto",
              maxWidth: "580px",
            }}
          >
            The Retail OS Core runs your whole business out of the box. Add
            modules as you grow — like apps on your phone.
          </p>
        </div>
        <div
          className="wz-card"
          style={{
            padding: "24px",
            marginBottom: "18px",
            borderColor: "var(--border-accent)",
            background: "var(--accent-soft)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "8px",
              marginBottom: "8px",
            }}
          >
            <div style={{ fontSize: "18px", fontWeight: "800" }}>
              🏬 Retail OS Core
            </div>
            <span
              className="wz-pill"
              style={{
                background: "var(--bg-card)",
                color: "var(--accent-strong)",
                border: "1px solid var(--border-accent)",
              }}
            >
              the base everyone gets
            </span>
          </div>
          <p
            style={{
              fontSize: "13.5px",
              color: "var(--text-secondary)",
              lineHeight: "1.6",
              margin: "0",
              maxWidth: "760px",
            }}
          >
            The CEO War Room · live P&amp;L to net profit · outlet &amp;
            category leaderboards · your AI analyst (ask anything, in plain
            language) · automatic data connectors · reports &amp; exports · and
            the Action Engine that turns insights into tasks and approvals.
          </p>
        </div>
        <div
          style={{
            fontSize: "12.5px",
            fontWeight: "700",
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            color: "var(--text-muted)",
            margin: "0 0 12px 2px",
          }}
        >
          Add-on modules
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: "14px",
          }}
        >
          <div
            className="wz-card"
            style={{
              padding: "18px",
              borderColor: "var(--border)",
              position: "relative",
            }}
          >
            <div
              style={{ fontSize: "22px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              ₨
            </div>
            <div
              style={{
                fontSize: "15px",
                fontWeight: "750",
                marginBottom: "4px",
              }}
            >
              Finance
            </div>
            <p
              style={{
                fontSize: "12.5px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              Deep P&amp;L, operating expenses, cashflow and net margin — the
              full financial picture, automated.
            </p>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              borderColor: "var(--border)",
              position: "relative",
            }}
          >
            <div
              style={{ fontSize: "22px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              📦
            </div>
            <div
              style={{
                fontSize: "15px",
                fontWeight: "750",
                marginBottom: "4px",
              }}
            >
              Planning &amp; Buying
            </div>
            <p
              style={{
                fontSize: "12.5px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              Sell-through, open-to-buy, dead stock and reorder signals so you
              buy the right stock at the right time.
            </p>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              borderColor: "var(--border)",
              position: "relative",
            }}
          >
            <div
              style={{ fontSize: "22px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              📣
            </div>
            <div
              style={{
                fontSize: "15px",
                fontWeight: "750",
                marginBottom: "4px",
              }}
            >
              Marketing
            </div>
            <p
              style={{
                fontSize: "12.5px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              ROAS, CAC and campaign performance tied to real sales — know what
              your ad spend actually returns.
            </p>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              borderColor: "var(--border)",
              position: "relative",
            }}
          >
            <div
              style={{ fontSize: "22px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              🛒
            </div>
            <div
              style={{
                fontSize: "15px",
                fontWeight: "750",
                marginBottom: "4px",
              }}
            >
              E-commerce
            </div>
            <p
              style={{
                fontSize: "12.5px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              Online orders, COD, courier and city analytics alongside your
              retail — one unified view.
            </p>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              borderColor: "var(--border)",
              position: "relative",
            }}
          >
            <div
              style={{ fontSize: "22px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              📹
            </div>
            <div
              style={{
                fontSize: "15px",
                fontWeight: "750",
                marginBottom: "4px",
              }}
            >
              Vision (CCTV)
            </div>
            <p
              style={{
                fontSize: "12.5px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              Footfall, queue times, conversion and shrinkage from your existing
              cameras — the store floor, quantified.
            </p>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              borderColor: "var(--border)",
              position: "relative",
            }}
          >
            <div
              style={{ fontSize: "22px", marginBottom: "8px" }}
              aria-hidden="true"
            >
              👥
            </div>
            <div
              style={{
                fontSize: "15px",
                fontWeight: "750",
                marginBottom: "4px",
              }}
            >
              HR &amp; Attendance
            </div>
            <p
              style={{
                fontSize: "12.5px",
                color: "var(--text-secondary)",
                lineHeight: "1.55",
                margin: "0",
              }}
            >
              Staff presence, productivity and payroll signals connected to
              outlet performance.
            </p>
          </div>
        </div>
        <p
          style={{
            textAlign: "center",
            fontSize: "12.5px",
            color: "var(--text-muted)",
            marginTop: "18px",
          }}
        >
          New modules ship regularly. Your Retail OS grows without you switching
          tools.
        </p>
      </section>
      <section
        id="how"
        style={{
          background: "var(--bg-card)",
          borderTop: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
          padding: "56px 0",
        }}
      >
        <div
          style={{
            maxWidth: "1080px",
            margin: "0 auto",
            padding: "0 24px",
            display: "grid",
            gridTemplateColumns: "1fr",
            gap: "34px",
          }}
        >
          <div style={{ textAlign: "center" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                fontSize: "12.5px",
                fontWeight: "700",
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                color: "var(--accent-strong)",
                background: "var(--accent-soft)",
                border: "1px solid var(--border-accent)",
                padding: "6px 12px",
                borderRadius: "999px",
              }}
            >
              How it works
            </span>
            <h2
              style={{
                fontSize: "clamp(24px, 3.5vw, 34px)",
                fontWeight: "820",
                letterSpacing: "-0.8px",
                margin: "16px 0 0",
              }}
            >
              From data to decisions in three steps
            </h2>
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "26px",
              maxWidth: "560px",
              margin: "0 auto",
              width: "100%",
            }}
          >
            <div
              style={{ display: "flex", gap: "16px", alignItems: "flex-start" }}
            >
              <div
                style={{
                  flexShrink: "0",
                  width: "38px",
                  height: "38px",
                  borderRadius: "999px",
                  display: "grid",
                  placeItems: "center",
                  background: "var(--accent-soft)",
                  border: "1px solid var(--border-accent)",
                  color: "var(--accent-strong)",
                  fontWeight: "800",
                  fontSize: "16px",
                }}
              >
                1
              </div>
              <div>
                <div
                  style={{
                    fontSize: "16px",
                    fontWeight: "750",
                    marginBottom: "4px",
                  }}
                >
                  Connect your data
                </div>
                <p
                  style={{
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.6",
                    margin: "0",
                    maxWidth: "460px",
                  }}
                >
                  Upload a sales export, or auto-sync your POS/ERP every night.
                  Any source, any column names — WorkZap maps it for you and
                  normalizes everything.
                </p>
              </div>
            </div>
            <div
              style={{ display: "flex", gap: "16px", alignItems: "flex-start" }}
            >
              <div
                style={{
                  flexShrink: "0",
                  width: "38px",
                  height: "38px",
                  borderRadius: "999px",
                  display: "grid",
                  placeItems: "center",
                  background: "var(--accent-soft)",
                  border: "1px solid var(--border-accent)",
                  color: "var(--accent-strong)",
                  fontWeight: "800",
                  fontSize: "16px",
                }}
              >
                2
              </div>
              <div>
                <div
                  style={{
                    fontSize: "16px",
                    fontWeight: "750",
                    marginBottom: "4px",
                  }}
                >
                  The AI goes to work
                </div>
                <p
                  style={{
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.6",
                    margin: "0",
                    maxWidth: "460px",
                  }}
                >
                  It watches every outlet, SKU and day — spotting margin leaks,
                  pace-to-target gaps, dead stock and outliers you&apos;d never
                  catch by hand.
                </p>
              </div>
            </div>
            <div
              style={{ display: "flex", gap: "16px", alignItems: "flex-start" }}
            >
              <div
                style={{
                  flexShrink: "0",
                  width: "38px",
                  height: "38px",
                  borderRadius: "999px",
                  display: "grid",
                  placeItems: "center",
                  background: "var(--accent-soft)",
                  border: "1px solid var(--border-accent)",
                  color: "var(--accent-strong)",
                  fontWeight: "800",
                  fontSize: "16px",
                }}
              >
                3
              </div>
              <div>
                <div
                  style={{
                    fontSize: "16px",
                    fontWeight: "750",
                    marginBottom: "4px",
                  }}
                >
                  You get decisions
                </div>
                <p
                  style={{
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.6",
                    margin: "0",
                    maxWidth: "460px",
                  }}
                >
                  A morning brief, live alerts when a rule is breached, and
                  one-tap actions your team can own — all from your phone or
                  desk.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section
        style={{ maxWidth: "1080px", margin: "0 auto", padding: "56px 24px" }}
      >
        <div style={{ textAlign: "center", marginBottom: "34px" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "12.5px",
              fontWeight: "700",
              letterSpacing: "0.5px",
              textTransform: "uppercase",
              color: "var(--accent-strong)",
              background: "var(--accent-soft)",
              border: "1px solid var(--border-accent)",
              padding: "6px 12px",
              borderRadius: "999px",
            }}
          >
            Real questions, real answers
          </span>
          <h2
            style={{
              fontSize: "clamp(24px, 3.5vw, 34px)",
              fontWeight: "820",
              letterSpacing: "-0.8px",
              margin: "16px 0 8px",
            }}
          >
            The questions you actually ask — answered from your own numbers
          </h2>
          <p
            style={{
              color: "var(--text-secondary)",
              fontSize: "15px",
              margin: "0 auto",
              maxWidth: "580px",
            }}
          >
            Ask in plain language. WorkZap answers from your live data and hands
            you the action to take — no analyst, no waiting.
          </p>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            gap: "14px",
          }}
        >
          <div
            className="wz-card"
            style={{
              padding: "18px",
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
            }}
          >
            <span
              style={{
                color: "var(--accent-strong)",
                fontSize: "16px",
                marginTop: "1px",
                flexShrink: "0",
              }}
              aria-hidden="true"
            >
              ✦
            </span>
            <span
              style={{
                fontSize: "14.5px",
                fontWeight: "600",
                lineHeight: "1.5",
                color: "var(--text-primary)",
              }}
            >
              “Which outlet is dragging down the group — and why?”
            </span>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
            }}
          >
            <span
              style={{
                color: "var(--accent-strong)",
                fontSize: "16px",
                marginTop: "1px",
                flexShrink: "0",
              }}
              aria-hidden="true"
            >
              ✦
            </span>
            <span
              style={{
                fontSize: "14.5px",
                fontWeight: "600",
                lineHeight: "1.5",
                color: "var(--text-primary)",
              }}
            >
              “What&apos;s my real margin after discounts, GST and cost?”
            </span>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
            }}
          >
            <span
              style={{
                color: "var(--accent-strong)",
                fontSize: "16px",
                marginTop: "1px",
                flexShrink: "0",
              }}
              aria-hidden="true"
            >
              ✦
            </span>
            <span
              style={{
                fontSize: "14.5px",
                fontWeight: "600",
                lineHeight: "1.5",
                color: "var(--text-primary)",
              }}
            >
              “What should I reorder this week, and what&apos;s dead stock?”
            </span>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
            }}
          >
            <span
              style={{
                color: "var(--accent-strong)",
                fontSize: "16px",
                marginTop: "1px",
                flexShrink: "0",
              }}
              aria-hidden="true"
            >
              ✦
            </span>
            <span
              style={{
                fontSize: "14.5px",
                fontWeight: "600",
                lineHeight: "1.5",
                color: "var(--text-primary)",
              }}
            >
              “Why did net profit fall last month when sales went up?”
            </span>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
            }}
          >
            <span
              style={{
                color: "var(--accent-strong)",
                fontSize: "16px",
                marginTop: "1px",
                flexShrink: "0",
              }}
              aria-hidden="true"
            >
              ✦
            </span>
            <span
              style={{
                fontSize: "14.5px",
                fontWeight: "600",
                lineHeight: "1.5",
                color: "var(--text-primary)",
              }}
            >
              “Are my discounts winning sales, or just burning margin?”
            </span>
          </div>
          <div
            className="wz-card"
            style={{
              padding: "18px",
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
            }}
          >
            <span
              style={{
                color: "var(--accent-strong)",
                fontSize: "16px",
                marginTop: "1px",
                flexShrink: "0",
              }}
              aria-hidden="true"
            >
              ✦
            </span>
            <span
              style={{
                fontSize: "14.5px",
                fontWeight: "600",
                lineHeight: "1.5",
                color: "var(--text-primary)",
              }}
            >
              “Which categories are quietly dying before it hurts me?”
            </span>
          </div>
        </div>
      </section>
      <section
        id="pricing"
        style={{
          background: "var(--bg-card)",
          borderTop: "1px solid var(--border)",
          borderBottom: "1px solid var(--border)",
          padding: "56px 0",
        }}
      >
        <div
          style={{ maxWidth: "1080px", margin: "0 auto", padding: "0 24px" }}
        >
          <div style={{ textAlign: "center", marginBottom: "34px" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                fontSize: "12.5px",
                fontWeight: "700",
                letterSpacing: "0.5px",
                textTransform: "uppercase",
                color: "var(--accent-strong)",
                background: "var(--accent-soft)",
                border: "1px solid var(--border-accent)",
                padding: "6px 12px",
                borderRadius: "999px",
              }}
            >
              Pricing
            </span>
            <h2
              style={{
                fontSize: "clamp(24px, 3.5vw, 34px)",
                fontWeight: "820",
                letterSpacing: "-0.8px",
                margin: "16px 0 8px",
              }}
            >
              One core platform. Pay for the modules you use.
            </h2>
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "15px",
                margin: "0 auto",
                maxWidth: "560px",
              }}
            >
              A one-time setup to connect your data, then a simple monthly
              subscription. Add or remove modules anytime.
            </p>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
              gap: "18px",
            }}
          >
            <div
              className="wz-card"
              style={{
                padding: "26px",
                display: "flex",
                flexDirection: "column",
                gap: "14px",
                borderColor: "var(--border)",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: "20px",
                    fontWeight: "800",
                    letterSpacing: "-0.3px",
                  }}
                >
                  Starter
                </div>
                <div
                  style={{
                    fontSize: "13px",
                    color: "var(--text-muted)",
                    marginTop: "2px",
                  }}
                >
                  Single store getting started
                </div>
              </div>
              <ul
                style={{
                  listStyle: "none",
                  padding: "0",
                  margin: "0",
                  display: "flex",
                  flexDirection: "column",
                  gap: "9px",
                  flex: "1",
                }}
              >
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Retail OS Core
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  1 add-on module
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Nightly data sync
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Email support
                </li>
              </ul>
              <Link
                href="/pi/talk-to-pi"
                className="wz-btn wz-btn-secondary"
                style={{ justifyContent: "center" }}
              >
                Book a demo
              </Link>
            </div>
            <div
              className="wz-card"
              style={{
                padding: "26px",
                display: "flex",
                flexDirection: "column",
                gap: "14px",
                borderColor: "var(--border-accent)",
                boxShadow: "var(--shadow-glow)",
              }}
            >
              <div>
                <span
                  className="wz-pill"
                  style={{
                    background: "var(--accent-soft)",
                    color: "var(--accent-strong)",
                    marginBottom: "8px",
                    display: "inline-block",
                  }}
                >
                  Most popular
                </span>
                <div
                  style={{
                    fontSize: "20px",
                    fontWeight: "800",
                    letterSpacing: "-0.3px",
                  }}
                >
                  Growth
                </div>
                <div
                  style={{
                    fontSize: "13px",
                    color: "var(--text-muted)",
                    marginTop: "2px",
                  }}
                >
                  Multi-outlet retailers
                </div>
              </div>
              <ul
                style={{
                  listStyle: "none",
                  padding: "0",
                  margin: "0",
                  display: "flex",
                  flexDirection: "column",
                  gap: "9px",
                  flex: "1",
                }}
              >
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Retail OS Core
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Finance + Planning + Marketing
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Up to 10 outlets
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  AI analyst, unlimited
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Priority support
                </li>
              </ul>
              <Link
                href="/pi/talk-to-pi"
                className="wz-btn wz-btn-primary"
                style={{ justifyContent: "center" }}
              >
                Book a demo
              </Link>
            </div>
            <div
              className="wz-card"
              style={{
                padding: "26px",
                display: "flex",
                flexDirection: "column",
                gap: "14px",
                borderColor: "var(--border)",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: "20px",
                    fontWeight: "800",
                    letterSpacing: "-0.3px",
                  }}
                >
                  Enterprise
                </div>
                <div
                  style={{
                    fontSize: "13px",
                    color: "var(--text-muted)",
                    marginTop: "2px",
                  }}
                >
                  Chains &amp; groups
                </div>
              </div>
              <ul
                style={{
                  listStyle: "none",
                  padding: "0",
                  margin: "0",
                  display: "flex",
                  flexDirection: "column",
                  gap: "9px",
                  flex: "1",
                }}
              >
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Everything in Growth
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Vision (CCTV) + E-commerce + HR
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Unlimited outlets &amp; seats
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Custom connectors
                </li>
                <li
                  style={{
                    display: "flex",
                    gap: "9px",
                    fontSize: "13.5px",
                    color: "var(--text-secondary)",
                    lineHeight: "1.5",
                  }}
                >
                  <span
                    style={{ color: "var(--accent-strong)", fontWeight: "800" }}
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                  Dedicated onboarding
                </li>
              </ul>
              <Link
                href="/pi/talk-to-pi"
                className="wz-btn wz-btn-secondary"
                style={{ justifyContent: "center" }}
              >
                Book a demo
              </Link>
            </div>
          </div>
        </div>
      </section>
      <section
        style={{
          maxWidth: "1080px",
          margin: "0 auto",
          padding: "64px 24px",
          textAlign: "center",
        }}
      >
        <h2
          style={{
            fontSize: "clamp(26px, 4vw, 40px)",
            fontWeight: "850",
            letterSpacing: "-1px",
            margin: "0 auto 14px",
            maxWidth: "640px",
          }}
        >
          See WorkZap on your own numbers — today.
        </h2>
        <p
          style={{
            color: "var(--text-secondary)",
            fontSize: "16px",
            margin: "0 auto 28px",
            maxWidth: "520px",
          }}
        >
          Create your workspace, upload a sales file, and get your first AI
          brief in about three minutes.
        </p>
        <div
          style={{
            display: "flex",
            gap: "12px",
            justifyContent: "center",
            flexWrap: "wrap",
          }}
        >
          <a
            href="https://app.workzap.ai"
            className="wz-btn wz-btn-primary"
            style={{ padding: "13px 26px", fontSize: "16px" }}
          >
            Get started free →
          </a>
          <Link
            href="/pi/talk-to-pi"
            className="wz-btn wz-btn-secondary"
            style={{ padding: "13px 26px", fontSize: "16px" }}
          >
            Book a demo
          </Link>
        </div>
      </section>
      <footer
        style={{ borderTop: "1px solid var(--border)", padding: "28px 0" }}
      >
        <div
          style={{
            maxWidth: "1080px",
            margin: "0 auto",
            padding: "0 24px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "16px",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div
              className="wz-logo"
              style={{ width: "28px", height: "28px", fontSize: "14px" }}
            >
              W
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
              WorkZap — The AI Operating System for Retail
            </div>
          </div>
          <div
            style={{
              display: "flex",
              gap: "18px",
              fontSize: "13px",
              color: "var(--text-muted)",
            }}
          >
            <a
              href="https://app.workzap.ai"
              style={{ color: "var(--text-muted)", textDecoration: "none" }}
            >
              Sign in
            </a>
            <Link
              href="/pi/talk-to-pi"
              style={{ color: "var(--text-muted)", textDecoration: "none" }}
            >
              Contact
            </Link>
            <span>© 2026 WorkZap</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
