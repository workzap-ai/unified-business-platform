import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { PageIntro, Section, Slot } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/privacy",
  title: "Privacy notice for pi | pi by Workzap",
  description: "How Workzap handles what you tell pi on WhatsApp.",
});

export default function Privacy() {
  return (
    <>
      <Breadcrumbs path="/privacy" name="Privacy notice" />
      <PageIntro
        title="Privacy notice for pi"
        sub="A short summary in plain English, and a link to Workzap’s full privacy notice."
      />
      <Section>
        <p>
          <Slot kind="PRODUCT">
            the plain-English summary of how pi uses what you tell it: what is
            kept, who can see it, how long, and how to ask for it to be deleted
          </Slot>
        </p>
        <p>
          <Slot kind="WORKZAP">link to Workzap’s full privacy policy</Slot>
        </p>
        <p>
          <Slot kind="WORKZAP">
            Workzap’s company name, and a legal contact for data requests
          </Slot>
        </p>
      </Section>
    </>
  );
}
