import { CustomerConversation } from "@/features/customer/portal";

export const metadata = { title: "Conversation" };

export default async function Page(props: { params: Promise<{ id: string }> }) {
  const { id } = await props.params;
  return <CustomerConversation id={id} />;
}
