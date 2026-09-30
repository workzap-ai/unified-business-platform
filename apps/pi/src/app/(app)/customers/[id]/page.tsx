import { CustomerProfilePage } from "@/features/customers";

export const metadata = { title: "Customer" };

export default async function Page(props: PageProps<"/customers/[id]">) {
  const { id } = await props.params;
  return <CustomerProfilePage id={id} />;
}
