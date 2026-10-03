import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { PageIntro, Points, Section, Slot } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/talk-to-pi/help",
  title: "WhatsApp didn’t open? How to reach pi",
  description:
    "If the pi button did nothing, here is how to install WhatsApp or use WhatsApp Web and message pi.",
});

export default function Help() {
  return (
    <>
      <Breadcrumbs path="/talk-to-pi/help" name="WhatsApp didn’t open?" />
      <PageIntro title="WhatsApp didn’t open?" />
      <Section>
        <Points
          items={[
            {
              lead: "On a phone.",
              text: "Install WhatsApp from your app store, then tap the button again.",
            },
            {
              lead: "On a computer.",
              text: "Open WhatsApp Web, or scan the code on the start page with your phone.",
            },
            {
              lead: "Message pi directly.",
              text: (
                <>
                  Save <Slot kind="PRODUCT">pi’s number</Slot> in your contacts
                  as “pi” and send “Hi pi”.
                </>
              ),
            },
          ]}
        />
        <p style={{ marginTop: 18 }}>
          Still stuck?{" "}
          <Slot kind="WORKZAP">
            a way to reach Workzap for someone who cannot use WhatsApp at all.
            All contact currently goes through pi, which needs WhatsApp, so this
            page would be a dead end
          </Slot>
        </p>
      </Section>
    </>
  );
}
