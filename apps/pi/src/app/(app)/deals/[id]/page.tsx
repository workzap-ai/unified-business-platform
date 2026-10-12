import { DealPage } from "@/features/deal";

export const metadata = { title: "Deal" };

export default async function Page(props: { params: Promise<{ id: string }> }) {
  const { id } = await props.params;
  return <DealPage id={id} />;
}
