import { MessageCircle } from "lucide-react";
import { Badge } from "@/components/ui/display";
import type { Customer } from "@/features/business/types";
import { CUSTOMER_SOURCE_LABELS } from "../lib";

export function CustomerSourceBadge({
  source,
}: {
  source: Customer["source"];
}) {
  if (source === "whatsapp") {
    return (
      <Badge tone="info">
        <MessageCircle aria-hidden="true" /> {CUSTOMER_SOURCE_LABELS.whatsapp}
      </Badge>
    );
  }
  return <Badge tone="outline">{CUSTOMER_SOURCE_LABELS[source]}</Badge>;
}

export function TagList({ tags, max = 3 }: { tags: string[]; max?: number }) {
  if (!tags.length) return <span className="text-muted-foreground">—</span>;
  const shown = tags.slice(0, max);
  const rest = tags.length - shown.length;
  return (
    <span className="flex flex-wrap items-center gap-1">
      {shown.map((tag) => (
        <Badge key={tag} tone="neutral">
          {tag}
        </Badge>
      ))}
      {rest > 0 && (
        <span
          className="text-xs text-muted-foreground"
          title={tags.slice(max).join(", ")}
        >
          +{rest}
        </span>
      )}
    </span>
  );
}
