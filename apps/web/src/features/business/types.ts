/**
 * Contracts for core business modules. Each schema mirrors the corresponding backend
 * response model (apps/api/app/modules/<module>/schemas.py). Money and quantities
 * arrive as decimal strings and stay strings in the UI.
 */
import { z } from "zod";
import { decimal } from "@/services/api-client";

const id = z.string();
const ts = z.string();
const nullableDecimal = decimal.nullable();

/* Customers ------------------------------------------------------------------ */
export const customerSchema = z.object({
  id,
  name: z.string(),
  email: z.string().nullable(),
  phone: z.string().nullable(),
  company: z.string().nullable(),
  status: z.enum(["active", "archived"]),
  source: z.enum(["manual", "whatsapp", "import"]),
  tags: z.array(z.string()),
  last_contacted_at: ts.nullable(),
  created_at: ts,
});
export const customerDetailSchema = customerSchema.extend({
  summary: z.object({
    order_count: z.number(),
    open_quote_count: z.number(),
    outstanding_balance: nullableDecimal,
    currency: z.string().nullable(),
    open_conversations: z.number(),
  }),
});
export const noteSchema = z.object({
  id,
  author_label: z.string(),
  body: z.string(),
  created_at: ts,
});
export const activitySchema = z.object({
  id,
  kind: z.string(),
  summary: z.string(),
  ref_type: z.string().nullable(),
  ref_id: z.string().nullable(),
  actor_label: z.string(),
  created_at: ts,
});
export type Customer = z.infer<typeof customerSchema>;
export type CustomerDetail = z.infer<typeof customerDetailSchema>;
export type CustomerNote = z.infer<typeof noteSchema>;
export type CustomerActivity = z.infer<typeof activitySchema>;
export type CustomerInput = {
  name: string;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  tags: string[];
};

/* Catalog -------------------------------------------------------------------- */
export const categorySchema = z.object({
  id,
  name: z.string(),
  slug: z.string(),
  description: z.string(),
});
export const variantSchema = z.object({
  id,
  product_id: id,
  sku: z.string(),
  name: z.string(),
  price: decimal,
  currency: z.string(),
  status: z.enum(["active", "inactive"]),
  track_inventory: z.boolean(),
  low_stock_threshold: z.number().nullable(),
  attributes: z.record(z.string(), z.unknown()),
});
const productBase = z.object({
  offering_type: z.enum(["service", "product", "hybrid", "package"]),
  id,
  name: z.string(),
  description: z.string(),
  category_id: id.nullable(),
  status: z.enum(["active", "inactive"]),
  pi_visible: z.boolean(),
  attributes: z.record(z.string(), z.unknown()),
  created_at: ts,
});
export const productListItemSchema = productBase.extend({
  category_name: z.string().nullable(),
  variant_count: z.number(),
  min_price: nullableDecimal,
  max_price: nullableDecimal,
  currency: z.string().nullable(),
});
export const productDetailSchema = productBase.extend({
  category_name: z.string().nullable(),
  variants: z.array(variantSchema),
});
export type Category = z.infer<typeof categorySchema>;
export type Variant = z.infer<typeof variantSchema>;
export type ProductListItem = z.infer<typeof productListItemSchema>;
export type ProductDetail = z.infer<typeof productDetailSchema>;
export type VariantInput = {
  sku: string;
  name: string;
  price: string;
  currency: string;
  track_inventory: boolean;
  low_stock_threshold: number | null;
};
export type ProductInput = {
  offering_type: "service" | "product" | "hybrid" | "package";
  name: string;
  description: string;
  category_id: string | null;
  pi_visible: boolean;
  variants: VariantInput[];
};

