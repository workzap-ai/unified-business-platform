import { PageHeader } from "@/components/ui";
import { NotificationsList } from "@/features/journey";

export const metadata = { title: "Notifications" };

export default function Page() {
  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Your business review, plan and WhatsApp number, as they happen."
      />
      <NotificationsList />
    </div>
  );
}
