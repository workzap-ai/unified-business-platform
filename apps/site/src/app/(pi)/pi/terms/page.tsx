import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { PageIntro, Section, Slot } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/terms",
  title: "Terms for pi | pi by Workzap",
  description: "The terms for using pi, Workzap’s WhatsApp agent.",
});

export default function Terms() {
  return (
    <>
      <Breadcrumbs path="/terms" name="Terms" />
      <PageIntro
        title="Terms for pi"
        sub="These terms apply when you message pi."
      />
      <Section>
        <p>
          <Slot kind="WORKZAP">link to Workzap’s own terms</Slot>
        </p>
        <p>
          <Slot kind="WORKZAP">Workzap’s company name</Slot>
        </p>
      </Section>
    </>
  );
}