/* Inventory ------------------------------------------------------------------ */
export const locationSchema = z.object({
  id,
  name: z.string(),
  code: z.string(),
  branch_id: id.nullable(),
  is_default: z.boolean(),
  status: z.enum(["active", "inactive"]),
});
export const stockLevelSchema = z.object({
  variant_id: id,
  product_id: id,
  product_name: z.string(),
  variant_name: z.string(),
  sku: z.string(),
  location_id: id,
  location_name: z.string(),
  on_hand: z.number(),
  reserved: z.number(),
  available: z.number(),
  low_stock_threshold: z.number().nullable(),
  is_low: z.boolean(),
});
export const movementSchema = z.object({
  id,
  variant_id: id,
  location_id: id,
  quantity: z.number(),
  kind: z.enum([
    "receipt",
    "adjustment",
    "sale",
    "return",
    "transfer_in",
    "transfer_out",
  ]),
  reason: z.string(),
  balance_after: z.number(),
  ref_type: z.string().nullable(),
  ref_id: id.nullable(),
  actor_label: z.string(),
  created_at: ts,
});
export type Location = z.infer<typeof locationSchema>;
export type StockLevel = z.infer<typeof stockLevelSchema>;
export type Movement = z.infer<typeof movementSchema>;
export type AdjustmentInput = {
  variant_id: string;
  location_id: string | null;
  quantity: number;
  kind: "receipt" | "adjustment" | "return";
  reason: string;
};

/* Sales ------------------------------------------------------------------------ */
export const leadSchema = z.object({
  id,
  customer_id: id.nullable(),
  title: z.string(),
  stage: z.enum(["new", "qualified", "proposal", "won", "lost"]),
  source: z.enum(["manual", "pi", "website", "referral"]),
  estimated_value: nullableDecimal,
  currency: z.string(),
  requirements: z.record(z.string(), z.unknown()),
  missing_information: z.array(z.string()),
  notes: z.string(),
  conversation_id: id.nullable(),
  closed_at: ts.nullable(),
  created_at: ts,
  updated_at: ts,
  customer_name: z.string().nullable(),
  next_stages: z.array(z.string()),
});
export const pipelineStageSchema = z.object({
  stage: z.string(),
  count: z.number(),
  value: decimal,
});
export type Lead = z.infer<typeof leadSchema>;
export type LeadStage = Lead["stage"];
export type PipelineStage = z.infer<typeof pipelineStageSchema>;

/* Documents: quotes, orders, invoices --------------------------------------------- */
const lineBase = {
  id,
  variant_id: id.nullable(),
  position: z.number(),
  description: z.string(),
  unit_price: decimal,
  discount: decimal,
  line_total: decimal,
};
const totals = {
  currency: z.string(),
  subtotal: decimal,
  discount_total: decimal,
  tax_total: decimal,
  total: decimal,
};

export const quoteSchema = z.object({
  id,
  number: z.string(),
  customer_id: id,
  lead_id: id.nullable(),
  status: z.enum([
    "draft",
    "pending_approval",
    "approved",
    "sent",
    "accepted",
    "rejected",
    "expired",
    "cancelled",
  ]),
  source: z.enum(["manual", "pi"]),
  ...totals,
  tax_rate: decimal,
  requires_approval: z.boolean(),
  valid_until: z.string(),
  notes: z.string(),
  approved_at: ts.nullable(),
  sent_at: ts.nullable(),
  order_id: id.nullable(),
  created_at: ts,
  customer_name: z.string().nullable(),
});
export const quoteDetailSchema = quoteSchema.extend({
  lines: z.array(z.object({ ...lineBase, quantity: decimal })),
  next_actions: z.array(z.string()),
});
export type Quote = z.infer<typeof quoteSchema>;
export type QuoteDetail = z.infer<typeof quoteDetailSchema>;
export type QuoteLineInput = {
  variant_id?: string | null;
  description?: string | null;
  quantity: string;
  unit_price?: string | null;
  discount: string;
};

export const orderSchema = z.object({
  fulfillment_type: z.enum(["service", "product", "hybrid"]),
  id,
  number: z.string(),
  customer_id: id,
  quote_id: id.nullable(),
  status: z.enum([
    "draft",
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
  ]),
  source: z.enum(["manual", "pi", "quote"]),
  ...totals,
  tax_rate: decimal,
  notes: z.string(),
  confirmed_at: ts.nullable(),
  cancelled_at: ts.nullable(),
  created_by_label: z.string(),
  created_at: ts,
  customer_name: z.string().nullable(),
});
export const orderDetailSchema = orderSchema.extend({
  lines: z.array(
    z.object({ ...lineBase, sku: z.string().nullable(), quantity: z.number() }),
  ),
  next_actions: z.array(z.string()),
  invoice_id: id.nullable(),
  invoice_number: z.string().nullable(),
});
export type Order = z.infer<typeof orderSchema>;
export type OrderDetail = z.infer<typeof orderDetailSchema>;
export type OrderStatus = Order["status"];
export type OrderLineInput = {
  variant_id: string;
  quantity: number;
  discount: string;
};

