import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { MyPiOverview } from "@/features/my-pi";

export const metadata = { title: "My Pi settings" };

export default function Page() {
  return (
    <div>
      <Link
        href="/my-pi"
        className="mb-5 inline-flex items-center gap-2 text-sm text-accent hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden /> Back to My Pi
      </Link>
      <MyPiOverview />
    </div>
  );
}
