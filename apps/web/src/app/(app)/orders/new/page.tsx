import type { Metadata } from "next";
import { NewOrderPage } from "@/features/documents/builder-pages";

export const metadata: Metadata = { title: "New order" };

export default function Page() {
  return <NewOrderPage />;
}
