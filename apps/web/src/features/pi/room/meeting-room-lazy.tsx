"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/display";

/** The video SDK is large: it loads only when a room page asks for it, and never on the server. */
export const MeetingRoomCall = dynamic(
  () => import("./meeting-room-call").then((m) => m.MeetingRoomCall),
  { ssr: false, loading: () => <Skeleton className="h-72 w-full" /> },
);
