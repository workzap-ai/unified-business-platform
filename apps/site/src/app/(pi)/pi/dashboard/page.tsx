import { notFound } from "next/navigation";
import { PI } from "@/features/pi/config";
import { WhatsAppButton } from "@/features/pi/client";
import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import {
  AiChip,
  Face,
  PageIntro,
  Points,
  Section,
  Slot,
} from "@/features/pi/ui";
import Image from "next/image";

export const metadata = piMetadata({
  path: "/dashboard",
  title: "Your problems, sorted: the pi dashboard | pi by Workzap",
  description:
    "See every problem pi has noted, sorted by type, with exactly what you said. The pi dashboard keeps your problems in one place.",
});

// Written and ready, but hidden until the dashboard exists (see PI.live in config.ts).
export default function Dashboard() {
  if (!PI.live.dashboard) notFound();
  return (
    <>
      <Breadcrumbs path="/dashboard" name="Your problems, sorted" />
      <PageIntro
        title="See every problem pi has noted"
        sub="Your dashboard shows what you told pi, sorted by type, so you can see what keeps coming up."
      />
      <Section title="What you’ll see">
        <div className="pi-two">
          <Points
            items={[
              {
                lead: "Sorted by type.",
                text: "Your problems grouped so similar ones sit together.",
              },
              {
                lead: "Open and fixed.",
                text: "See what’s still open and what’s been sorted out.",
              },
              {
                lead: "Exactly what you said.",
                text: "Each note sits next to your original message, so you can check pi got it right and correct it.",
              },
              {
                lead: "What keeps coming up.",
                text: (
                  <>
                    Patterns over time, so you can see which problems matter
                    most. <Slot kind="PRODUCT">confirm this view exists</Slot>
                  </>
                ),
              },
              {
                lead: "Your solution and quote.",
                text: (
                  <>
                    If you ask for them, they sit here too, with their status.{" "}
                    <Slot kind="PRODUCT">
                      confirm they live on the dashboard
                    </Slot>
                  </>
                ),
              },
              {
                lead: "Yours to control.",
                text: (
                  <Slot kind="PRODUCT">
                    whether you can edit, export or delete what pi has noted,
                    and how
                  </Slot>
                ),
              },
            ]}
          />
          <div
            className="pi-mock"
            role="group"
            aria-label="Illustrative dashboard"
          >
            <div className="pi-mock-head">
              <span>
                <Image
                  src="/pi-brand/pi-lockup-horizontal-color.svg"
                  alt="pi by Workzap"
                  width={57}
                  height={30}
                  unoptimized
                />{" "}
                <AiChip />
              </span>
              <div className="pi-mock-tabs">
                <span>Problems</span>
                <span>Segments</span>
              </div>
            </div>
            <div className="pi-mock-body">
              <div className="pi-mock-card is-working">
                <Face name="think" size={64} />
                <strong>pi is sorting your latest messages</strong>
                <span>Thinking face — only while it is working</span>
              </div>
              <div className="pi-mock-card">
                <Face name="done" size={64} />
                <strong>Payment issue resolved</strong>
                <span>Resolved face — only once it is</span>
              </div>
            </div>
            <p className="pi-small" style={{ padding: "0 18px 14px" }}>
              Illustrative.
            </p>
          </div>
        </div>
      </Section>
      <Section title="Signing in" tone="soft">
        <p>
          <Slot kind="PRODUCT">
            how a customer signs in — for example with the WhatsApp number they
            chat from — and the sign-in link, which today would sit on the
            Workzap app
          </Slot>
        </p>
        <div className="pi-cta-row">
          <WhatsAppButton page="dashboard" pos="closing" variant="secondary" />
        </div>
      </Section>
    </>
  );
}
