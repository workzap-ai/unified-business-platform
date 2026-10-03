// Content for the retail modules explorer. Every line below comes from the
// "Complete Feature Inventory" (2026-10-03) and describes a capability listed as live.
// Deliberately left out: anything the inventory flags as not live or not ready to sell
// (mobile executive app, the WhatsApp assistant's office-PC dependency, HR automation,
// open-to-buy, projections), plus client names, shop counts and measured results.

export type TabId =
  | "stores"
  | "finance"
  | "planning"
  | "ecommerce"
  | "marketing"
  | "people"
  | "executive";

export interface Feature {
  title: string;
  text: string;
}

export interface ModuleTab {
  id: TabId;
  label: string;
  pill: string;
  headline: string;
  summary: string;
  features: Feature[];
}

export const MODULE_TABS: ModuleTab[] = [
  {
    id: "stores",
    label: "Stores & warehouse",
    pill: "Retail OS Core",
    headline: "Every shop run from a phone. Head office sees all of them.",
    summary:
      "Store managers get a simple daily app for their own shop. Head office gets one view of the whole network, and the warehouse gets a clear list of what to move.",
    features: [
      {
        title: "Sales against target",
        text: "Each manager sees their own shop’s sales against target, compared with last year, last month and last week.",
      },
      {
        title: "Find stock anywhere",
        text: "Look up any item across every shop, with photos of what to push and what is stuck.",
      },
      {
        title: "Photo-based daily checks",
        text: "A daily stock count and a store walk, done with photos and location. A defect stays open until a photo shows it fixed.",
      },
      {
        title: "Cash that has to balance",
        text: "Daily cash close, bank deposits and petty cash, with recording locked until the shop’s first physical count is done.",
      },
      {
        title: "Field visits that leave a trail",
        text: "Area managers log weekly visits with location, three required photos and a drawer count.",
      },
      {
        title: "Warehouse demand inbox",
        text: "Shop requests arrive with a recommendation — looks okay, why are they asking, or shouldn’t be asking — based on live sell-through. Transfers sent but never received are flagged when stuck.",
      },
    ],
  },
  {
    id: "finance",
    label: "Finance",
    pill: "Finance module",
    headline: "A finance desk that watches itself.",
    summary:
      "Sales, audited profit and loss, cash, payables and receivables in one place, with an automatic auditor that flags what looks wrong.",
    features: [
      {
        title: "Period KPIs",
        text: "Net sales, bills, units, average transaction value, average selling price, units per transaction and gross margin for any period.",
      },
      {
        title: "Audited P&L and balance sheet",
        text: "By month or fiscal year, with sales by channel and profit by shop.",
      },
      {
        title: "Cash and treasury",
        text: "Cash position, supplier payables, receivables and the net, plus a seven-day cheque-due forecast and a four-week cash forecast.",
      },
      {
        title: "Reconciliation",
        text: "Courier cash-on-delivery tracking, online mis-booking detection, and cash collected versus deposited by shop.",
      },
      {
        title: "Automatic internal auditor",
        text: "A rules-driven feed of findings, ranked Critical, Warning, Info or Positive.",
      },
      {
        title: "Margin leakage",
        text: "Who applied which discount, returns by shop, loyalty redemptions, and dead stock at risk of markdown.",
      },
      {
        title: "Ask the finance AI",
        text: "Ask questions about live finance data in plain language, and flag any number that looks wrong.",
      },
    ],
  },
  {
    id: "planning",
    label: "Planning & buying",
    pill: "Planning & Buying module",
    headline: "Know what to buy, move and clear.",
    summary:
      "One cockpit for stock cover, lost sales and cash frozen in slow stock, with margin classification and transfer planning on a single shared ledger.",
    features: [
      {
        title: "Stock command",
        text: "Stock cover in months, sales lost to stock-outs, sales trapped in the wrong location, and cash frozen in dead stock.",
      },
      {
        title: "Stars, traps, cash cows and dogs",
        text: "Every product classified by margin and sales velocity, so you know what to back and what to stop.",
      },
      {
        title: "One shared stock ledger",
        text: "Transfers of every type are planned together against one ledger, so no unit is promised twice. Exports as pick-lists.",
      },
      {
        title: "Rotation loop",
        text: "A weekly cycle: pull dead stock, send proven sellers, then clear what is left, with a ceiling per shop.",
      },
      {
        title: "Size sets that stay whole",
        text: "Colour-and-size sets move together, so shops don’t end up with broken ranges.",
      },
      {
        title: "Trends and sell-through",
        text: "Daily and monthly trends against the 12-month average and the same month last year, plus sell-through and best sellers.",
      },
      {
        title: "Purchase plans you can check",
        text: "A six-month purchase-order plan with forecast-versus-actual tracking.",
      },
    ],
  },
  {
    id: "ecommerce",
    label: "E-commerce",
    pill: "E-commerce module",
    headline: "Your online store, run from the same desk.",
    summary:
      "Orders, ads, couriers, customer service, catalogue and stock for your Shopify store, alongside your shops.",
    features: [
      {
        title: "Live store numbers",
        text: "Orders, revenue, discounts and returns from Shopify, with a date-wise breakdown and the week’s top products.",
      },
      {
        title: "Ads against targets",
        text: "Meta, Google, TikTok and Snapchat performance with editable targets and progress bars.",
      },
      {
        title: "Couriers",
        text: "Shipment status, today’s dispatches and searchable shipment detail.",
      },
      {
        title: "Confirmations and returns",
        text: "Dispatched, delivered and pending orders, with returns and cancellations broken down by reason.",
      },
      {
        title: "Catalogue tools",
        text: "Auto-sort or drag-reorder collections, and create products with images in a single action.",
      },
      {
        title: "Stock across locations",
        text: "A multi-location stock table and a barcode-driven demand-list builder that exports a replenishment sheet.",
      },
      {
        title: "Complaints queue",
        text: "Customer complaints in one queue, linked from customer service.",
      },
    ],
  },
  {
    id: "marketing",
    label: "Marketing & customers",
    pill: "Marketing module",
    headline: "Know what your marketing earns. Message the right customers.",
    summary:
      "Daily ad performance, an AI queue of recommended ad actions, and customer segments built from your own sales.",
    features: [
      {
        title: "Yesterday’s pulse",
        text: "Channel mix and brand health every morning.",
      },
      {
        title: "AI action queue",
        text: "The AI recommends pausing, scaling or refreshing ads, with priority. You edit and approve before anything changes.",
      },
      {
        title: "Creative pipeline",
        text: "A board that follows content from shoot to live, plus a content calendar and an influencer tracker.",
      },
      {
        title: "Daily creative brief",
        text: "A phone-first page telling the content team what to shoot, edit and post today, built from stock, offers and sales data, without showing cost figures.",
      },
      {
        title: "Customer lifetime value",
        text: "Footfall, repeat buyers and average lifetime value, built from phone-tagged bills.",
      },
      {
        title: "Weekend SMS plans",
        text: "Segmented win-back and reactivation sends, with a built-in holdout group so you can measure the real lift.",
      },
      {
        title: "Audience builder",
        text: "Filter by recency, category and spend, preview the count and cost, and download the list.",
      },
    ],
  },
  {
    id: "people",
    label: "People",
    pill: "HR & Attendance module",
    headline: "Headcount, payroll and risk, with private data kept private.",
    summary:
      "A clear picture of your workforce and what it costs, with sensitive details hidden until someone chooses to see them.",
    features: [
      {
        title: "Executive overview",
        text: "Headcount and monthly cost trends, cost by branch and department, and attrition by month.",
      },
      {
        title: "Workforce explorer",
        text: "Search and filter every staff record in one table.",
      },
      {
        title: "Payroll by cycle",
        text: "A payroll view for each pay cycle.",
      },
      {
        title: "Leave and attendance",
        text: "Low leave balances, and the people who are late most often.",
      },
      {
        title: "Red flags",
        text: "Anomalies detected automatically and ranked Critical, High, Medium or Low.",
      },
      {
        title: "Sensitive data hidden by default",
        text: "ID numbers and bank details are blurred until someone clicks to reveal them.",
      },
    ],
  },
  {
    id: "executive",
    label: "Executive & control",
    pill: "Retail OS Core",
    headline:
      "The whole company at a glance, and the rules that keep it honest.",
    summary:
      "A private view for the people who run the business, with policies, approvals and tasks that every department shares.",
    features: [
      {
        title: "Company control tower",
        text: "Revenue, gross profit, e-commerce, cash on delivery in transit, commitments and dead stock on a single screen.",
      },
      {
        title: "Controllable money",
        text: "A ranked list of cash you can recover or unlock, each with an owner and a next action.",
      },
      {
        title: "This month, live",
        text: "Target against actual at today’s pace, plus a nightly brief from every department.",
      },
      {
        title: "Think out loud with AI",
        text: "A private AI strategist grounded in your own company data, with conversation history.",
      },
      {
        title: "Policies with AI review",
        text: "Every operating policy in one living rulebook. Anyone can propose a change; the AI can block a change but cannot approve one.",
      },
      {
        title: "Approvals and tasks",
        text: "Requests are approved with evidence and a clear trail, and one task board spans every department.",
      },
      {
        title: "A view without the money",
        text: "Give an outside consultant an operations-only view that hides sales, margin and profit by design.",
      },
    ],
  },
];
