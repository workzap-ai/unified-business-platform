import Link from "next/link";
import { PageHead, PI_CONTACT, Shell } from "./chrome";
import { Badge, Icon } from "./icons";
import { TalkForm } from "./talk-form";

export function NoriTalk() {
  return (
    <Shell current="/nori/talk">
      <PageHead
        label="Talk to us"
        title="Talk to us."
        lead="Book 30 minutes. Tell us how many shops you run. We show you the screens for your role."
      />
      <section className="nx-section nv-talk-section">
        <div className="nx-wrap nv-talk">
          <TalkForm />
          <aside className="nv-pi">
            <Badge name="chat" size={24} />
            <h2>Prefer WhatsApp? Message pi.</h2>
            <p>pi is Workzap’s assistant. Ask a question or ask for a meeting.</p>
            <Link className="nx-btn nx-btn-secondary" href={PI_CONTACT}>
              Message pi on WhatsApp
            </Link>
            <ul className="nv-points">
              <li>
                <Icon name="check" size={16} />
                Your shops and what you use today.
              </li>
              <li>
                <Icon name="check" size={16} />
                The screens that matter for your role.
              </li>
              <li>
                <Icon name="check" size={16} />
                The price, and how to start.
              </li>
            </ul>
          </aside>
        </div>
      </section>
    </Shell>
  );
}
