/**
 * Fictional, internally consistent sample business used only in demo data mode.
 *
 * - commerce (Northwind Trading Co., production): a tea/coffee & kitchenware retailer
 *   with enough volume to exercise tables, charts and every status.
 * - services (Brightline Studio): a small web agency; no inventory; PI captures
 *   requirements.
 * - empty (any other environment, e.g. Northwind Staging): first-use states.
 */
import type {
  BusinessSettings,
  Category,
  Customer,
  CustomerActivity,
  CustomerNote,
  Department,
  Employee,
  Expense,
  Invoice,
  InvoiceDetail,
  Lead,
  Location,
  Movement,
  Order,
  OrderDetail,
  Payment,
  ProductDetail,
  Quote,
  QuoteDetail,
  Variant,
  Branch,
} from "@/features/business/types";
import { centsToString, toCents } from "@/lib/format";
import { demoCollection, type DemoProfile } from "./store";
import { dateOnly, daysAgo, rng, type Rng } from "./random";

export type StockRow = {
  variant_id: string;
  location_id: string;
  on_hand: number;
  reserved: number;
};

export type DemoBusiness = {
  settings: BusinessSettings;
  customers: Customer[];
  notes: (CustomerNote & { customer_id: string })[];
  activities: (CustomerActivity & { customer_id: string })[];
  categories: Category[];
  products: ProductDetail[];
  locations: Location[];
  stock: StockRow[];
  movements: Movement[];
  leads: Lead[];
  quotes: QuoteDetail[];
  orders: OrderDetail[];
  invoices: InvoiceDetail[];
  expenses: Expense[];
  branches: Branch[];
  departments: Department[];
  employees: Employee[];
  counters: Record<string, number>;
};

/* Helpers ------------------------------------------------------------------------ */

export function sumMoney(values: string[]): string {
  return centsToString(values.reduce((acc, v) => acc + toCents(v), BigInt(0)));
}

export function mulMoney(price: string, quantity: number | string): string {
  const cents = toCents(price) * BigInt(Math.round(Number(quantity) * 1000));
  // quantity has up to 3 decimals; round half up to cents
  const scaled = (cents + BigInt(500)) / BigInt(1000);
  return centsToString(scaled);
}

export function taxOf(amount: string, rate: string): string {
  const cents = toCents(amount) * BigInt(Math.round(Number(rate) * 10000));
  return centsToString((cents + BigInt(5000)) / BigInt(10000));
}

export function nextNumber(
  business: DemoBusiness,
  kind: "order" | "quote" | "invoice" | "payment" | "expense",
) {
  const prefix = {
    order: "ORD",
    quote: "QUO",
    invoice: "INV",
    payment: "PAY",
    expense: "EXP",
  }[kind];
  business.counters[kind] = (business.counters[kind] ?? 0) + 1;
  return `${prefix}-${String(business.counters[kind]).padStart(6, "0")}`;
}

function roundPrice(r: Rng, min: number, max: number, step = 50) {
  return (Math.round(r.int(min, max) / step) * step).toFixed(2);
}

const FIRST = [
  "Ayesha",
  "Bilal",
  "Hira",
  "Usman",
  "Zainab",
  "Farhan",
  "Mehwish",
  "Hamza",
  "Sana",
  "Imran",
  "Nida",
  "Kashif",
  "Rabia",
  "Omar",
  "Maryam",
  "Danish",
  "Iqra",
  "Faisal",
  "Anum",
  "Saad",
  "Laiba",
  "Tariq",
  "Mahnoor",
  "Adeel",
  "Sarah",
  "James",
  "Priya",
  "Chen",
  "Elena",
  "Marcus",
];
const LAST = [
  "Khan",
  "Qureshi",
  "Siddiqui",
  "Malik",
  "Sheikh",
  "Ahmed",
  "Raza",
  "Hussain",
  "Chaudhry",
  "Butt",
  "Mirza",
  "Abbasi",
  "Farooq",
  "Iqbal",
  "Javed",
  "Nasir",
  "Rehman",
  "Aslam",
  "Whitfield",
  "Patel",
  "Liang",
  "Novak",
  "Okafor",
];
const COMPANIES = [
  "Harbor Foods",
  "Crescent Café",
  "Lumen Retail",
  "Saffron Kitchen",
  "Blue Pine Hotels",
  "The Daily Grind Coffee House",
  "Indus Gourmet Supplies",
  "Kiln & Crate",
  "Monsoon Bistro",
  "Evergreen Offices",
  "Tandoor Street Eats",
  "Margalla Heights Residency Management Co.",
  "Pearl Continental Supplies",
  "Urban Brew Collective",
  "Two Rivers Deli",
];
const CITIES = [
  "Karachi",
  "Lahore",
  "Islamabad",
  "Rawalpindi",
  "Faisalabad",
  "Multan",
  "Peshawar",
];

/* Catalog template (commerce) --------------------------------------------------------- */

