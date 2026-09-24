import { PiWorkspaceLayout } from "@/features/pi/workspace/pi-workspace-layout";

export default function PiLayout({ children }: { children: React.ReactNode }) {
  return <PiWorkspaceLayout>{children}</PiWorkspaceLayout>;
}
