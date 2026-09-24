import {
  apiRequest,
  ApiError,
  pageSchema,
  type Page,
} from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness, nextNumber, sumMoney } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import { dateOnly } from "@/demo/random";
import {
  expenseSchema,
  financeSummarySchema,
  type Expense,
  type ExpenseInput,
  type FinanceSummary,
  type ListParams,
} from "@/features/business/types";

export interface FinanceService {
  summary(start: string, end: string): Promise<FinanceSummary>;
  expenses(params: ListParams & { category?: string }): Promise<Page<Expense>>;
  createExpense(input: ExpenseInput): Promise<Expense>;
  voidExpense(id: string): Promise<Expense>;
}

const live: FinanceService = {
  summary: (start, end) =>
    apiRequest("GET", "/finance/summary", financeSummarySchema, {
      query: { start, end },
    }),
  expenses: ({ page = 1, pageSize = 25, search, category }) =>
    apiRequest("GET", "/finance/expenses", pageSchema(expenseSchema), {
      query: { page, page_size: pageSize, search, category },
    }),
  createExpense: (input) =>
    apiRequest("POST", "/finance/expenses", expenseSchema, { body: input }),
  voidExpense: (id) =>
    apiRequest("POST", `/finance/expenses/${id}/void`, expenseSchema),
};

const demo: FinanceService = {
  async summary(start, end) {
    await demoDelay();
    const business = demoBusiness();
    const currency = business.settings.default_currency;
    const payments = business.invoices
      .flatMap((i) => i.payments)
      .filter((p) => p.received_on >= start && p.received_on <= end);
    const expenses = business.expenses.filter(
      (e) =>
        e.status === "recorded" &&
        e.incurred_on >= start &&
        e.incurred_on <= end,
    );
    const today = dateOnly(0);
    const open = business.invoices.filter((i) =>
      ["issued", "partially_paid"].includes(i.status),
    );
    const bucketOf = (due: string | null) => {
      if (!due || due >= today) return "current";
      const days = Math.floor((Date.parse(today) - Date.parse(due)) / 86400000);
      return days <= 30
        ? "1-30"
        : days <= 60
          ? "31-60"
          : days <= 90
            ? "61-90"
            : "90+";
    };
    const aging = ["current", "1-30", "31-60", "61-90", "90+"].map((bucket) => {
      const rows = open.filter((i) => bucketOf(i.due_date) === bucket);
      return {
        bucket,
        amount: sumMoney(
          rows.map((i) => sumMoney([i.total, `-${i.amount_paid}`])),
        ),
        count: rows.length,
      };
    });
    const byCategory = new Map<string, string[]>();
    for (const e of expenses)
      byCategory.set(e.category, [
        ...(byCategory.get(e.category) ?? []),
        e.amount,
      ]);
    const cashIn = sumMoney(payments.map((p) => p.amount));
    const cashOut = sumMoney(expenses.map((e) => e.amount));
    return {
      currency,
      period_start: start,
      period_end: end,
      cash_in: cashIn,
      cash_out: cashOut,
      net_cash: sumMoney([cashIn, `-${cashOut}`]),
      receivables: sumMoney(aging.map((a) => a.amount)),
      aging,
      expenses_by_category: [...byCategory.entries()]
        .map(([category, amounts]) => ({ category, amount: sumMoney(amounts) }))
        .sort((a, b) => Number(b.amount) - Number(a.amount)),
    };
  },
  async expenses({ page = 1, pageSize = 25, search, category }) {
    await demoDelay();
    const rows = demoBusiness().expenses.filter(
      (e) =>
        (!category || e.category === category) &&
        (!search ||
          matches(e.description, search) ||
          matches(e.vendor, search)),
    );
    return paginate(rows, page, pageSize);
  },
  async createExpense(input) {
    await demoDelay(300);
    if (input.incurred_on > dateOnly(0))
      throw new ApiError(
        422,
        "FUTURE_DATE",
        undefined,
        "Expenses cannot be dated in the future",
      );
    const business = demoBusiness();
    const expense: Expense = {
      id: demoId("exp"),
      number: nextNumber(business, "expense"),
      currency: business.settings.default_currency,
      status: "recorded",
      recorded_by_label: "Amina Rahman",
      created_at: new Date().toISOString(),
      ...input,
    };
    business.expenses.unshift(expense);
    return expense;
  },
  async voidExpense(id) {
    await demoDelay(200);
    const expense = demoBusiness().expenses.find((e) => e.id === id);
    if (!expense) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (expense.status === "void")
      throw new ApiError(
        422,
        "ALREADY_VOID",
        undefined,
        "This expense is already void",
      );
    expense.status = "void";
    return { ...expense };
  },
};

export const financeService = select<FinanceService>({ demo, live });