type ProductTemplate = {
  name: string;
  category: string;
  description: string;
  variants: [string, string, number, number][];
  tracked?: boolean;
  piVisible?: boolean;
  status?: "inactive";
};
// variants: [sku suffix, variant name, min price, max price]
const COMMERCE_PRODUCTS: ProductTemplate[] = [
  {
    name: "Jasmine Green Tea",
    category: "tea",
    description: "Hand-rolled green tea scented with jasmine blossoms.",
    variants: [
      ["100", "100g tin", 900, 1100],
      ["250", "250g pouch", 1900, 2300],
    ],
  },
  {
    name: "Kashmiri Pink Chai Blend",
    category: "tea",
    description:
      "Traditional noon chai leaves with cardamom and a hint of salt.",
    variants: [["200", "200g", 1200, 1500]],
  },
  {
    name: "Assam Breakfast Black Tea",
    category: "tea",
    description: "Malty, full-bodied loose leaf for strong morning chai.",
    variants: [
      ["250", "250g", 1100, 1300],
      ["1KG", "1kg café pack", 3900, 4400],
    ],
  },
  {
    name: "Himalayan Oolong",
    category: "tea",
    description:
      "Lightly oxidised high-altitude oolong with stone-fruit notes.",
    variants: [["100", "100g", 2400, 2900]],
  },
  {
    name: "Chamomile & Lemongrass Infusion",
    category: "tea",
    description: "Caffeine-free herbal blend for evenings.",
    variants: [["50", "50g", 700, 900]],
  },
  {
    name: "Single Origin Ethiopia Yirgacheffe",
    category: "coffee",
    description:
      "Washed Arabica with bergamot and jasmine notes. Roasted weekly.",
    variants: [
      ["WB250", "Whole bean 250g", 2800, 3300],
      ["GR250", "Ground 250g", 2800, 3300],
    ],
  },
  {
    name: "House Espresso Blend",
    category: "coffee",
    description: "Chocolatey espresso blend for milk drinks.",
    variants: [
      ["WB500", "Whole bean 500g", 4200, 4800],
      ["WB1KG", "Whole bean 1kg", 7800, 8600],
    ],
  },
  {
    name: "Colombia Huila Decaf",
    category: "coffee",
    description: "Sugarcane-process decaf with caramel sweetness.",
    variants: [["WB250", "Whole bean 250g", 3100, 3500]],
  },
  {
    name: "Cold Brew Coffee Bags (10 pack)",
    category: "coffee",
    description: "Coarse-ground coffee in filter bags for overnight cold brew.",
    variants: [["10", "10 bags", 1800, 2100]],
  },
  {
    name: "Ceramic Pour-Over Kit",
    category: "equipment",
    description: "Dripper, carafe and 40 filters in a gift box.",
    variants: [
      ["WHT", "White", 6200, 6800],
      ["SND", "Sand", 6200, 6800],
    ],
  },
  {
    name: "Gooseneck Pour Kettle 1L",
    category: "equipment",
    description: "Stainless steel kettle with precise pour spout.",
    variants: [
      ["SS", "Stainless", 8900, 9800],
      ["BLK", "Matte black", 9400, 10200],
    ],
  },
  {
    name: "Burr Coffee Grinder — Hand",
    category: "equipment",
    description: "Conical steel burrs, 30 grind settings.",
    variants: [["STD", "Standard", 11500, 12900]],
  },
  {
    name: "Electric Burr Grinder Pro",
    category: "equipment",
    description: "Café-grade flat burrs with stepless adjustment.",
    variants: [["PRO", "Pro", 34000, 38500]],
  },
  {
    name: "French Press 800ml",
    category: "equipment",
    description: "Borosilicate glass with double mesh filter.",
    variants: [["800", "800ml", 4300, 4900]],
  },
  {
    name: "Digital Brewing Scale",
    category: "equipment",
    description: "0.1g precision with built-in timer.",
    variants: [["STD", "Standard", 5200, 5900]],
  },
  {
    name: "Stoneware Mug",
    category: "ceramics",
    description: "Hand-glazed 350ml mug. Each piece varies slightly.",
    variants: [
      ["BLK", "Black", 1600, 1900],
      ["TEAL", "Teal", 1600, 1900],
      ["CRM", "Cream", 1600, 1900],
    ],
  },
  {
    name: "Handmade Chai Cup Set (4)",
    category: "ceramics",
    description: "Set of four kulhar-inspired glazed cups.",
    variants: [["SET4", "Set of 4", 3200, 3700]],
  },
  {
    name: "Cast Iron Teapot 900ml",
    category: "ceramics",
    description: "Enamel-lined cast iron with infuser basket.",
    variants: [["900", "900ml", 7400, 8200]],
  },
  {
    name: "Tea Tasting Gift Box",
    category: "gifts",
    description: "Six 25g teas with a tasting journal.",
    variants: [["BOX6", "Box of 6", 4500, 5200]],
  },
  {
    name: "Coffee Lover's Hamper",
    category: "gifts",
    description: "Two coffees, a mug and a hand grinder, gift wrapped.",
    variants: [["HMP", "Hamper", 16500, 18900]],
  },
  {
    name: "Corporate Gift Set (custom branding)",
    category: "gifts",
    description:
      "Branded tea or coffee sets for corporate orders. Minimum 20 units.",
    variants: [["CORP", "Per set", 3800, 4400]],
    piVisible: false,
  },
  {
    name: "Paper Filters #2 (100)",
    category: "accessories",
    description: "Unbleached cone filters for pour-over drippers.",
    variants: [["100", "100 pack", 650, 800]],
  },
  {
    name: "Reusable Steel Straws (4)",
    category: "accessories",
    description: "With cleaning brush and pouch.",
    variants: [["4", "Pack of 4", 550, 700]],
  },
  {
    name: "Milk Frothing Pitcher 350ml",
    category: "accessories",
    description: "Stainless pitcher with measurement marks.",
    variants: [["350", "350ml", 2100, 2500]],
  },
  {
    name: "Tea Infuser Ball",
    category: "accessories",
    description: "Fine mesh infuser with chain.",
    variants: [["STD", "Standard", 400, 550]],
  },
  {
    name: "Barista Training Session (2 hours)",
    category: "services",
    description: "In-store hands-on session for up to 3 people.",
    variants: [["2H", "2-hour session", 9000, 9000]],
    tracked: false,
  },
  {
    name: "Seasonal Matcha Latte Powder",
    category: "tea",
    description: "Discontinued seasonal item.",
    variants: [["200", "200g", 2600, 2900]],
    status: "inactive",
  },
];

