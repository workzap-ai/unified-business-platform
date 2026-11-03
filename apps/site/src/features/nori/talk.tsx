import Link from "next/link";
import { PageHead, PI_CONTACT, Shell } from "./chrome";
import { TalkForm } from "./talk-form";

export function NoriTalk() {
  return (
    <Shell current="/nori/talk">
      <PageHead
        label="Talk to us"
        title="Talk to us."
        lead="Book 30 minutes. Tell us how many shops you run. We show you the screens for your role."
      />
      <section className="nx-section">
        <div className="nx-wrap nv-talk">
          <aside className="nv-pi">
            <span className="nx-label">Prefer WhatsApp?</span>
            <h2>Message pi.</h2>
            <p>pi is Workzap’s assistant. Ask a question or ask for a meeting.</p>
            <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
              Message pi on WhatsApp
            </Link>
            <ul className="nv-plain">
              <li>Your shops and what you use today.</li>
              <li>The screens that matter for your role.</li>
              <li>Plans, and how to start.</li>
            </ul>
          </aside>
          <TalkForm />
        </div>
      </section>
    </Shell>
  );
}
