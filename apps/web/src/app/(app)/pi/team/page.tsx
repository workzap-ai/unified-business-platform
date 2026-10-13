import type { Metadata } from "next";
import { TeamBoardPage } from "@/features/pi/workspace/team-board-page";

export const metadata: Metadata = { title: "Team board" };

export default function Page() {
  return <TeamBoardPage />;
}
