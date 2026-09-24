/** Quotes and orders: document workflows with controlled transitions. */
import { z } from "zod";
import { apiRequest, ApiError, pageSchema, type Page } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness, mulMoney, nextNumber, sumMoney, taxOf, variantIndex, type DemoBusiness } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import { dateOnly } from "@/demo/random";
import { toCents, centsToString } from "@/lib/format";
import {
  orderDetailSchema,
  orderSchema,
  quoteDetailSchema,
  quoteSchema,
  type ListParams,
  type Order,
  type OrderDetail,
  type OrderLineInput,
  type Quote,
  type QuoteDetail,
  type QuoteLineInput,
} from "@/features/business/types";

export type QuoteAction = "submit" | "approve" | "return_to_draft" | "send" | "accept" | "reject" | "expire" | "cancel";
export type OrderAction = "confirm" | "start_processing" | "ship" | "deliver" | "cancel";

export const QUOTE_ACTIONS: Record<Quote["status"], (QuoteAction | "convert_to_order")[]> = {
  draft: ["submit", "cancel"],
  pending_approval: ["approve", "return_to_draft", "cancel"],
  approved: ["send", "return_to_draft", "cancel"],
  sent: ["accept", "reject", "expire", "cancel"],
  accepted: ["convert_to_order"],
  rejected: [],
  expired: [],
  cancelled: [],
};
export const ORDER_FLOW: Record<Order["status"], OrderAction[]> = {
  draft: ["confirm", "cancel"],
  confirmed: ["start_processing", "cancel"],
  processing: ["ship", "cancel"],
  shipped: ["deliver"],
  delivered: [],
  cancelled: [],
};

export interface DocumentsService {
  quotes(params: ListParams & { customerId?: string }): Promise<Page<Quote>>;
  quote(id: string): Promise<QuoteDetail>;
  createQuote(input: { customer_id: string; valid_until?: string | null; notes: string; lines: QuoteLineInput[] }): Promise<QuoteDetail>;
  updateQuote(id: string, input: { valid_until?: string | null; notes?: string; lines?: QuoteLineInput[] }): Promise<QuoteDetail>;
  quoteAction(id: string, action: QuoteAction): Promise<QuoteDetail>;
  convertQuote(id: string): Promise<Order>;
  orders(params: ListParams & { customerId?: string }): Promise<Page<Order>>;
  order(id: string): Promise<OrderDetail>;
  createOrder(input: { customer_id: string; notes: string; lines: OrderLineInput[] }): Promise<OrderDetail>;
  updateOrderLines(id: string, lines: OrderLineInput[]): Promise<OrderDetail>;
  orderAction(id: string, action: OrderAction): Promise<OrderDetail>;
}

const live: DocumentsService = {
  quotes: ({ page = 1, pageSize = 25, search, status, customerId }) =>
    apiRequest("GET", "/quotes", pageSchema(quoteSchema), { query: { page, page_size: pageSize, search, status, customer_id: customerId } }),
  quote: (id) => apiRequest("GET", `/quotes/${id}`, quoteDetailSchema),
  createQuote: (input) => apiRequest("POST", "/quotes", quoteDetailSchema, { body: input }),
  updateQuote: (id, input) => apiRequest("PATCH", `/quotes/${id}`, quoteDetailSchema, { body: input }),
  quoteAction: (id, action) => apiRequest("POST", `/quotes/${id}/actions`, quoteDetailSchema, { body: { action } }),
  // The conversion endpoint returns the order without display-only customer_name.
  convertQuote: (id) =>
    apiRequest("POST", `/quotes/${id}/order`, orderSchema.extend({ customer_name: z.string().nullable().catch(null) })),
  orders: ({ page = 1, pageSize = 25, search, status, customerId }) =>
    apiRequest("GET", "/orders", pageSchema(orderSchema), { query: { page, page_size: pageSize, search, status, customer_id: customerId } }),
  order: (id) => apiRequest("GET", `/orders/${id}`, orderDetailSchema),
  createOrder: (input) => apiRequest("POST", "/orders", orderDetailSchema, { body: input }),
  updateOrderLines: (id, lines) => apiRequest("PUT", `/orders/${id}/lines`, orderDetailSchema, { body: { lines } }),
  orderAction: (id, action) => apiRequest("POST", `/orders/${id}/actions`, orderDetailSchema, { body: { action } }),
};

/* Demo implementation ----------------------------------------------------------------- */

function rule(code: string, message: string): never {
  throw new ApiError(422, code, undefined, message);
}

