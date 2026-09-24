import type { Metadata } from "next";
import { LocationsPage } from "@/features/inventory/locations-page";

export const metadata: Metadata = { title: "Locations" };

export default function Page() {
  return <LocationsPage />;
}
