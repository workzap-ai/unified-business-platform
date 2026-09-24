import { apiRequest, ApiError, pageSchema, type Page } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness, mulMoney, nextNumber, sumMoney, taxOf } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import { dateOnly } from "@/demo/random";
import { toCents, centsToString } from "@/lib/format";
import {
  billingSummarySchema,
  invoiceDetailSchema,
  invoiceSchema,
  paymentSchema,
  type BillingSummary,
  type Invoice,
  type InvoiceDetail,
  type InvoiceInput,
  type ListParams,
  type Payment,
  type PaymentInput,
} from "@/features/business/types";

export interface BillingService {
  summary(): Promise<BillingSummary>;
  invoices(params: ListParams & { customerId?: string; overdue?: boolean }): Promise<Page<Invoice>>;
  invoice(id: string): Promise<InvoiceDetail>;
  createInvoice(input: InvoiceInput): Promise<InvoiceDetail>;
  invoiceAction(id: string, action: "issue" | "void"): Promise<InvoiceDetail>;
  recordPayment(invoiceId: string, input: PaymentInput): Promise<Payment>;
  payments(params: { page?: number; pageSize?: number }): Promise<Page<Payment & { invoice_number?: string; customer_name?: string | null }>>;
}

const live: BillingService = {
  summary: () => apiRequest("GET", "/billing/summary", billingSummarySchema),
  invoices: ({ page = 1, pageSize = 25, search, status, customerId, overdue }) =>
    apiRequest("GET", "/billing/invoices", pageSchema(invoiceSchema), {
      query: { page, page_size: pageSize, search, status, customer_id: customerId, overdue: overdue || undefined },
    }),
  invoice: (id) => apiRequest("GET", `/billing/invoices/${id}`, invoiceDetailSchema),
  createInvoice: (input) => apiRequest("POST", "/billing/invoices", invoiceDetailSchema, { body: input }),
  invoiceAction: (id, action) => apiRequest("POST", `/billing/invoices/${id}/actions`, invoiceDetailSchema, { body: { action } }),
  recordPayment: (id, input) => apiRequest("POST", `/billing/invoices/${id}/payments`, paymentSchema, { body: input }),
  payments: ({ page = 1, pageSize = 25 }) =>
    apiRequest("GET", "/billing/payments", pageSchema(paymentSchema), { query: { page, page_size: pageSize } }),
};

function rule(code: string, message: string): never {
  throw new ApiError(422, code, undefined, message);
}

function view(invoice: InvoiceDetail): InvoiceDetail {
  const overdue = ["issued", "partially_paid"].includes(invoice.status) && !!invoice.due_date && invoice.due_date < dateOnly(0);
  const actions =
    invoice.status === "draft" ? ["issue", "void"] :
    invoice.status === "issued" ? (toCents(invoice.amount_paid) > BigInt(0) ? ["record_payment"] : ["record_payment", "void"]) :
    invoice.status === "partially_paid" ? ["record_payment"] : [];
  return { ...invoice, is_overdue: overdue, balance_due: sumMoney([invoice.total, `-${invoice.amount_paid}`]), next_actions: actions, lines: [...invoice.lines], payments: [...invoice.payments] };
}

function find(id: string) {
  const invoice = demoBusiness().invoices.find((i) => i.id === id);
  if (!invoice) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return invoice;
}

