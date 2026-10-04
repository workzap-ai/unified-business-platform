import { JsonLd, breadcrumbs, pageMetadata } from "@/lib/seo";
import { APP_URL, TALK } from "@/features/workzap/data";
import { Button, PageHero, PiChat, Slot } from "@/features/workzap/ui";

export const metadata = pageMetadata({
  path: "/contact",
  title: "Contact Workzap: talk to pi on WhatsApp",
  description:
    "There is one way to reach Workzap: talk to pi, our WhatsApp agent. pi is an AI and says so. Here is what to expect when you start a chat.",
  siteName: "Workzap",
  brand: "workzap",
});

export default function Contact() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "Contact", path: "/contact" },
        ])}
      />
      <PageHero
        eyebrow="Contact"
        title="Talk to pi. That is how you reach Workzap."
        lead="Every question and every enquiry starts with pi, our WhatsApp agent. Tell pi what you need, in your own words."
      />

      <section className="wz-section wz-soft" aria-label="How to reach Workzap">
        <div className="wz-wrap">
          <div className="wz-contact">
            <div className="wz-card">
              <h2 className="wz-h2">Start a chat with pi</h2>
              <p>
                pi is an AI from Workzap, and it says so in its first message.
                pi is not launched yet. The button opens pi’s start page.
              </p>
              <div className="wz-actions">
                <Button href={TALK}>Talk to pi</Button>
              </div>
              <h3 className="wz-h3" style={{ marginTop: 40 }}>
                What to expect
              </h3>
              <ol className="wz-expect" style={{ marginTop: 20 }}>
                <li>
                  pi tells you it is an AI, then asks what is going wrong.
                </li>
                <li>
                  You answer in your own words, the way you would tell a
                  colleague.
                </li>
                <li>pi notes each problem and sorts them.</li>
                <li>
                  When you are ready, you get a solution document and a quote.
                  You decide whether Workzap builds it.
                </li>
                <li>Payment never happens inside the chat.</li>
              </ol>
            </div>
            <div className="wz-contact-art">
              <PiChat />
            </div>
          </div>

          <div className="wz-aside">
            <p>
              <strong>Already use nori?</strong> Sign in to your account, or get
              started, at app.workzap.ai.
            </p>
            <a className="wz-btn wz-btn-secondary wz-btn-sm" href={APP_URL}>
              Sign in
            </a>
          </div>
          <p className="wz-cap" style={{ marginTop: 20 }}>
            <Slot kind="WORKZAP">
              Only if the owner wants a route to a person (an email address or a
              form): the details. Today pi is the only contact route.
            </Slot>
          </p>
        </div>
      </section>
    </>
  );
}