function priceDocument(business: DemoBusiness, inputs: QuoteLineInput[], allowCustom: boolean) {
  const index = variantIndex(business);
  const lines = inputs.map((input, i) => {
    let description = input.description ?? "";
    let unit_price = input.unit_price ?? "0.00";
    if (input.variant_id) {
      const entry = index.get(input.variant_id);
      if (!entry || entry.variant.status !== "active" || entry.product.status !== "active") rule("VARIANT_UNAVAILABLE", "This item is not available");
      unit_price = entry.variant.price;
      description ||= `${entry.product.name} — ${entry.variant.name}`;
    } else if (!allowCustom) rule("CUSTOM_PRICE_NOT_ALLOWED", "Custom-priced lines need a team member");
    const gross = mulMoney(unit_price, input.quantity);
    if (toCents(input.discount) > toCents(gross)) rule("INVALID_DISCOUNT", "A discount exceeds its line");
    return { id: demoId("line"), variant_id: input.variant_id ?? null, position: i + 1, description, quantity: input.quantity, unit_price, discount: centsToString(toCents(input.discount)), line_total: sumMoney([gross, `-${input.discount}`]), gross };
  });
  const subtotal = sumMoney(lines.map((l) => l.gross));
  const discount_total = sumMoney(lines.map((l) => l.discount));
  const taxable = sumMoney([subtotal, `-${discount_total}`]);
  const tax_total = taxOf(taxable, business.settings.tax_rate);
  return { lines: lines.map(({ gross: _gross, ...l }) => l), subtotal, discount_total, tax_total, total: sumMoney([taxable, tax_total]) };
}

function requiresApproval(business: DemoBusiness, subtotal: string, discount: string, total: string, source: string) {
  const s = toCents(subtotal);
  const rate = s > BigInt(0) ? Number(toCents(discount)) / Number(s) : 0;
  const threshold = business.settings.quote_approval_threshold;
  return source === "pi" || rate > Number(business.settings.max_discount_rate) || (threshold !== null && toCents(total) > toCents(threshold));
}

function findQuote(id: string) {
  const quote = demoBusiness().quotes.find((q) => q.id === id);
  if (!quote) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return quote;
}

function findOrder(id: string) {
  const order = demoBusiness().orders.find((o) => o.id === id);
  if (!order) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return order;
}

function quoteView(q: QuoteDetail): QuoteDetail {
  return { ...q, lines: q.lines.map((l) => ({ ...l })), next_actions: QUOTE_ACTIONS[q.status].filter((a) => !(a === "convert_to_order" && q.order_id)) };
}

function orderView(o: OrderDetail): OrderDetail {
  return { ...o, lines: o.lines.map((l) => ({ ...l })), next_actions: ORDER_FLOW[o.status] };
}

function applyOrderStock(business: DemoBusiness, order: OrderDetail, direction: -1 | 1) {
  const index = variantIndex(business);
  const main = business.locations.find((l) => l.is_default);
  for (const line of order.lines) {
    if (!line.variant_id) continue;
    const entry = index.get(line.variant_id);
    if (!entry?.variant.track_inventory || !main) continue;
    let row = business.stock.find((s) => s.variant_id === line.variant_id && s.location_id === main.id);
    if (!row) {
      row = { variant_id: line.variant_id, location_id: main.id, on_hand: 0, reserved: 0 };
      business.stock.push(row);
    }
    const next = row.on_hand + direction * line.quantity;
    if (next < row.reserved || next < 0) rule("INSUFFICIENT_STOCK", `Not enough stock for ${entry.variant.sku}`);
  }
  for (const line of order.lines) {
    if (!line.variant_id) continue;
    const entry = index.get(line.variant_id);
    if (!entry?.variant.track_inventory || !main) continue;
    const row = business.stock.find((s) => s.variant_id === line.variant_id && s.location_id === main.id)!;
    row.on_hand += direction * line.quantity;
    business.movements.unshift({ id: demoId("mov"), variant_id: line.variant_id, location_id: main.id, quantity: direction * line.quantity, kind: direction < 0 ? "sale" : "return", reason: direction < 0 ? `Order ${order.number}` : `Cancelled order ${order.number}`, balance_after: row.on_hand, ref_type: "order", ref_id: order.id, actor_label: "Amina Rahman", created_at: new Date().toISOString() });
  }
}