const demo: BillingService = {
  async summary() {
    await demoDelay();
    const business = demoBusiness();
    const open = business.invoices.filter((i) => ["issued", "partially_paid"].includes(i.status)).map(view);
    const overdue = open.filter((i) => i.is_overdue);
    const monthStart = dateOnly(0).slice(0, 8) + "01";
    const collected = business.invoices.flatMap((i) => i.payments).filter((p) => p.received_on >= monthStart);
    return {
      currency: business.settings.default_currency,
      outstanding: sumMoney(open.map((i) => i.balance_due)),
      overdue: sumMoney(overdue.map((i) => i.balance_due)),
      overdue_count: overdue.length,
      collected_this_month: sumMoney(collected.map((p) => p.amount)),
      draft_count: business.invoices.filter((i) => i.status === "draft").length,
    };
  },
  async invoices({ page = 1, pageSize = 25, search, status, customerId, overdue }) {
    await demoDelay();
    const rows = demoBusiness()
      .invoices.map(view)
      .filter((i) => (!status || i.status === status) && (!customerId || i.customer_id === customerId) && (!overdue || i.is_overdue) && (!search || matches(i.number, search) || matches(i.customer_name, search)))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    return paginate(rows.map(({ lines: _l, payments: _p, next_actions: _n, ...i }) => i), page, pageSize);
  },
  async invoice(id) {
    await demoDelay();
    return view(find(id));
  },
  async createInvoice(input) {
    await demoDelay(350);
    const business = demoBusiness();
    const customer = business.customers.find((c) => c.id === input.customer_id);
    if (!customer) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    const lines = input.lines.map((l, i) => {
      const gross = mulMoney(l.unit_price, l.quantity);
      if (toCents(l.discount) > toCents(gross)) rule("INVALID_DISCOUNT", "A discount exceeds its line");
      return { id: demoId("line"), variant_id: null, position: i + 1, description: l.description, quantity: l.quantity, unit_price: l.unit_price, discount: l.discount, line_total: sumMoney([gross, `-${l.discount}`]), gross };
    });
    const subtotal = sumMoney(lines.map((l) => l.gross));
    const discount_total = sumMoney(lines.map((l) => l.discount));
    const taxable = sumMoney([subtotal, `-${discount_total}`]);
    const tax_total = taxOf(taxable, business.settings.tax_rate);
    const total = sumMoney([taxable, tax_total]);
    const invoice: InvoiceDetail = {
      id: demoId("inv"), number: nextNumber(business, "invoice"), customer_id: customer.id, order_id: null, status: "draft", issue_date: null,
      due_date: input.due_date ?? null, currency: business.settings.default_currency, subtotal, discount_total, tax_total, total, amount_paid: "0.00",
      notes: input.notes, created_at: new Date().toISOString(), customer_name: customer.name, balance_due: total, is_overdue: false,
      lines: lines.map(({ gross: _g, ...l }) => l), payments: [], next_actions: [],
    };
    business.invoices.unshift(invoice);
    return view(invoice);
  },
  async invoiceAction(id, action) {
    await demoDelay(250);
    const invoice = find(id);
    if (action === "issue") {
      if (invoice.status !== "draft") rule("INVALID_TRANSITION", "Only drafts can be issued");
      invoice.status = "issued";
      invoice.issue_date = dateOnly(0);
      invoice.due_date ??= dateOnly(demoBusiness().settings.invoice_due_days);
    } else {
      if (toCents(invoice.amount_paid) > BigInt(0)) rule("INVOICE_HAS_PAYMENTS", "Paid invoices cannot be voided");
      if (!["draft", "issued"].includes(invoice.status)) rule("INVALID_TRANSITION", `An invoice cannot move from ${invoice.status} to void`);
      invoice.status = "void";
    }
    return view(invoice);
  },
  async recordPayment(invoiceId, input) {
    await demoDelay(300);
    const business = demoBusiness();
    const invoice = find(invoiceId);
    if (!["issued", "partially_paid"].includes(invoice.status)) rule("INVOICE_NOT_OPEN", "Payments need an issued invoice");
    const balance = toCents(invoice.total) - toCents(invoice.amount_paid);
    const amount = toCents(input.amount);
    if (amount <= BigInt(0)) rule("INVALID_AMOUNT", "Enter an amount greater than zero");
    if (amount > balance) rule("OVERPAYMENT", "Payment exceeds the balance due");
    const payment: Payment = {
      id: demoId("pay"), invoice_id: invoice.id, number: nextNumber(business, "payment"), amount: centsToString(amount), currency: invoice.currency,
      method: input.method, received_on: input.received_on || dateOnly(0), reference: input.reference, recorded_by_label: "Amina Rahman", created_at: new Date().toISOString(),
    };
    invoice.payments.push(payment);
    invoice.amount_paid = centsToString(toCents(invoice.amount_paid) + amount);
    invoice.status = toCents(invoice.amount_paid) === toCents(invoice.total) ? "paid" : "partially_paid";
    return payment;
  },
  async payments({ page = 1, pageSize = 25 }) {
    await demoDelay();
    const rows = demoBusiness()
      .invoices.flatMap((i) => i.payments.map((p) => ({ ...p, invoice_number: i.number, customer_name: i.customer_name })))
      .sort((a, b) => b.received_on.localeCompare(a.received_on));
    return paginate(rows, page, pageSize);
  },
};

export const billingService = select<BillingService>({ demo, live });
