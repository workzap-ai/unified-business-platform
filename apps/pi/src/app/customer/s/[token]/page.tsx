import { SharedRequests } from "@/features/customer/shared-view";

export const metadata = {
  title: "Shared requests",
  // The token is in the address: never send it to another site.
  referrer: "no-referrer" as const,
  robots: { index: false, follow: false },
};

export default async function Page(props: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await props.params;
  return <SharedRequests token={token} />;
}
