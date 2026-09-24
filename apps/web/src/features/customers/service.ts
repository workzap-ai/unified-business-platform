import { apiRequest, ApiError, DemoError, pageSchema, type Page } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import { toCents, centsToString } from "@/lib/format";
import {
  activitySchema,
  customerDetailSchema,
  customerSchema,
  noteSchema,
  type Customer,
  type CustomerActivity,
  type CustomerDetail,
  type CustomerInput,
  type CustomerNote,
  type ListParams,
} from "@/features/business/types";

export interface CustomersService {
  list(params: ListParams & { tag?: string }): Promise<Page<Customer>>;
  get(id: string): Promise<CustomerDetail>;
  create(input: CustomerInput): Promise<Customer>;
  update(id: string, input: Partial<CustomerInput>): Promise<Customer>;
  setStatus(id: string, status: Customer["status"]): Promise<Customer>;
  notes(id: string, page?: number): Promise<Page<CustomerNote>>;
  addNote(id: string, body: string): Promise<CustomerNote>;
  activities(id: string, page?: number): Promise<Page<CustomerActivity>>;
}

const live: CustomersService = {
  list: ({ page = 1, pageSize = 25, search, status, tag }) =>
    apiRequest("GET", "/customers", pageSchema(customerSchema), {
      query: { page, page_size: pageSize, search, status, tag },
    }),
  get: (id) => apiRequest("GET", `/customers/${id}`, customerDetailSchema),
  create: (input) => apiRequest("POST", "/customers", customerSchema, { body: input }),
  update: (id, input) => apiRequest("PATCH", `/customers/${id}`, customerSchema, { body: input }),
  setStatus: (id, status) =>
    apiRequest("PUT", `/customers/${id}/status`, customerSchema, { body: { status } }),
  notes: (id, page = 1) =>
    apiRequest("GET", `/customers/${id}/notes`, pageSchema(noteSchema), { query: { page, page_size: 50 } }),
  addNote: (id, body) => apiRequest("POST", `/customers/${id}/notes`, noteSchema, { body: { body } }),
  activities: (id, page = 1) =>
    apiRequest("GET", `/customers/${id}/activities`, pageSchema(activitySchema), {
      query: { page, page_size: 50 },
    }),
};

function find(id: string) {
  const customer = demoBusiness().customers.find((c) => c.id === id);
  if (!customer) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return customer;
}

function assertUniquePhone(phone: string | null | undefined, exceptId?: string) {
  if (phone && demoBusiness().customers.some((c) => c.phone === phone && c.id !== exceptId)) {
    throw new ApiError(409, "RESOURCE_CONFLICT", undefined, "A customer with this phone number already exists");
  }
}

function log(customerId: string, kind: string, summary: string) {
  demoBusiness().activities.unshift({
    id: demoId("act"),
    customer_id: customerId,
    kind,
    summary,
    ref_type: null,
    ref_id: null,
    actor_label: "Amina Rahman",
    created_at: new Date().toISOString(),
  });
}

const demo: CustomersService = {
  async list({ page = 1, pageSize = 25, search, status, tag }) {
    await demoDelay();
    const rows = demoBusiness().customers.filter(
      (c) =>
        (!status || c.status === status) &&
        (!tag || c.tags.includes(tag)) &&
        (!search || [c.name, c.email, c.phone, c.company].some((v) => matches(v, search))),
    );
    return paginate(rows, page, pageSize);
  },
  async get(id) {
    await demoDelay();
    const business = demoBusiness();
    const customer = find(id);
    const balance = business.invoices
      .filter((i) => i.customer_id === id && ["issued", "partially_paid"].includes(i.status))
      .reduce((sum, i) => sum + toCents(i.balance_due), BigInt(0));
    const { demoPi } = await import("@/features/pi/demo-data");
    return {
      ...customer,
      summary: {
        order_count: business.orders.filter((o) => o.customer_id === id && o.status !== "cancelled").length,
        open_quote_count: business.quotes.filter((q) => q.customer_id === id && ["draft", "pending_approval", "approved", "sent"].includes(q.status)).length,
        outstanding_balance: centsToString(balance),
        currency: business.settings.default_currency,
        open_conversations: demoPi().conversations.filter((c) => c.customer_id === id && c.status === "open").length,
      },
    };
  },
  async create(input) {
    await demoDelay(300);
    assertUniquePhone(input.phone);
    const customer: Customer = {
      id: demoId("cus"),
      name: input.name,
      email: input.email || null,
      phone: input.phone || null,
      company: input.company || null,
      status: "active",
      source: "manual",
      tags: [...new Set(input.tags)].sort(),
      last_contacted_at: null,
      created_at: new Date().toISOString(),
    };
    demoBusiness().customers.unshift(customer);
    log(customer.id, "created", "Customer created");
    return customer;
  },
  async update(id, input) {
    await demoDelay(250);
    const customer = find(id);
    if (input.phone !== undefined) assertUniquePhone(input.phone, id);
    Object.assign(customer, {
      ...(input.name !== undefined && { name: input.name }),
      ...(input.email !== undefined && { email: input.email || null }),
      ...(input.phone !== undefined && { phone: input.phone || null }),
      ...(input.company !== undefined && { company: input.company || null }),
      ...(input.tags !== undefined && { tags: [...new Set(input.tags)].sort() }),
    });
    log(id, "updated", "Customer details updated");
    return { ...customer };
  },
  async setStatus(id, status) {
    await demoDelay(200);
    const customer = find(id);
    customer.status = status;
    return { ...customer };
  },
  async notes(id) {
    await demoDelay();
    find(id);
    return paginate(demoBusiness().notes.filter((n) => n.customer_id === id), 1, 50);
  },
  async addNote(id, body) {
    await demoDelay(200);
    find(id);
    if (!body.trim()) throw new DemoError("Write a note first.");
    const note = { id: demoId("note"), customer_id: id, author_label: "Amina Rahman", body, created_at: new Date().toISOString() };
    demoBusiness().notes.unshift(note);
    log(id, "note", body.slice(0, 120));
    return note;
  },
  async activities(id) {
    await demoDelay();
    find(id);
    const rows = demoBusiness()
      .activities.filter((a) => a.customer_id === id)
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    return paginate(rows, 1, 50);
  },
};

export const customersService = select<CustomersService>({ demo, live });
