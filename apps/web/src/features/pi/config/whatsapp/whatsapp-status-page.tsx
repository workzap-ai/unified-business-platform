"use client";

import Link from "next/link";
import {
  ArrowDownLeft,
  ArrowUpRight,
  MessageCircle,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { formatDateTime, formatNumber, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { PropertyList } from "@/components/app/record";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import { humanizeError, piKeys } from "../shared";
import { WhatsAppNav } from "./whatsapp-nav";

export function WhatsAppStatusPage() {
  return (
    <RequirePermission permission="pi.whatsapp.manage" area="WhatsApp settings">
      <Status />
    </RequirePermission>
  );
}

function Status() {
  const connection = useScopedQuery(
    piKeys.connection,
    () => piService.connection(),
    { refetchInterval: 30_000 },
  );
  const c = connection.data;
  return (
    <PageShell width="default">
      <PageHeader
        title="WhatsApp"
        description="Health of the connected number: traffic, delivery and webhook verification."
      />
      <WhatsAppNav />
      {connection.isError ? (
        <Card>
          <ErrorState
            error={connection.error}
            onRetry={() => void connection.refetch()}
          />
        </Card>
      ) : connection.isPending ? (
        <div className="space-y-4">
          <MetricGrid className="xl:grid-cols-3">
            {Array.from({ length: 3 }, (_, i) => (
              <MetricCard key={i} label="" value="" loading />
            ))}
          </MetricGrid>
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : !c ? (
        <Card>
          <EmptyState
            tone="pi"
            icon={MessageCircle}
            title="No WhatsApp number connected"
            description="Connect a number to see delivery health here."
            action={
              <Button size="sm" asChild>
                <Link href="/pi/whatsapp">Set up connection</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          <MetricGrid className="xl:grid-cols-3">
            <MetricCard
              label="Inbound (24h)"
              icon={ArrowDownLeft}
              value={formatNumber(c.messages_24h.inbound)}
              detail={
                c.last_inbound_at
                  ? `Last ${relativeTime(c.last_inbound_at)}`
                  : "None received yet"
              }
            />
            <MetricCard
              label="Outbound (24h)"
              icon={ArrowUpRight}
              value={formatNumber(c.messages_24h.outbound)}
              detail={
                c.last_outbound_at
                  ? `Last ${relativeTime(c.last_outbound_at)}`
                  : "None sent yet"
              }
            />
            <MetricCard
              label="Failed (24h)"
              icon={TriangleAlert}
              tone={c.messages_24h.failed ? "danger" : "default"}
              value={formatNumber(c.messages_24h.failed)}
              detail="Messages WhatsApp didn't accept"
            />
          </MetricGrid>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Connection health" />
              <CardBody>
                <PropertyList
                  items={[
                    {
                      label: "Status",
                      value: <StatusBadge status={c.status} />,
                    },
                    {
                      label: "Number",
                      value: c.display_phone_number,
                    },
                    {
                      label: "Last inbound",
                      value: c.last_inbound_at ? (
                        <time
                          dateTime={c.last_inbound_at}
                          title={formatDateTime(c.last_inbound_at)}
                        >
                          {relativeTime(c.last_inbound_at)}
                        </time>
                      ) : (
                        "Never"
                      ),
                    },
                    {
                      label: "Last outbound",
                      value: c.last_outbound_at ? (
                        <time
                          dateTime={c.last_outbound_at}
                          title={formatDateTime(c.last_outbound_at)}
                        >
                          {relativeTime(c.last_outbound_at)}
                        </time>
                      ) : (
                        "Never"
                      ),
                    },
                    {
                      label: "Last error",
                      value: c.last_error_code ? (
                        <span className="text-danger">
                          {humanizeError(c.last_error_code)}
                        </span>
                      ) : (
                        <span className="text-success">None</span>
                      ),
                    },
                    {
                      label: "Error at",
                      value: c.last_error_at
                        ? formatDateTime(c.last_error_at)
                        : undefined,
                    },
                  ]}
                />
              </CardBody>
            </Card>
            <Card>
              <CardHeader
                title="Webhook"
                icon={<ShieldCheck />}
                description="How WhatsApp delivers customer messages to PI"
              />
              <CardBody className="space-y-3">
                {c.webhook_verified ? (
                  <Notice tone="success" title="Webhook verified">
                    Verified{" "}
                    {c.verified_at ? formatDateTime(c.verified_at) : ""}. Every
                    request is checked against Meta&apos;s signature before
                    it&apos;s processed.
                  </Notice>
                ) : (
                  <Notice
                    tone="warning"
                    title="Webhook not verified"
                    action={
                      <Button size="xs" variant="secondary" asChild>
                        <Link href="/pi/whatsapp">Setup</Link>
                      </Button>
                    }
                  >
                    PI won&apos;t receive messages until Meta verifies the
                    webhook URL.
                  </Notice>
                )}
                <div className="space-y-2 text-[13px] text-foreground-secondary">
                  <p>
                    <span className="font-medium text-foreground">
                      Delivery.
                    </span>{" "}
                    Outbound messages move from sent to delivered to read as
                    WhatsApp reports status updates. A failed message is usually
                    a recipient issue — e.g. the customer hasn&apos;t messaged
                    in the last 24 hours — and is never retried automatically in
                    a way that could double-send.
                  </p>
                  <p>
                    <Link
                      href="/pi/whatsapp/events"
                      className="font-medium text-primary hover:underline"
                    >
                      View the webhook event log
                    </Link>
                  </p>
                </div>
              </CardBody>
            </Card>
          </div>
        </div>
      )}
    </PageShell>
  );
}