const SERVICE_PRODUCTS: ProductTemplate[] = [
  {
    name: "Website Design — Starter",
    category: "web",
    description: "Up to 5 pages, responsive, CMS setup, 2 revision rounds.",
    variants: [["STARTER", "Starter package", 1800, 1800]],
    tracked: false,
  },
  {
    name: "Website Design — Business",
    category: "web",
    description: "Up to 15 pages, custom design system, blog, analytics.",
    variants: [["BUSINESS", "Business package", 4800, 4800]],
    tracked: false,
  },
  {
    name: "E-commerce Store Build",
    category: "web",
    description: "Storefront with catalog, payments and order emails.",
    variants: [["STORE", "Store build", 7500, 7500]],
    tracked: false,
  },
  {
    name: "SEO Retainer",
    category: "marketing",
    description: "Monthly technical SEO, content briefs and reporting.",
    variants: [["SEO-M", "Per month", 900, 900]],
    tracked: false,
  },
  {
    name: "Care & Maintenance Plan",
    category: "support",
    description: "Updates, backups, uptime monitoring, 3h support per month.",
    variants: [["CARE-M", "Per month", 250, 250]],
    tracked: false,
  },
  {
    name: "Brand Identity Workshop",
    category: "marketing",
    description: "Half-day workshop with logo and palette deliverables.",
    variants: [["BRAND", "Workshop", 1200, 1200]],
    tracked: false,
  },
];

/* Generators ------------------------------------------------------------------------ */

function settingsFor(profile: DemoProfile): BusinessSettings {
  if (profile.kind === "services") {
    return {
      business_type: "service_business",
      default_currency: "USD",
      tax_rate: "0.0000",
      auto_invoice_on_order_confirm: true,
      low_stock_threshold: 5,
      invoice_due_days: 14,
      quote_validity_days: 30,
      quote_approval_threshold: "5000.00",
      max_discount_rate: "0.1000",
    };
  }
  return {
    business_type: "hybrid_business",
    default_currency: "PKR",
    tax_rate: "0.1600",
    auto_invoice_on_order_confirm: true,
    low_stock_threshold: 10,
    invoice_due_days: 14,
    quote_validity_days: 21,
    quote_approval_threshold: "250000.00",
    max_discount_rate: "0.1000",
  };
}

function buildCatalog(
  r: Rng,
  templates: ProductTemplate[],
  currency: string,
  prefix: string,
) {
  const categoryNames: Record<string, string> = {
    tea: "Tea",
    coffee: "Coffee",
    equipment: "Brewing Equipment",
    ceramics: "Ceramics & Teaware",
    gifts: "Gifts & Hampers",
    accessories: "Accessories",
    services: "Services",
    web: "Web Design",
    marketing: "Marketing",
    support: "Support Plans",
  };
  const used = [...new Set(templates.map((t) => t.category))];
  const categories: Category[] = used.map((slug) => ({
    id: `cat-${prefix}-${slug}`,
    name: categoryNames[slug] ?? slug,
    slug,
    description: "",
  }));
  const products: ProductDetail[] = templates.map((t, i) => {
    const productId = `prd-${prefix}-${i + 1}`;
    const base = t.name
      .split(/\s+/)
      .filter((w) => /^[A-Za-z]/.test(w))
      .slice(0, 2)
      .map((w) => w.slice(0, 3).toUpperCase())
      .join("-");
    const variants: Variant[] = t.variants.map(
      ([suffix, name, min, max], j) => ({
        id: `var-${prefix}-${i + 1}-${j + 1}`,
        product_id: productId,
        sku: `${base}-${suffix}`.slice(0, 40),
        name,
        price: roundPrice(r, min, max, currency === "USD" ? 50 : 50),
        currency,
        status: t.status === "inactive" ? "inactive" : "active",
        track_inventory: t.tracked !== false,
        low_stock_threshold:
          t.tracked === false
            ? null
            : r.chance(0.3)
              ? r.pick([5, 15, 20])
              : null,
        attributes: {},
      }),
    );
    return {
      id: productId,
      offering_type: t.tracked === false ? "service" : "product",
      name: t.name,
      description: t.description,
      category_id: `cat-${prefix}-${t.category}`,
      status: t.status ?? "active",
      pi_visible: t.piVisible ?? true,
      attributes:
        t.category === "coffee"
          ? {
              roast: r.pick(["Light", "Medium", "Dark"]),
              origin: r.pick(["Ethiopia", "Colombia", "Brazil", "Blend"]),
            }
          : {},
      created_at: daysAgo(r.int(60, 400)),
      category_name: categoryNames[t.category] ?? t.category,
      variants,
    };
  });
  return { categories, products };
}

