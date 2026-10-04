import Image from "next/image";
import { JsonLd, breadcrumbs, pageMetadata } from "@/lib/seo";
import { APP_URL, TALK } from "@/features/workzap/data";
import { PI } from "@/features/pi/config";
import { Button, PageHero, PiChat } from "@/features/workzap/ui";

export const metadata = pageMetadata({
  path: "/contact",
  title: "Contact Workzap: message pi on WhatsApp",
  description: `Message pi, Workzap's WhatsApp agent, on ${PI.displayNumber}. pi is an AI and says so in its first message. Here is what to expect.`,
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
        title="Message pi on WhatsApp."
        lead="Every question and every enquiry to Workzap starts with pi, our WhatsApp agent. Tell pi what you need, in your own words."
      />

      <section className="wz-section wz-soft" aria-label="How to reach Workzap">
        <div className="wz-wrap">
          <div className="wz-contact">
            <div className="wz-card">
              <h2 className="wz-h2">Message pi on WhatsApp</h2>
              <p className="wz-contact-number">
                <strong>{PI.displayNumber}</strong>
              </p>
              <p>
                pi is an AI from Workzap, and it says so in its first message.
                pi is available on WhatsApp now. The button opens pi’s start
                page.
              </p>
              <div className="wz-actions">
                <Button href={TALK}>Talk to pi</Button>
              </div>
              <div className="wz-contact-qr">
                <Image
                  src="/pi-brand/pi-whatsapp-qr.svg"
                  alt={`QR code that opens a WhatsApp chat with pi at ${PI.displayNumber}`}
                  width={240}
                  height={240}
                  unoptimized
                />
                <p className="wz-cap">
                  On a computer? Scan this code with your phone’s camera to open
                  the chat.
                </p>
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
        </div>
      </section>
    </>
  );
}
