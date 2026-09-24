import type { Metadata } from "next";
import { ExpensesPage } from "@/features/finance/expenses-page";

export const metadata: Metadata = { title: "Expenses" };

export default function Page() {
  return <ExpensesPage />;
}
