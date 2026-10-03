import { Breadcrumbs, piMetadata } from "@/features/pi/meta";
import { CtaBlock, PageIntro, Points, Section, Slot } from "@/features/pi/ui";

export const metadata = piMetadata({
  path: "/who-its-for",
  title: "Who pi is for: talk, don’t fill in forms | pi by Workzap",
  description:
    "pi is for people who would rather talk about a problem than fill in a form: owners, managers and teams. See who it suits, and who it doesn’t.",
});

export default function WhoItsFor() {
  return (
    <>
      <Breadcrumbs path="/who-its-for" name="Who pi is for" />
      <PageIntro
        title="Who pi is for"
        sub="pi is for people who’d rather talk about a problem than fill in a form."
      />
      <Section title="Who it suits">
        <Points
          items={[
            {
              lead: "Owners and managers",
              text: "who have problems on their mind and no time to write them up.",
            },
            {
              lead: "Teams",
              text: "where everyone sees a different problem and nothing gets collected in one place.",
            },
            {
              lead: "Organisations with many voices",
              text: (
                <>
                  where lots of people raise problems. pi sorts them, so you can
                  see which matter most.{" "}
                  <Slot kind="CONFIRM">multi-person use</Slot>
                </>
              ),
            },
            {
              lead: "Retailers",
              text: (
                <Slot kind="WORKZAP">
                  one short paragraph for retailers — supplied once Workzap’s
                  positioning is final
                </Slot>
              ),
            },
          ]}
        />
      </Section>
      <Section title="Who it isn’t for" tone="soft">
        <p>
          pi isn’t built for emergencies, and it won’t make decisions for you.
          If you need an answer from a person right now, ask pi to bring one in.{" "}
          <Slot kind="CONFIRM">
            pi can hand a chat to a person at Workzap — build the hand-off
            before this line goes live
          </Slot>
        </p>
      </Section>
      <CtaBlock page="who-its-for" pos="closing" />
    </>
  );
}