export const paymentSchema = z.object({
  id,
  invoice_id: id,
  number: z.string(),
  amount: decimal,
  currency: z.string(),
  method: z.enum(["cash", "bank_transfer", "card", "mobile_wallet", "other"]),
  received_on: z.string(),
  reference: z.string(),
  recorded_by_label: z.string(),
  created_at: ts,
});
export const invoiceSchema = z.object({
  id,
  number: z.string(),
  customer_id: id,
  order_id: id.nullable(),
  status: z.enum(["draft", "issued", "partially_paid", "paid", "void"]),
  issue_date: z.string().nullable(),
  due_date: z.string().nullable(),
  ...totals,
  amount_paid: decimal,
  notes: z.string(),
  created_at: ts,
  customer_name: z.string().nullable(),
  balance_due: decimal,
  is_overdue: z.boolean(),
});
export const invoiceDetailSchema = invoiceSchema.extend({
  lines: z.array(z.object({ ...lineBase, quantity: decimal })),
  payments: z.array(paymentSchema),
  next_actions: z.array(z.string()),
});
export const billingSummarySchema = z.object({
  currency: z.string(),
  outstanding: decimal,
  overdue: decimal,
  overdue_count: z.number(),
  collected_this_month: decimal,
  draft_count: z.number(),
});
export type Payment = z.infer<typeof paymentSchema>;
export type Invoice = z.infer<typeof invoiceSchema>;
export type InvoiceDetail = z.infer<typeof invoiceDetailSchema>;
export type BillingSummary = z.infer<typeof billingSummarySchema>;
export type PaymentInput = {
  amount: string;
  method: Payment["method"];
  received_on?: string;
  reference: string;
};
export type InvoiceInput = {
  customer_id: string;
  due_date?: string | null;
  notes: string;
  lines: {
    description: string;
    quantity: string;
    unit_price: string;
    discount: string;
  }[];
};

/* Finance --------------------------------------------------------------------------- */
export const EXPENSE_CATEGORIES = [
  "rent",
  "payroll",
  "utilities",
  "inventory",
  "marketing",
  "software",
  "travel",
  "taxes",
  "professional_services",
  "other",
] as const;
export const expenseSchema = z.object({
  id,
  number: z.string(),
  category: z.enum(EXPENSE_CATEGORIES),
  description: z.string(),
  vendor: z.string(),
  amount: decimal,
  currency: z.string(),
  incurred_on: z.string(),
  status: z.enum(["recorded", "void"]),
  recorded_by_label: z.string(),
  created_at: ts,
});
export const financeSummarySchema = z.object({
  currency: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  cash_in: decimal,
  cash_out: decimal,
  net_cash: decimal,
  receivables: decimal,
  aging: z.array(
    z.object({ bucket: z.string(), amount: decimal, count: z.number() }),
  ),
  expenses_by_category: z.array(
    z.object({ category: z.string(), amount: decimal }),
  ),
});
export type Expense = z.infer<typeof expenseSchema>;
export type FinanceSummary = z.infer<typeof financeSummarySchema>;
export type ExpenseInput = {
  category: Expense["category"];
  description: string;
  vendor: string;
  amount: string;
  incurred_on: string;
};

/* HR ----------------------------------------------------------------------------------- */
export const employeeSchema = z.object({
  id,
  full_name: z.string(),
  email: z.string().nullable(),
  phone: z.string().nullable(),
  job_title: z.string(),
  department_id: id.nullable(),
  department_name: z.string().nullable(),
  manager_id: id.nullable(),
  employment_type: z.enum(["full_time", "part_time", "contract", "intern"]),
  status: z.enum(["active", "on_leave", "terminated"]),
  hire_date: z.string(),
  termination_date: z.string().nullable(),
  salary: nullableDecimal.optional(),
  salary_currency: z.string().nullable().optional(),
  gender: z.enum(["male", "female"]).nullable().optional(),
  work_arrangement: z
    .enum(["onsite", "hybrid", "remote", "freelancer"])
    .nullable()
    .optional(),
  date_of_birth: z.string().nullable().optional(),
  has_personal_details: z.boolean().optional(),
  sensitive_visible: z.boolean(),
  created_at: ts,
});
export const headcountSchema = z.object({
  total: z.number(),
  active: z.number(),
  on_leave: z.number(),
  terminated: z.number(),
  by_department: z.array(z.tuple([z.string(), z.number()])),
});
export type Employee = z.infer<typeof employeeSchema>;
export type Headcount = z.infer<typeof headcountSchema>;
export type EmployeeInput = {
  full_name: string;
  job_title: string;
  employment_type: Employee["employment_type"];
  hire_date: string;
  email?: string | null;
  phone?: string | null;
  department_id?: string | null;
  manager_id?: string | null;
  salary?: string | null;
  salary_currency?: string | null;
  status?: Employee["status"];
};