function buildCustomers(
  r: Rng,
  count: number,
  prefix: string,
  services: boolean,
): Customer[] {
  const customers: Customer[] = [];
  for (let i = 0; i < count; i++) {
    const business = r.chance(services ? 0.8 : 0.35);
    const person = `${r.pick(FIRST)} ${r.pick(LAST)}`;
    const company = business
      ? services
        ? r.pick([
            "Northgate Dental",
            "Aria Fitness Studio",
            "Peak Legal Partners",
            "Verde Landscaping",
            "Kite & Co. Architects",
            "Moss Street Bakery",
            "Harbourline Logistics",
            "Solace Therapy Clinic",
          ])
        : COMPANIES[i % COMPANIES.length]!
      : null;
    const viaWhatsapp = r.chance(0.35);
    const tags = new Set<string>();
    if (business)
      tags.add(
        r.pick(
          services
            ? ["agency-client", "retainer"]
            : ["wholesale", "cafe", "horeca"],
        ),
      );
    if (r.chance(0.15)) tags.add("vip");
    if (viaWhatsapp) tags.add("whatsapp");
    if (r.chance(0.12)) tags.add(r.pick(CITIES).toLowerCase());
    const phone = services
      ? `+1415555${String(1000 + i).slice(-4)}`
      : `+92${r.pick(["300", "301", "321", "333", "345"])}${String(r.int(1000000, 9999999))}`;
    const name = business && r.chance(0.5) ? company! : person;
    customers.push({
      id: `cus-${prefix}-${i + 1}`,
      name:
        i === 7 && !services
          ? "Syeda Mahrukh Fatima Zaidi-Hashmi (Head of Procurement, Margalla Heights)"
          : name,
      email: r.chance(0.8)
        ? `${person.toLowerCase().replace(/[^a-z]+/g, ".")}@${
            company
              ? company
                  .toLowerCase()
                  .replace(/[^a-z]+/g, "")
                  .slice(0, 14)
              : "mail"
          }.example`
        : null,
      phone: r.chance(0.92) ? phone : null,
      company: name === company ? null : company,
      status: r.chance(0.07) ? "archived" : "active",
      source: viaWhatsapp ? "whatsapp" : r.chance(0.1) ? "import" : "manual",
      tags: [...tags],
      last_contacted_at: r.chance(0.85)
        ? daysAgo(r.int(0, 60) + r.next())
        : null,
      created_at: daysAgo(r.int(5, 380)),
    });
  }
  return customers.sort((a, b) => b.created_at.localeCompare(a.created_at));
}

function priceLines(
  items: {
    variant: Variant | null;
    description: string;
    quantity: number;
    unit_price: string;
    discount: string;
  }[],
  taxRate: string,
) {
  const lines = items.map((item, index) => {
    const gross = mulMoney(item.unit_price, item.quantity);
    return {
      ...item,
      position: index + 1,
      line_total: sumMoney([gross, `-${item.discount}`]),
      gross,
    };
  });
  const subtotal = sumMoney(lines.map((l) => l.gross));
  const discount_total = sumMoney(lines.map((l) => l.discount));
  const taxable = sumMoney([subtotal, `-${discount_total}`]);
  const tax_total = taxOf(taxable, taxRate);
  return {
    lines,
    subtotal,
    discount_total,
    tax_total,
    total: sumMoney([taxable, tax_total]),
  };
}

