import { PayRequestPage } from "@/features/public/pay-request";

export const metadata = { title: "Make a payment" };

export default async function Page(props: PageProps<"/pay/request/[token]">) {
  const { token } = await props.params;
  return <PayRequestPage token={token} />;
}
