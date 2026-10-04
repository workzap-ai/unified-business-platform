import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { PI } from "@/features/pi/config";
import { PageIntro, Points, Section } from "@/features/pi/ui";

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
                  Save <strong>{PI.displayNumber}</strong> in your contacts as
                  “pi” and send “Hi pi”.
                </>
              ),
            },
          ]}
        />
      </Section>
    </>
  );
}