function build(profile: DemoProfile): DemoBusiness {
  const settings = settingsFor(profile);
  const empty: DemoBusiness = {
    settings,
    customers: [],
    notes: [],
    activities: [],
    categories: [],
    products: [],
    locations: [],
    stock: [],
    movements: [],
    leads: [],
    quotes: [],
    orders: [],
    invoices: [],
    expenses: [],
    branches: [],
    departments: [],
    employees: [],
    counters: {},
  };
  if (profile.kind === "empty") return empty;

  const services = profile.kind === "services";
  const prefix = services ? "bl" : "nw";
  const r = rng(services ? 9091 : 4242);
  const currency = settings.default_currency;
  const business = empty;
  const { categories, products } = buildCatalog(
    r,
    services ? SERVICE_PRODUCTS : COMMERCE_PRODUCTS,
    currency,
    prefix,
  );
  business.categories = categories;
  business.products = products;
  const sellable = products
    .filter((p) => p.status === "active")
    .flatMap((p) =>
      p.variants
        .filter((v) => v.status === "active")
        .map((v) => ({ product: p, variant: v })),
    );

  // Organization
  business.branches = services
    ? [
        {
          id: "br-bl-1",
          tenant_id: profile.tenantId,
          name: "Remote HQ",
          code: "hq",
        },
      ]
    : [
        {
          id: "br-nw-1",
          tenant_id: profile.tenantId,
          name: "Karachi Head Office",
          code: "khi",
        },
        {
          id: "br-nw-2",
          tenant_id: profile.tenantId,
          name: "Lahore Flagship Store",
          code: "lhe",
        },
        {
          id: "br-nw-3",
          tenant_id: profile.tenantId,
          name: "Islamabad Pop-up",
          code: "isb",
        },
      ];
  const deptNames = services
    ? ["Design", "Engineering", "Client Success"]
    : ["Operations", "Sales", "Customer Support", "Finance", "Warehouse"];
  business.departments = deptNames.map((name, i) => ({
    id: `dep-${prefix}-${i + 1}`,
    tenant_id: profile.tenantId,
    name,
    code: name.toLowerCase().replace(/[^a-z]+/g, "-"),
    branch_id: services
      ? null
      : business.branches[i % business.branches.length]!.id,
  }));

  // Locations & stock (commerce only)
  if (!services) {
    business.locations = [
      {
        id: "loc-nw-1",
        name: "Main Warehouse — Karachi",
        code: "main",
        branch_id: "br-nw-1",
        is_default: true,
        status: "active",
      },
      {
        id: "loc-nw-2",
        name: "Lahore Flagship Store",
        code: "lahore-store",
        branch_id: "br-nw-2",
        is_default: false,
        status: "active",
      },
      {
        id: "loc-nw-3",
        name: "Islamabad Pop-up",
        code: "isb-popup",
        branch_id: "br-nw-3",
        is_default: false,
        status: "inactive",
      },
    ];
    for (const { variant } of sellable) {
      if (!variant.track_inventory) continue;
      const roll = r.next();
      const main = roll < 0.08 ? 0 : roll < 0.2 ? r.int(1, 8) : r.int(18, 220);
      business.stock.push({
        variant_id: variant.id,
        location_id: "loc-nw-1",
        on_hand: main,
        reserved: main > 10 && r.chance(0.2) ? r.int(1, 4) : 0,
      });
      if (r.chance(0.6))
        business.stock.push({
          variant_id: variant.id,
          location_id: "loc-nw-2",
          on_hand: r.int(0, 40),
          reserved: 0,
        });
    }
    let m = 0;
    for (let i = 0; i < 90; i++) {
      const row = r.pick(business.stock);
      const kind = r.weighted([
        ["sale", 6],
        ["receipt", 2],
        ["adjustment", 1],
        ["return", 1],
      ] as const);
      const qty =
        kind === "sale"
          ? -r.int(1, 6)
          : kind === "receipt"
            ? r.int(12, 96)
            : kind === "return"
              ? r.int(1, 3)
              : r.pick([-2, -1, 1, 3]);
      m += 1;
      business.movements.push({
        id: `mov-nw-${m}`,
        variant_id: row.variant_id,
        location_id: row.location_id,
        quantity: qty,
        kind,
        reason:
          kind === "sale"
            ? "Order fulfilment"
            : kind === "receipt"
              ? r.pick([
                  "PO from Indus Tea Importers",
                  "Roastery delivery",
                  "Supplier restock",
                ])
              : kind === "return"
                ? "Customer return — unopened"
                : r.pick([
                    "Cycle count correction",
                    "Damaged in transit",
                    "Found during audit",
                  ]),
        balance_after: Math.max(0, row.on_hand + r.int(0, 20)),
        ref_type: kind === "sale" ? "order" : "manual",
        ref_id: null,
        actor_label:
          kind === "sale"
            ? r.pick(["PI", "Sana Malik", "Omar Siddiqui"])
            : r.pick(["Kashif Butt", "Omar Siddiqui"]),
        created_at: daysAgo(i * 0.7 + r.next()),
      });
    }
  }

  // Customers
  business.customers = buildCustomers(r, services ? 9 : 64, prefix, services);
  const activeCustomers = business.customers.filter(
    (c) => c.status === "active",
  );

  // Leads
  const leadTitles = services
    ? [
        "Website redesign for dental clinic",
        "Online store for bakery",
        "SEO retainer — legal firm",
        "Brand refresh + site",
        "Booking system for fitness studio",
        "Logistics company landing pages",
      ]
    : [
        "Café opening — espresso equipment",
        "Hotel chain tea amenity supply",
        "Corporate Eid gift sets (120 units)",
        "Office pantry monthly coffee",
        "Restaurant group chai program",
        "Wedding favors — tea boxes",
        "University cafeteria supply",
        "Co-working space coffee bar",
      ];
  const stages = [
    ["new", 4],
    ["qualified", 3],
    ["proposal", 3],
    ["won", 2],
    ["lost", 2],
  ] as const;
  leadTitles.forEach((title, i) => {
    const customer = r.pick(activeCustomers);
    const stage = r.weighted(stages);
    const fromPi = services ? i < 3 : r.chance(0.3);
    business.leads.push({
      id: `lead-${prefix}-${i + 1}`,
      customer_id: customer.id,
      title,
      stage,
      source: fromPi
        ? "pi"
        : r.pick(["manual", "referral", "website"] as const),
      estimated_value: r.chance(0.85)
        ? roundPrice(
            r,
            services ? 1500 : 45000,
            services ? 12000 : 900000,
            services ? 100 : 5000,
          )
        : null,
      currency,
      requirements:
        fromPi && services
          ? {
              service: r.pick(["Website design", "E-commerce store", "SEO"]),
              business_type: r.pick(["Dental clinic", "Bakery", "Law firm"]),
              website_type: r.pick(["Brochure", "Online store"]),
              features: r.pick([
                "Online booking, blog",
                "Payments, inventory sync",
                "Multilingual",
              ]),
              timeline: r.pick(["6 weeks", "Before March", "ASAP"]),
              budget: r.chance(0.5) ? r.pick(["$3k–5k", "Under $2k"]) : "",
            }
          : fromPi
            ? {
                quantity: r.pick(["120 sets", "40 kg / month"]),
                delivery_city: r.pick(CITIES),
              }
            : {},
      missing_information: fromPi
        ? services
          ? r.pick([["budget"], ["timeline", "budget"], []])
          : r.pick([["branding_artwork"], []])
        : [],
      notes: stage === "lost" ? "Went with a cheaper local supplier." : "",
      conversation_id: fromPi ? `conv-${prefix}-${i + 1}` : null,
      closed_at:
        stage === "won" || stage === "lost" ? daysAgo(r.int(2, 40)) : null,
      created_at: daysAgo(r.int(3, 90)),
      updated_at: daysAgo(r.int(0, 3)),
      customer_name: customer.name,
      next_stages: (
        {
          new: ["lost", "qualified"],
          qualified: ["lost", "new", "proposal"],
          proposal: ["lost", "qualified", "won"],
          won: [],
          lost: ["new"],
        } as Record<string, string[]>
      )[stage]!,
    });
  });

  // Orders + invoices + payments
  const orderCount = services ? 7 : 210;
  for (let i = 0; i < orderCount; i++) {
    const customer = r.pick(activeCustomers);
    const age = services ? r.int(3, 150) : Math.pow(r.next(), 1.25) * 340;
    const status =
      age < 1.5
        ? r.weighted([
            ["draft", 2],
            ["confirmed", 3],
            ["processing", 2],
          ] as const)
        : age < 6
          ? r.weighted([
              ["confirmed", 2],
              ["processing", 2],
              ["shipped", 3],
              ["cancelled", 1],
            ] as const)
          : r.weighted([
              ["delivered", 12],
              ["cancelled", 1],
              ["shipped", 1],
            ] as const);
    const count = services
      ? 1
      : r.weighted([
          [1, 5],
          [2, 3],
          [3, 2],
          [4, 1],
        ] as const);
    const picks = Array.from({ length: count }, () => r.pick(sellable));
    const unique = [...new Map(picks.map((p) => [p.variant.id, p])).values()];
    const priced = priceLines(
      unique.map(({ product, variant }) => ({
        variant,
        description: `${product.name} — ${variant.name}`,
        quantity: services
          ? 1
          : r.weighted([
              [1, 6],
              [2, 3],
              [3, 1],
              [6, 1],
              [12, 0.5],
            ] as const),
        unit_price: variant.price,
        discount: "0.00",
      })),
      settings.tax_rate,
    );
    const source = r.weighted([
      ["manual", 5],
      ["pi", services ? 1 : 3],
      ["quote", 1],
    ] as const);
    const number = nextNumber(business, "order");
    const orderId = `ord-${prefix}-${i + 1}`;
    const created = daysAgo(age, r.int(9, 21));
    const confirmed = status !== "draft" && status !== "cancelled";
    const order: OrderDetail = {
      fulfillment_type: services ? "service" : "product",
      id: orderId,
      number,
      customer_id: customer.id,
      quote_id: null,
      status,
      source,
      currency,
      subtotal: priced.subtotal,
      discount_total: priced.discount_total,
      tax_rate: settings.tax_rate,
      tax_total: priced.tax_total,
      total: priced.total,
      notes:
        source === "pi"
          ? "Created by PI after customer confirmation on WhatsApp."
          : "",
      confirmed_at: confirmed ? created : null,
      cancelled_at: status === "cancelled" ? created : null,
      created_by_label:
        source === "pi"
          ? "PI"
          : r.pick(["Amina Rahman", "Sana Malik", "Omar Siddiqui"]),
      created_at: created,
      customer_name: customer.name,
      lines: priced.lines.map((l, j) => ({
        id: `${orderId}-l${j + 1}`,
        variant_id: l.variant?.id ?? null,
        position: l.position,
        sku: l.variant?.sku ?? null,
        description: l.description,
        quantity: l.quantity,
        unit_price: l.unit_price,
        discount: l.discount,
        line_total: l.line_total,
      })),
      next_actions: [],
      invoice_id: null,
      invoice_number: null,
    };
    business.orders.push(order);
    if (confirmed) {
      const invNumber = nextNumber(business, "invoice");
      const invId = `inv-${prefix}-${business.invoices.length + 1}`;
      const issue = created.slice(0, 10);
      const dueOffset = settings.invoice_due_days;
      const due = new Date(new Date(created).getTime() + dueOffset * 86400000)
        .toISOString()
        .slice(0, 10);
      const overdue = due < dateOnly(0);
      const payState =
        age < 2
          ? "none"
          : overdue
            ? r.weighted([
                ["paid", 24],
                ["partial", 1],
                ["none", 1],
              ] as const)
            : r.weighted([
                ["paid", 3],
                ["none", 2],
                ["partial", 1],
              ] as const);
      const payments: Payment[] = [];
      let paid = "0.00";
      if (payState !== "none") {
        const amount =
          payState === "paid"
            ? priced.total
            : centsToString(toCents(priced.total) / BigInt(2));
        paid = amount;
        payments.push({
          id: `pay-${prefix}-${business.invoices.length + 1}`,
          invoice_id: invId,
          number: nextNumber(business, "payment"),
          amount,
          currency,
          method: r.pick([
            "bank_transfer",
            "cash",
            "card",
            "mobile_wallet",
          ] as const),
          received_on: dateOnly(-Math.max(0, age - r.int(1, 10))),
          reference: r.chance(0.6) ? `TRX${r.int(100000, 999999)}` : "",
          recorded_by_label: r.pick(["Nida Farooq", "Amina Rahman"]),
          created_at: daysAgo(Math.max(0, age - 2)),
        });
      }
      const invStatus =
        payState === "paid"
          ? "paid"
          : payState === "partial"
            ? "partially_paid"
            : "issued";
      const balance = sumMoney([priced.total, `-${paid}`]);
      const invoice: InvoiceDetail = {
        id: invId,
        number: invNumber,
        customer_id: customer.id,
        order_id: orderId,
        status: invStatus,
        issue_date: issue,
        due_date: due,
        currency,
        subtotal: priced.subtotal,
        discount_total: priced.discount_total,
        tax_total: priced.tax_total,
        total: priced.total,
        amount_paid: paid,
        notes: "",
        created_at: created,
        customer_name: customer.name,
        balance_due: balance,
        is_overdue: overdue && invStatus !== "paid",
        lines: order.lines.map((l) => ({
          id: `${invId}-${l.id}`,
          variant_id: l.variant_id,
          position: l.position,
          description: l.description,
          quantity: String(l.quantity),
          unit_price: l.unit_price,
          discount: l.discount,
          line_total: l.line_total,
        })),
        payments,
        next_actions: [],
      };
      business.invoices.push(invoice);
      order.invoice_id = invId;
      order.invoice_number = invNumber;
    }
  }
  // A draft manual invoice and a void one
  if (!services && activeCustomers[3]) {
    const c = activeCustomers[3];
    const priced = priceLines(
      [
        {
          variant: null,
          description: "Barista training — on-site (Harbor Foods)",
          quantity: 1,
          unit_price: "18000.00",
          discount: "0.00",
        },
      ],
      settings.tax_rate,
    );
    business.invoices.push({
      id: `inv-${prefix}-draft`,
      number: nextNumber(business, "invoice"),
      customer_id: c.id,
      order_id: null,
      status: "draft",
      issue_date: null,
      due_date: null,
      currency,
      subtotal: priced.subtotal,
      discount_total: "0.00",
      tax_total: priced.tax_total,
      total: priced.total,
      amount_paid: "0.00",
      notes: "Awaiting PO number from client.",
      created_at: daysAgo(1),
      customer_name: c.name,
      balance_due: priced.total,
      is_overdue: false,
      lines: [
        {
          id: "l1",
          variant_id: null,
          position: 1,
          description: priced.lines[0]!.description,
          quantity: "1",
          unit_price: "18000.00",
          discount: "0.00",
          line_total: priced.lines[0]!.line_total,
        },
      ],
      payments: [],
      next_actions: [],
    });
  }

  // Quotes
  const quoteCount = services ? 6 : 26;
  for (let i = 0; i < quoteCount; i++) {
    const customer = r.pick(activeCustomers);
    const status = r.weighted([
      ["draft", 3],
      ["pending_approval", 2],
      ["approved", 2],
      ["sent", 4],
      ["accepted", 4],
      ["rejected", 2],
      ["expired", 1],
      ["cancelled", 1],
    ] as const);
    const count = r.int(1, services ? 3 : 5);
    const picks = [
      ...new Map(
        Array.from({ length: count }, () => r.pick(sellable)).map((p) => [
          p.variant.id,
          p,
        ]),
      ).values(),
    ];
    const items = picks.map(({ product, variant }) => {
      const quantity = services ? 1 : r.pick([6, 10, 12, 20, 24, 40, 60]);
      const gross = mulMoney(variant.price, quantity);
      const discount =
        status === "pending_approval" && r.chance(0.7)
          ? centsToString((toCents(gross) * BigInt(15)) / BigInt(100))
          : r.chance(0.25)
            ? centsToString((toCents(gross) * BigInt(5)) / BigInt(100))
            : "0.00";
      return {
        variant,
        description: `${product.name} — ${variant.name}`,
        quantity,
        unit_price: variant.price,
        discount,
      };
    });
    if (services && r.chance(0.5))
      items.push({
        variant: null as unknown as Variant,
        description: "Custom integration — booking API (estimate)",
        quantity: 1,
        unit_price: "1400.00",
        discount: "0.00",
      });
    const priced = priceLines(
      items.map((it) => ({ ...it, variant: it.variant ?? null })),
      settings.tax_rate,
    );
    const created = daysAgo(r.int(0, 60) + r.next());
    const quoteId = `quo-${prefix}-${i + 1}`;
    const source = services
      ? i < 2
        ? "pi"
        : "manual"
      : r.chance(0.2)
        ? "pi"
        : "manual";
    const validUntil =
      status === "expired"
        ? dateOnly(-r.int(1, 20))
        : dateOnly(r.int(3, settings.quote_validity_days));
    business.quotes.push({
      id: quoteId,
      number: nextNumber(business, "quote"),
      customer_id: customer.id,
      lead_id: null,
      status,
      source,
      currency,
      subtotal: priced.subtotal,
      discount_total: priced.discount_total,
      tax_rate: settings.tax_rate,
      tax_total: priced.tax_total,
      total: priced.total,
      requires_approval: source === "pi" || status === "pending_approval",
      valid_until: validUntil,
      notes: status === "rejected" ? "Client found a lower price." : "",
      approved_at: ["approved", "sent", "accepted"].includes(status)
        ? created
        : null,
      sent_at: ["sent", "accepted", "rejected", "expired"].includes(status)
        ? created
        : null,
      order_id: null,
      created_at: created,
      customer_name: customer.name,
      lines: priced.lines.map((l, j) => ({
        id: `${quoteId}-l${j + 1}`,
        variant_id: l.variant?.id ?? null,
        position: l.position,
        description: l.description,
        quantity: String(l.quantity),
        unit_price: l.unit_price,
        discount: l.discount,
        line_total: l.line_total,
      })),
      next_actions: [],
    });
  }

  // Expenses
  const expenseSeeds: [Expense["category"], string, string, number, number][] =
    services
      ? [
          ["software", "Design & hosting tools", "Various SaaS", 380, 520],
          ["payroll", "Contractor payments", "Freelancers", 4200, 6800],
          ["marketing", "Portfolio ads", "Social ads", 300, 900],
          ["rent", "Co-working desks", "Hive Space", 900, 900],
        ]
      : [
          [
            "rent",
            "Warehouse rent — Karachi",
            "Korangi Estates",
            185000,
            185000,
          ],
          ["rent", "Lahore store rent", "Gulberg Properties", 240000, 240000],
          ["payroll", "Monthly payroll", "Staff salaries", 1150000, 1250000],
          [
            "utilities",
            "Electricity & internet",
            "K-Electric / PTCL",
            42000,
            68000,
          ],
          [
            "inventory",
            "Green coffee purchase",
            "Indus Tea Importers",
            380000,
            720000,
          ],
          ["marketing", "Instagram & Meta ads", "Meta", 45000, 120000],
          ["software", "POS & accounting software", "Various", 18000, 26000],
          ["travel", "Supplier visit — Gilgit", "PIA / hotels", 38000, 90000],
          [
            "professional_services",
            "Tax advisory",
            "Rahman & Co. Chartered",
            55000,
            55000,
          ],
          ["taxes", "Quarterly sales tax", "FBR", 210000, 390000],
        ];
  let e = 0;
  for (let month = 0; month < 6; month++) {
    for (const [category, description, vendor, min, max] of expenseSeeds) {
      if (category === "travel" && r.chance(0.6)) continue;
      if (category === "taxes" && month % 3 !== 0) continue;
      e += 1;
      business.expenses.push({
        id: `exp-${prefix}-${e}`,
        number: nextNumber(business, "expense"),
        category,
        description,
        vendor,
        amount: roundPrice(r, min, max, services ? 10 : 500),
        currency,
        incurred_on: dateOnly(-(month * 30 + r.int(1, 27))),
        status: r.chance(0.03) ? "void" : "recorded",
        recorded_by_label: r.pick(["Nida Farooq", "Amina Rahman"]),
        created_at: daysAgo(month * 30),
      });
    }
  }
  business.expenses.sort((a, b) => b.incurred_on.localeCompare(a.incurred_on));

  // Employees
  const roles = services
    ? [
        ["Amina Rahman", "Founder & Creative Director", 0],
        ["Leo Park", "Senior Web Developer", 1],
        ["Maya Castillo", "UI Designer", 0],
        ["Ibrahim Tahir", "Client Success Lead", 2],
        ["Nora Lindqvist", "Frontend Developer (Contract)", 1],
        ["Sami Haddad", "Design Intern", 0],
      ]
    : [
        ["Amina Rahman", "Managing Director", 0],
        ["Omar Siddiqui", "Operations Manager", 0],
        ["Kashif Butt", "Warehouse Supervisor", 4],
        ["Sana Malik", "Customer Support Lead", 2],
        ["Hamza Raza", "Support Agent", 2],
        ["Iqra Aslam", "Support Agent (Urdu & Punjabi)", 2],
        ["Nida Farooq", "Finance & Accounts Officer", 3],
        ["Faisal Iqbal", "Key Account Manager — HoReCa", 1],
        ["Laiba Javed", "Sales Associate — Lahore", 1],
        ["Adeel Mirza", "Sales Associate — Lahore", 1],
        ["Rabia Nasir", "Barista Trainer", 1],
        ["Tariq Hussain", "Picker & Packer", 4],
        ["Danish Abbasi", "Picker & Packer", 4],
        ["Anum Sheikh", "Delivery Coordinator", 0],
        ["Saad Qureshi", "Procurement Officer", 0],
        ["Mahnoor Khan", "Marketing Executive", 1],
        ["Zainab Ahmed", "Store Manager — Lahore", 1],
        ["Usman Chaudhry", "Warehouse Associate", 4],
        ["Hira Malik", "Accounts Assistant (on leave)", 3],
        ["Imran Rehman", "Former Driver", 4],
      ];
  business.employees = roles.map(([name, title, dept], i) => {
    const status = String(title).includes("on leave")
      ? "on_leave"
      : String(title).startsWith("Former")
        ? "terminated"
        : "active";
    return {
      id: `emp-${prefix}-${i + 1}`,
      full_name: String(name),
      email: `${String(name).toLowerCase().split(" ")[0]}@${services ? "brightline" : "northwind"}.example`,
      phone: null,
      job_title: String(title).replace(" (on leave)", ""),
      department_id: business.departments[Number(dept)]?.id ?? null,
      department_name: business.departments[Number(dept)]?.name ?? null,
      manager_id: i === 0 ? null : `emp-${prefix}-1`,
      employment_type: String(title).includes("Contract")
        ? "contract"
        : String(title).includes("Intern")
          ? "intern"
          : r.chance(0.12)
            ? "part_time"
            : "full_time",
      status,
      hire_date: dateOnly(-r.int(60, 1600)),
      termination_date:
        status === "terminated" ? dateOnly(-r.int(10, 50)) : null,
      salary: services
        ? roundPrice(r, 3000, 9000, 100)
        : roundPrice(r, 55000, 420000, 1000),
      salary_currency: currency,
      sensitive_visible: true,
      created_at: daysAgo(r.int(60, 900)),
    } satisfies Employee;
  });

  // Notes & activities
  for (const customer of business.customers.slice(0, 40)) {
    const orders = business.orders
      .filter((o) => o.customer_id === customer.id)
      .slice(0, 4);
    business.activities.push({
      id: `act-${customer.id}-c`,
      customer_id: customer.id,
      kind: "created",
      summary:
        customer.source === "whatsapp"
          ? "Customer created from WhatsApp"
          : "Customer created",
      ref_type: "customer",
      ref_id: customer.id,
      actor_label: customer.source === "whatsapp" ? "PI" : "Sana Malik",
      created_at: customer.created_at,
    });
    for (const o of orders)
      business.activities.push({
        id: `act-${o.id}`,
        customer_id: customer.id,
        kind: "order",
        summary: `Order ${o.number}: ${o.status}`,
        ref_type: "order",
        ref_id: o.id,
        actor_label: o.created_by_label,
        created_at: o.created_at,
      });
    if (r.chance(0.4)) {
      const body = r.pick([
        "Prefers delivery after 4pm. Call before dispatch.",
        "Asked about wholesale pricing for 20kg monthly — follow up next week.",
        "Loves the Ethiopia roast; notify when new single origins arrive.",
        "Payment usually via bank transfer on the 5th.",
      ]);
      const note = {
        id: `note-${customer.id}`,
        customer_id: customer.id,
        author_label: r.pick(["Sana Malik", "Faisal Iqbal"]),
        body,
        created_at: daysAgo(r.int(1, 30)),
      };
      business.notes.push(note);
      business.activities.push({
        id: `act-${note.id}`,
        customer_id: customer.id,
        kind: "note",
        summary: body.slice(0, 120),
        ref_type: "note",
        ref_id: note.id,
        actor_label: note.author_label,
        created_at: note.created_at,
      });
    }
  }
  return business;
}

export const demoBusiness = demoCollection<DemoBusiness>("business", build);

/** Convenience projections used by demo services. */
export function variantIndex(business: DemoBusiness) {
  const map = new Map<string, { variant: Variant; product: ProductDetail }>();
  for (const product of business.products)
    for (const variant of product.variants)
      map.set(variant.id, { variant, product });
  return map;
}

export type { Quote, Order, Invoice, Lead };
