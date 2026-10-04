import { JsonLd, breadcrumbs, pageMetadata } from "@/lib/seo";
import { APP_URL, PRODUCTS, TALK } from "@/features/workzap/data";
import { ArrowLink, CtaBand, Lockup, PageHero } from "@/features/workzap/ui";

export const metadata = pageMetadata({
  path: "/products",
  title: "Products: nori and pi | Workzap",
  description:
    "Compare Workzap's two products. nori reads your sales and stock each morning. pi is a WhatsApp agent for the problems in your business, available now.",
  siteName: "Workzap",
  brand: "workzap",
});

export default function Products() {
  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: "Workzap", path: "/" },
          { name: "Products", path: "/products" },
        ])}
      />
      <PageHero
        eyebrow="Products"
        title="Two products. Two ways to see what needs fixing."
        lead="nori starts from your numbers. pi starts from what you tell it. Here is who each one is for, what it does and how you start."
      />

      <section className="wz-section wz-soft" aria-label="Compare nori and pi">
        <div className="wz-wrap">
          <table className="wz-compare">
            <caption className="wz-sr">
              nori and pi, compared: who it is for, what it does, how you start
              and plans.
            </caption>
            <thead>
              <tr>
                <td className="wz-sr">Question</td>
                <th scope="col">
                  <span className="wz-col-head wz-col-nori">
                    <Lockup product={PRODUCTS.nori} height={56} />
                    <p>{PRODUCTS.nori.line}</p>
                  </span>
                </th>
                <th scope="col">
                  <span className="wz-col-head wz-col-pi">
                    <Lockup product={PRODUCTS.pi} height={56} />
                    <p>{PRODUCTS.pi.line} Live on WhatsApp.</p>
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">Who it is for</th>
                <td data-label="nori">
                  <p>
                    Business owners and department heads who want a short read
                    from their own sales and stock.
                  </p>
                </td>
                <td data-label="pi">
                  <p>
                    A person running a business who wants to say what is going
                    wrong.
                  </p>
                </td>
              </tr>
              <tr>
                <th scope="row">What it does</th>
                <td data-label="nori">
                  <p>
                    Reads your sales and stock and picks out the one thing worth
                    looking at today. A short read each morning.
                  </p>
                  <p>
                    Seven areas: stores and warehouse, finance, planning and
                    buying, e-commerce, marketing and customers, people, and
                    executive and control.
                  </p>
                </td>
                <td data-label="pi">
                  <p>
                    Notes the problems you describe on WhatsApp and sorts them.
                    When you are ready, you get a solution document and a quote.
                  </p>
                  <p>pi is an AI and says so in its first message.</p>
                </td>
              </tr>
              <tr>
                <th scope="row">How you start</th>
                <td data-label="nori">
                  <p>
                    <a className="wz-arrow-link" href={APP_URL}>
                      Sign in or get started at app.workzap.ai
                    </a>
                  </p>
                </td>
                <td data-label="pi">
                  <p>Start a chat on WhatsApp. pi is available now.</p>
                  <p>
                    <ArrowLink href={TALK}>Talk to pi</ArrowLink>
                  </p>
                </td>
              </tr>
              <tr>
                <th scope="row">Plans and quotes</th>
                <td data-label="nori">
                  <p>
                    Starter, Growth and Enterprise. They differ by size and
                    support.
                  </p>
                </td>
                <td data-label="pi">
                  <p>
                    A solution comes with a quote. You decide whether Workzap
                    builds it. Payment never happens inside the chat.
                  </p>
                </td>
              </tr>
              <tr>
                <th scope="row">Status</th>
                <td data-label="nori">
                  <p>Vision (CCTV) is coming soon.</p>
                </td>
                <td data-label="pi">
                  <p>Available on WhatsApp now.</p>
                </td>
              </tr>
              <tr>
                <th scope="row">Learn more</th>
                <td data-label="nori">
                  <p>
                    <ArrowLink href="/nori">About nori</ArrowLink>
                  </p>
                  <p>
                    <ArrowLink href="/nori/whats-inside">
                      What’s inside
                    </ArrowLink>
                  </p>
                  <p>
                    <ArrowLink href="/nori/pricing">Pricing</ArrowLink>
                  </p>
                </td>
                <td data-label="pi">
                  <p>
                    <ArrowLink href="/pi">About pi</ArrowLink>
                  </p>
                  <p>
                    <ArrowLink href="/pi/how-it-works">How pi works</ArrowLink>
                  </p>
                  <p>
                    <ArrowLink href="/pi/faq">Questions about pi</ArrowLink>
                  </p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="wz-section" aria-labelledby="which">
        <div className="wz-wrap">
          <div className="wz-head">
            <p className="wz-eyebrow">Where to start</p>
            <h2 className="wz-h2" id="which">
              Start with the question you have.
            </h2>
          </div>
          <ul className="wz-questions">
            <li className="wz-q-nori">
              <h3 className="wz-h3">What should I look at today?</h3>
              <p>
                nori reads your sales and stock and picks out the one thing
                worth looking at, in a short read each morning.
              </p>
              <ArrowLink href="/nori">Explore nori</ArrowLink>
            </li>
            <li className="wz-q-pi">
              <h3 className="wz-h3">What is going wrong?</h3>
              <p>
                Tell pi in your own words. pi notes and sorts each problem, then
                you decide whether Workzap builds a solution.
              </p>
              <ArrowLink href="/pi">Learn about pi</ArrowLink>
            </li>
          </ul>
        </div>
      </section>

      <CtaBand
        title="Not sure where to start?"
        sub="Tell pi what is going wrong on WhatsApp. pi is an AI and says so in its first message."
        secondary={null}
      />
    </>
  );
}
