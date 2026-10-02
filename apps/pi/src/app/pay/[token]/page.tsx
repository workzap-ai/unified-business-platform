import { PayManualPage } from "@/features/public/pay-manual";

export const metadata = { title: "Make a payment" };

export default async function Page(props: PageProps<"/pay/[token]">) {
  const { token } = await props.params;
  return <PayManualPage token={token} />;
}
