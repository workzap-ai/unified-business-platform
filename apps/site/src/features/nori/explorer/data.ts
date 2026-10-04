// Content for the nori modules explorer. Every line comes from the "Complete Feature
// Inventory" (2026-10-03) and describes a capability listed as live. Left out on
// purpose: anything the inventory flags as not live or not ready to sell, client names,
// shop counts and measured results.
// Written to the nori voice (brand guide v1.0, pages 21-22): plain nouns instead of
// invented product words, sentences of up to 20 words, and none of the avoid-list words
// (optimise, leverage, insights, AI-powered, alert, critical, warning, urgent, must,
// unlock, supercharge).

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
  headline: string;
  summary: string;
  features: Feature[];
}

export const MODULE_TABS: ModuleTab[] = [
  {
    id: "stores",
    label: "Stores & warehouse",
    headline: "Every shop on a phone. Head office sees all of them.",
    summary:
      "Store managers get a simple daily app for their own shop. Head office sees the whole network. The warehouse sees what to move.",
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
        text: "Daily cash close, bank deposits and petty cash. Recording is locked until the shop’s first physical count is done.",
      },
      {
        title: "Field visits with a trail",
        text: "Area managers log weekly visits with location, three required photos and a drawer count.",
      },
      {
        title: "Warehouse requests",
        text: "Shop requests arrive with a suggestion: looks okay, why are they asking, or shouldn’t be asking. It is based on live sell-through. Transfers sent but never received are flagged when stuck.",
      },
    ],
  },
  {
    id: "finance",
    label: "Finance",
    headline: "A finance desk that checks itself.",
    summary:
      "Sales, audited profit and loss, cash, payables and receivables in one place. An automatic auditor points out what looks wrong.",
    features: [
      {
        title: "Period figures",
        text: "Net sales, bills, units, average transaction value, average selling price, units per transaction and gross margin for any period.",
      },
      {
        title: "Audited P&L and balance sheet",
        text: "By month or fiscal year, with sales by channel and profit by shop.",
      },
      {
        title: "Cash and treasury",
        text: "Cash position, supplier payables, receivables and the net. A seven-day cheque-due forecast and a four-week cash forecast.",
      },
      {
        title: "Reconciliation",
        text: "Courier cash-on-delivery tracking, online mis-booking detection, and cash collected compared with cash deposited, by shop.",
      },
      {
        title: "Automatic internal auditor",
        text: "A rules-based list of findings, ranked by how much each one matters.",
      },
      {
        title: "Margin leakage",
        text: "Who applied which discount, returns by shop, loyalty redemptions, and dead stock at risk of markdown.",
      },
      {
        title: "Ask in plain words",
        text: "Ask questions about live finance data, and flag any number that looks wrong.",
      },
    ],
  },
  {
    id: "planning",
    label: "Planning & buying",
    headline: "Know what to buy, move and clear.",
    summary:
      "One screen for stock cover, lost sales and cash tied up in slow stock. Products are classified by margin and speed, and transfers share one ledger.",
    features: [
      {
        title: "Stock on one screen",
        text: "Stock cover in months. Sales lost to stock-outs, sales stuck in the wrong shop, and cash tied up in dead stock.",
      },
      {
        title: "Stars, traps, cash cows and dogs",
        text: "Every product is classified by margin and sales speed, so you know what to back and what to stop.",
      },
      {
        title: "One shared stock ledger",
        text: "Transfers of every type are planned together against one ledger, so no unit is promised twice. Exports as pick-lists.",
      },
      {
        title: "Weekly stock rotation",
        text: "Pull dead stock, send proven sellers, then clear what is left, with a limit per shop.",
      },
      {
        title: "Size sets that stay whole",
        text: "Colour-and-size sets move together, so shops don’t end up with broken ranges.",
      },
      {
        title: "Trends and sell-through",
        text: "Daily and monthly trends compared with the 12-month average and the same month last year. Sell-through and best sellers too.",
      },
      {
        title: "Purchase plans you can check",
        text: "A six-month purchase-order plan, with forecast compared with actual.",
      },
    ],
  },
  {
    id: "ecommerce",
    label: "E-commerce",
    headline: "Your online store, run from the same desk.",
    summary:
      "Orders, ads, couriers, customer service, catalogue and stock for your Shopify store, next to your shops.",
    features: [
      {
        title: "Live store numbers",
        text: "Orders, revenue, discounts and returns from Shopify, with a date-wise breakdown and the week’s top products.",
      },
      {
        title: "Ads against targets",
        text: "Meta, Google, TikTok and Snapchat results with editable targets and progress bars.",
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
        text: "Auto-sort or drag-reorder collections. Create products with images in a single action.",
      },
      {
        title: "Stock across locations",
        text: "A multi-location stock table and a barcode-driven list builder that exports a replenishment sheet.",
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
    headline: "Know what your marketing earns. Message the right customers.",
    summary:
      "Daily ad results, suggested ad actions, and customer groups built from your own sales.",
    features: [
      {
        title: "Yesterday’s pulse",
        text: "Channel mix and brand health every morning.",
      },
      {
        title: "Suggested ad actions",
        text: "nori suggests pausing, scaling or refreshing ads, with a priority. You edit and approve before anything changes.",
      },
      {
        title: "Creative pipeline",
        text: "A board that follows content from shoot to live. A content calendar and an influencer tracker sit beside it.",
      },
      {
        title: "Daily creative brief",
        text: "A phone-first page for the content team: what to shoot, edit and post today, built from stock, offers and sales. No cost figures shown.",
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
        text: "Filter by recency, category and spend. Preview the count and cost, then download the list.",
      },
    ],
  },
  {
    id: "people",
    label: "People",
    headline: "Headcount, payroll and risk, with private data kept private.",
    summary:
      "A clear picture of your workforce and what it costs. Sensitive details stay hidden until someone chooses to see them.",
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
        title: "Odd figures",
        text: "Unusual patterns found automatically and ranked by how much they matter.",
      },
      {
        title: "Private details stay hidden",
        text: "ID numbers and bank details are blurred until someone clicks to reveal them.",
      },
    ],
  },
  {
    id: "executive",
    label: "Executive & control",
    headline: "The whole company at a glance, with clear rules.",
    summary:
      "A private view for the people who run the business, with policies, approvals and tasks every department shares.",
    features: [
      {
        title: "The company on one screen",
        text: "Revenue, gross profit, e-commerce, cash on delivery in transit, commitments and dead stock together.",
      },
      {
        title: "Cash you can free up",
        text: "A ranked list of cash you can recover, each with an owner and a next step.",
      },
      {
        title: "This month, live",
        text: "Target compared with actual at today’s pace, plus a nightly brief from every department.",
      },
      {
        title: "Think it through",
        text: "A private assistant that answers from your own company data and keeps the conversation.",
      },
      {
        title: "Policies with review",
        text: "Every operating policy sits in one rulebook. Anyone can propose a change. The AI can block a change but cannot approve one.",
      },
      {
        title: "Approvals and tasks",
        text: "Requests are approved with evidence and a clear trail. One task board spans every department.",
      },
      {
        title: "A view without the money",
        text: "Give an outside consultant an operations-only view. Sales, margin and profit are hidden by design.",
      },
    ],
  },
];