/* Organization ---------------------------------------------------------------------------- */
export const departmentSchema = z.object({
  id,
  tenant_id: id,
  name: z.string(),
  code: z.string(),
  branch_id: id.nullable(),
});
export const branchSchema = z.object({
  id,
  tenant_id: id,
  name: z.string(),
  code: z.string(),
});
export type Department = z.infer<typeof departmentSchema>;
export type Branch = z.infer<typeof branchSchema>;

/* Settings -------------------------------------------------------------------------------- */
export const businessSettingsSchema = z.object({
  business_type: z.enum([
    "service_business",
    "product_business",
    "hybrid_business",
  ]),
  default_currency: z.string(),
  tax_rate: decimal,
  auto_invoice_on_order_confirm: z.boolean(),
  low_stock_threshold: z.number(),
  invoice_due_days: z.number(),
  quote_validity_days: z.number(),
  quote_approval_threshold: nullableDecimal,
  max_discount_rate: decimal,
});
export type BusinessSettings = z.infer<typeof businessSettingsSchema>;

/* Overview & reports -------------------------------------------------------------------- */
const metric = z
  .object({
    value: z.union([z.number(), z.string()]),
    previous: z.union([z.number(), z.string()]).nullable().optional(),
    currency: z.string().nullable().optional(),
    detail: z.string().nullable().optional(),
  })
  .nullable();
export const overviewSchema = z.object({
  currency: z.string(),
  revenue: metric,
  orders: metric,
  customers: metric,
  pending_payments: metric,
  outstanding_invoices: metric,
  inventory_alerts: metric,
  quotes: metric,
  employees: metric,
  installed_products: z.array(
    z.object({ key: z.string(), name: z.string(), enabled: z.boolean() }),
  ),
  recent_activity: z.array(
    z.object({
      id,
      action: z.string(),
      actor_label: z.string(),
      entity_type: z.string().nullable(),
      entity_id: id.nullable(),
      created_at: ts,
    }),
  ),
});
export type Overview = z.infer<typeof overviewSchema>;
export type Metric = NonNullable<Overview["revenue"]>;

export const revenueReportSchema = z.object({
  currency: z.string(),
  months: z.array(
    z.object({ month: z.string(), invoiced: decimal, collected: decimal }),
  ),
  total_invoiced: decimal,
  total_collected: decimal,
});
const statusCount = z.object({
  status: z.string(),
  count: z.number(),
  value: decimal,
});
export const ordersReportSchema = z.object({
  currency: z.string(),
  by_status: z.array(statusCount),
  by_day: z.array(
    z.object({ day: z.string(), count: z.number(), value: decimal }),
  ),
  average_order_value: decimal,
});
export const customersReportSchema = z.object({
  currency: z.string(),
  total: z.number(),
  new_by_month: z.array(z.tuple([z.string(), z.number()])),
  top: z.array(
    z.object({
      customer_id: id,
      name: z.string(),
      invoiced: decimal,
      orders: z.number(),
    }),
  ),
});
export const quotesReportSchema = z.object({
  currency: z.string(),
  by_status: z.array(statusCount),
  conversion_rate: nullableDecimal,
  open_value: decimal,
});
export const inventoryReportSchema = z.object({
  low_stock_count: z.number(),
  stock_value: decimal,
  currency: z.string(),
});
export type RevenueReport = z.infer<typeof revenueReportSchema>;
export type OrdersReport = z.infer<typeof ordersReportSchema>;
export type CustomersReport = z.infer<typeof customersReportSchema>;
export type QuotesReport = z.infer<typeof quotesReportSchema>;
export type InventoryReport = z.infer<typeof inventoryReportSchema>;

export type ListParams = {
  page?: number;
  pageSize?: number;
  search?: string;
  status?: string;
  [key: string]: string | number | boolean | undefined;
};
