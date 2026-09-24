import type { Metadata } from "next";
import { FulfillmentPage } from "@/features/documents/fulfillment-page";

export const metadata: Metadata = { title: "Fulfillment" };

export default function Page() {
  return <FulfillmentPage />;
}
