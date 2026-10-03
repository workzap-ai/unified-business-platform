"use client";

import { ErrorState, Skeleton } from "@/components/ui";
import { errorText } from "@/lib/api";
import { ConversationView } from "./conversation";
import { Dashboard } from "./dashboard";
import { useMe } from "./shared";
import { SignIn } from "./sign-in";

function Loading() {
  return (
    <div
      className="mx-auto w-full max-w-6xl space-y-4"
      role="status"
      aria-label="Loading"
    >
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-24 w-full rounded-2xl" />
      <Skeleton className="h-64 w-full rounded-2xl" />
    </div>
  );
}

export function CustomerHome() {
  const me = useMe();
  if (me.isPending) return <Loading />;
  if (me.isError)
    return (
      <ErrorState message={errorText(me.error)} onRetry={() => me.refetch()} />
    );
  return me.data ? <Dashboard me={me.data} /> : <SignIn />;
}

export function CustomerConversation({ id }: { id: string }) {
  const me = useMe();
  if (me.isPending) return <Loading />;
  if (!me.data) return <SignIn />;
  return <ConversationView id={id} />;
}
