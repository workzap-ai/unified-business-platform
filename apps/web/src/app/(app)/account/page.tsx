import type { Metadata } from "next";
import { AccountPage } from "@/features/account/account-page";

export const metadata: Metadata = { title: "Account & security" };

export default function Page() {
  return <AccountPage />;
}
