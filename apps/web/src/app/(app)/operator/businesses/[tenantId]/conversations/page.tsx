import type { Metadata } from "next";
import { OperatorConversationsPage } from "@/features/operator/operator-pages";

export const metadata: Metadata = { title: "Customer conversations" };

export default async function Page(
  props: PageProps<"/operator/businesses/[tenantId]/conversations">,
) {
  const { tenantId } = await props.params;
  return <OperatorConversationsPage id={tenantId} />;
}