const demo: DocumentsService = {
  async quotes({ page = 1, pageSize = 25, search, status, customerId }) {
    await demoDelay();
    const rows = demoBusiness()
      .quotes.filter((q) => (!status || q.status === status) && (!customerId || q.customer_id === customerId) && (!search || matches(q.number, search) || matches(q.customer_name, search)))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    return paginate(rows.map(({ lines: _l, next_actions: _n, ...q }) => q), page, pageSize);
  },
  async quote(id) {
    await demoDelay();
    return quoteView(findQuote(id));
  },
  async createQuote(input) {
    await demoDelay(400);
    const business = demoBusiness();
    const customer = business.customers.find((c) => c.id === input.customer_id);
    if (!customer) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    const priced = priceDocument(business, input.lines, true);
    const quote: QuoteDetail = {
      id: demoId("quo"), number: nextNumber(business, "quote"), customer_id: customer.id, lead_id: null, status: "draft", source: "manual",
      currency: business.settings.default_currency, subtotal: priced.subtotal, discount_total: priced.discount_total, tax_rate: business.settings.tax_rate,
      tax_total: priced.tax_total, total: priced.total, requires_approval: requiresApproval(business, priced.subtotal, priced.discount_total, priced.total, "manual"),
      valid_until: input.valid_until || dateOnly(business.settings.quote_validity_days), notes: input.notes, approved_at: null, sent_at: null, order_id: null,
      created_at: new Date().toISOString(), customer_name: customer.name, lines: priced.lines, next_actions: [],
    };
    business.quotes.unshift(quote);
    return quoteView(quote);
  },
  async updateQuote(id, input) {
    await demoDelay(300);
    const business = demoBusiness();
    const quote = findQuote(id);
    if (quote.status !== "draft") rule("QUOTE_LOCKED", "Only draft quotes can be edited");
    if (input.notes !== undefined) quote.notes = input.notes;
    if (input.valid_until) quote.valid_until = input.valid_until;
    if (input.lines) {
      const priced = priceDocument(business, input.lines, quote.source === "manual");
      Object.assign(quote, { lines: priced.lines, subtotal: priced.subtotal, discount_total: priced.discount_total, tax_total: priced.tax_total, total: priced.total });
      quote.requires_approval = requiresApproval(business, priced.subtotal, priced.discount_total, priced.total, quote.source);
    }
    return quoteView(quote);
  },
  async quoteAction(id, action) {
    await demoDelay(250);
    const quote = findQuote(id);
    if (!QUOTE_ACTIONS[quote.status].includes(action)) rule("INVALID_TRANSITION", `A quote cannot ${action.replace(/_/g, " ")} from ${quote.status.replace(/_/g, " ")}`);
    const target = ({ submit: quote.requires_approval ? "pending_approval" : "approved", approve: "approved", return_to_draft: "draft", send: "sent", accept: "accepted", reject: "rejected", expire: "expired", cancel: "cancelled" } as const)[action];
    if (action === "send" && quote.valid_until < dateOnly(0)) rule("QUOTE_EXPIRED", "This quote's validity date has passed");
    quote.status = target;
    if (target === "approved") quote.approved_at = new Date().toISOString();
    if (target === "sent") quote.sent_at = new Date().toISOString();
    return quoteView(quote);
  },
  async convertQuote(id) {
    await demoDelay(400);
    const business = demoBusiness();
    const quote = findQuote(id);
    if (quote.status !== "accepted") rule("QUOTE_NOT_ACCEPTED", "Only accepted quotes become orders");
    if (quote.lines.some((l) => Number(l.quantity) % 1 !== 0)) rule("FRACTIONAL_QUANTITY", "Order quantities must be whole units");
    if (quote.order_id) return findOrder(quote.order_id);
    const index = variantIndex(business);
    const orderId = demoId("ord");
    const order: OrderDetail = {
      id: orderId, number: nextNumber(business, "order"), customer_id: quote.customer_id, quote_id: quote.id, status: "draft", source: "quote",
      currency: quote.currency, subtotal: quote.subtotal, discount_total: quote.discount_total, tax_rate: quote.tax_rate, tax_total: quote.tax_total, total: quote.total,
      notes: quote.notes, confirmed_at: null, cancelled_at: null, created_by_label: "Amina Rahman", created_at: new Date().toISOString(), customer_name: quote.customer_name,
      lines: quote.lines.map((l) => ({ ...l, id: demoId("line"), quantity: Number(l.quantity), sku: l.variant_id ? (index.get(l.variant_id)?.variant.sku ?? null) : null })),
      next_actions: [], invoice_id: null, invoice_number: null,
    };
    business.orders.unshift(order);
    quote.order_id = orderId;
    return order;
  },
  async orders({ page = 1, pageSize = 25, search, status, customerId }) {
    await demoDelay();
    const rows = demoBusiness()
      .orders.filter((o) => (!status || o.status === status) && (!customerId || o.customer_id === customerId) && (!search || matches(o.number, search) || matches(o.customer_name, search)))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    return paginate(rows.map(({ lines: _l, next_actions: _n, invoice_id: _i, invoice_number: _in, ...o }) => o), page, pageSize);
  },
  async order(id) {
    await demoDelay();
    return orderView(findOrder(id));
  },
  async createOrder(input) {
    await demoDelay(400);
    const business = demoBusiness();
    const customer = business.customers.find((c) => c.id === input.customer_id);
    if (!customer) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    const index = variantIndex(business);
    const priced = priceDocument(business, input.lines.map((l) => ({ variant_id: l.variant_id, quantity: String(l.quantity), discount: l.discount })), false);
    const order: OrderDetail = {
      id: demoId("ord"), number: nextNumber(business, "order"), customer_id: customer.id, quote_id: null, status: "draft", source: "manual",
      currency: business.settings.default_currency, subtotal: priced.subtotal, discount_total: priced.discount_total, tax_rate: business.settings.tax_rate,
      tax_total: priced.tax_total, total: priced.total, notes: input.notes, confirmed_at: null, cancelled_at: null, created_by_label: "Amina Rahman",
      created_at: new Date().toISOString(), customer_name: customer.name,
      lines: priced.lines.map((l) => ({ ...l, quantity: Number(l.quantity), sku: l.variant_id ? (index.get(l.variant_id)?.variant.sku ?? null) : null })),
      next_actions: [], invoice_id: null, invoice_number: null,
    };
    business.orders.unshift(order);
    return orderView(order);
  },
  async updateOrderLines(id, lines) {
    await demoDelay(300);
    const business = demoBusiness();
    const order = findOrder(id);
    if (order.status !== "draft") rule("ORDER_LOCKED", "Only draft orders can be edited");
    const index = variantIndex(business);
    const priced = priceDocument(business, lines.map((l) => ({ variant_id: l.variant_id, quantity: String(l.quantity), discount: l.discount })), false);
    Object.assign(order, { subtotal: priced.subtotal, discount_total: priced.discount_total, tax_total: priced.tax_total, total: priced.total, lines: priced.lines.map((l) => ({ ...l, quantity: Number(l.quantity), sku: l.variant_id ? (index.get(l.variant_id)?.variant.sku ?? null) : null })) });
    return orderView(order);
  },
  async orderAction(id, action) {
    await demoDelay(350);
    const business = demoBusiness();
    const order = findOrder(id);
    if (!ORDER_FLOW[order.status].includes(action)) rule("INVALID_TRANSITION", `An order cannot ${action.replace(/_/g, " ")} from ${order.status}`);
    const previous = order.status;
    if (action === "confirm") {
      applyOrderStock(business, order, -1);
      order.confirmed_at = new Date().toISOString();
      if (business.settings.auto_invoice_on_order_confirm) {
        const invoiceId = demoId("inv");
        const issued = dateOnly(0);
        business.invoices.unshift({
          id: invoiceId, number: nextNumber(business, "invoice"), customer_id: order.customer_id, order_id: order.id, status: "issued", issue_date: issued,
          due_date: dateOnly(business.settings.invoice_due_days), currency: order.currency, subtotal: order.subtotal, discount_total: order.discount_total,
          tax_total: order.tax_total, total: order.total, amount_paid: "0.00", notes: "", created_at: new Date().toISOString(), customer_name: order.customer_name,
          balance_due: order.total, is_overdue: false, lines: order.lines.map((l) => ({ ...l, quantity: String(l.quantity) })), payments: [], next_actions: [],
        });
        order.invoice_id = invoiceId;
        order.invoice_number = business.invoices[0]!.number;
      }
    }
    if (action === "cancel") {
      const invoice = business.invoices.find((i) => i.order_id === order.id && i.status !== "void");
      if (invoice && toCents(invoice.amount_paid) > BigInt(0)) rule("INVOICE_HAS_PAYMENTS", "Paid invoices cannot be voided");
      if (previous !== "draft") applyOrderStock(business, order, 1);
      if (invoice) invoice.status = "void";
      order.cancelled_at = new Date().toISOString();
    }
    order.status = ({ confirm: "confirmed", start_processing: "processing", ship: "shipped", deliver: "delivered", cancel: "cancelled" } as const)[action];
    return orderView(order);
  },
};

export const documentsService = select<DocumentsService>({ demo, live });
