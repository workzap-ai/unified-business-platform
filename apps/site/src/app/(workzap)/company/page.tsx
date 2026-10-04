import { JsonLd, breadcrumbs, pageMetadata } from "@/lib/seo";
import { PRODUCTS } from "@/features/workzap/data";
import {
  ArrowLink,
  CtaBand,
  Lockup,
  PageHero,
  Principles,
  SectionHead,
} from "@/features/workzap/ui";
import Link from "next/link";

export const metadata = pageMetadata({
  path: "/company",
  title: "About Workzap: the company behind nori and pi",
  description:
    "Workzap is a software company. It makes nori, a daily read for the shop, and pi, a WhatsApp agent. How we work with customers, and the rules we keep.",
  siteName: "Workzap",
  brand: "workzap",
});

export default function Company() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "Company", path: "/company" },
        ])}
      />
      <PageHero
        eyebrow="Company"
        title="About Workzap"
        lead="Workzap is a software company. We make two products, nori and pi. Both help the person who runs a business see what is going wrong and decide what to do about it."
      />

      <section className="wz-section wz-soft" aria-labelledby="what-we-do">
        <div className="wz-wrap wz-split">
          <div className="wz-head">
            <p className="wz-eyebrow">What we do</p>
            <h2 className="wz-h2" id="what-we-do">
              Software for finding problems and solving them.
            </h2>
          </div>
          <div className="wz-prose">
            <p>
              We make software for people who run businesses. nori reads a
              shop’s sales and stock and picks out the one thing worth looking
              at today. pi is a WhatsApp agent that listens to the problems a
              person describes, notes them and sorts them.
            </p>
            <p>
              Both are for the person who decides what happens next: the owner,
              the head of operations, the head of finance.
            </p>
          </div>
        </div>
      </section>

      <section className="wz-section">
        <div className="wz-wrap">
          <SectionHead
            eyebrow="What we make"
            title="Two products."
            sub="Each has its own pages, its own look and its own job."
          />
          <ul className="wz-makes">
            <li className="wz-make wz-make-nori">
              <div className="wz-make-art">
                <Lockup product={PRODUCTS.nori} height={84} decorative />
              </div>
              <h3 className="wz-h3">nori</h3>
              <p>
                The daily read for the shop. A short read each morning from the
                business’s own numbers, across seven areas.
              </p>
              <ArrowLink href="/nori">Explore nori</ArrowLink>
            </li>
            <li className="wz-make wz-make-pi">
              <div className="wz-make-art">
                <Lockup product={PRODUCTS.pi} height={96} decorative />
              </div>
              <h3 className="wz-h3">pi</h3>
              <p>
                Workzap’s WhatsApp agent. Tell pi what is going wrong on
                WhatsApp. pi is an AI and says so in its first message.
              </p>
              <ArrowLink href="/pi">Learn about pi</ArrowLink>
            </li>
          </ul>
        </div>
      </section>

      <section className="wz-section wz-soft">
        <div className="wz-wrap">
          <SectionHead
            eyebrow="Working with customers"
            title="How we work with you."
            sub="You choose where to start. You decide at each step."
          />
          <ul className="wz-paths">
            <li>
              <h3 className="wz-h3">With nori</h3>
              <ol className="wz-path-steps">
                <li>Sign in or get started at app.workzap.ai.</li>
                <li>Connect your data. nori reads it.</li>
                <li>
                  You get a short read each morning, with the one thing worth
                  looking at today.
                </li>
                <li>
                  Pick a plan: Starter, Growth or Enterprise. They differ by
                  size and support.
                </li>
              </ol>
              <p style={{ margin: "20px 0 0" }}>
                <ArrowLink href="/nori/how-it-works">How nori works</ArrowLink>
              </p>
            </li>
            <li>
              <h3 className="wz-h3">With pi</h3>
              <ol className="wz-path-steps">
                <li>Tell pi on WhatsApp what is going wrong.</li>
                <li>pi notes each problem and sorts them.</li>
                <li>
                  When you are ready, you get a solution document and a quote.
                </li>
                <li>
                  You decide whether Workzap builds it. Payment never happens
                  inside the chat.
                </li>
              </ol>
              <p style={{ margin: "20px 0 0" }}>
                <ArrowLink href="/pi/how-it-works">How pi works</ArrowLink>
              </p>
            </li>
          </ul>
          <p className="wz-cap" style={{ marginTop: 20 }}>
            <Link href="/pi/trust">How pi treats your chats</Link>.
          </p>
        </div>
      </section>

      <section className="wz-section">
        <div className="wz-wrap">
          <SectionHead
            eyebrow="Principles"
            title="Plain rules we keep."
            sub="What you can count on when you use a Workzap product."
          />
          <Principles />
        </div>
      </section>

      <CtaBand
        title="Tell pi what is going wrong."
        sub="Every enquiry to Workzap starts with pi on WhatsApp. pi is an AI and says so in its first message."
        secondary={{ href: "/contact", label: "How to reach us" }}
      />
    </>
  );
}
