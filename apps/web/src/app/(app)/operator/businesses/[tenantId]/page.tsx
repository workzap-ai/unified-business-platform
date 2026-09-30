import type { Metadata } from "next";
import { OperatorBusinessPage } from "@/features/operator/operator-pages";

export const metadata: Metadata = { title: "Pi business" };

export default async function Page(
  props: PageProps<"/operator/businesses/[tenantId]">,
) {
  const { tenantId } = await props.params;
  return <OperatorBusinessPage id={tenantId} />;
}
