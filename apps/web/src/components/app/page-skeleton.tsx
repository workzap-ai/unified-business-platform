import { Skeleton } from "@/components/ui/display";

export function PageSkeleton({
  variant = "list",
}: {
  variant?: "list" | "detail" | "dashboard";
}) {
  return (
    <div
      className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6 lg:px-8 lg:py-6"
      aria-busy="true"
      aria-label="Loading"
    >
      <Skeleton className="h-6 w-48" />
      <Skeleton className="mt-2 h-4 w-80 max-w-full" />
      {variant === "dashboard" && (
        <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-[104px] rounded-xl" />
          ))}
        </div>
      )}
      {variant === "detail" ? (
        <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_340px]">
          <Skeleton className="h-96 rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      ) : (
        <>
          <div className="mt-6 flex gap-2">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-8 w-24" />
          </div>
          <Skeleton className="mt-3 h-[420px] rounded-xl" />
        </>
      )}
    </div>
  );
}
