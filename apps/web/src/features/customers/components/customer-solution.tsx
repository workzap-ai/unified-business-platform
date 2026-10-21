"use client";

import Link from "next/link";
import { z } from "zod";
import { Check, Download, PackageCheck } from "lucide-react";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { useScopedQuery } from "@/hooks/use-scoped";
import { cn } from "@/lib/utils";
import { formatDate, formatMoney } from "@/lib/format";
import { apiRequest } from "@/services/api-client";
import { customerFilesService } from "../files-service";

/**
 * "Your solution": for a customer who paid, what they asked for and what they bought,
 * one block per paid project: their problem and goal, the proposal's lines and
 * must-haves, the work (Paid → Work started → Delivered), the payment with its
 * receipts, and their latest feedback. Backend: /customers/{id}/solution (saved
 * records only). Hidden until a project is paid.
 */

const stepSchema = z.object({
  key: z.string(),
  label: z.string(),
  done: z.boolean(),
  at: z.string().nullable().catch(null),
});
const projectSchema = z.object({
  lead_id: z.string(),
  title: z.string(),
  service: z.string().catch(""),
  scope: z.string().catch(""),
  notes: z
    .object({
      problem: z.string().optional(),
      goal: z.string().optional(),
      audience: z.string().optional(),
      target_date: z.string().optional(),
      features: z.array(z.string()).optional(),
      decisions: z.array(z.string()).optional(),
    })
    .catch({}),
  bought: z.object({
    quote_id: z.string(),
    quote_number: z.string(),
    currency: z.string(),
    total: z.string(),
    lines: z
      .array(
        z.object({
          description: z.string(),
          quantity: z.string(),
          line_total: z.string(),
        }),
      )
      .catch([]),
    proposal: z
      .object({
        intro: z.string().catch(""),
        sections: z
          .array(z.object({ title: z.string(), points: z.array(z.string()) }))
          .catch([]),
      })
      .catch({ intro: "", sections: [] }),
  }),
  payment: z.object({
    invoice_id: z.string(),
    invoice_number: z.string(),
    status: z.string(),
    currency: z.string(),
    total: z.string(),
    amount_paid: z.string(),
    balance: z.string(),
    paid_at: z.string().nullable().catch(null),
    receipts: z
      .array(z.object({ file_id: z.string(), name: z.string() }))
      .catch([]),
  }),
  delivery: z.object({
    order_id: z.string(),
    order_number: z.string(),
    order_status: z.string(),
    steps: z.array(stepSchema).catch([]),
  }),
  feedback: z
    .array(
      z.object({
        mood: z.string().catch("neutral"),
        words: z.string().catch(""),
        at: z.string().catch(""),
      }),
    )
    .catch([]),
  next: z
    .object({ title: z.string(), detail: z.string().catch("") })
    .nullable()
    .catch(null),
});
const solutionSchema = z.object({ projects: z.array(projectSchema).catch([]) });
type Project = z.infer<typeof projectSchema>;

const MOOD: Record<
  string,
  { label: string; tone: "success" | "warning" | "info" }
> = {
  happy: { label: "Happy", tone: "success" },
  unhappy: { label: "Unhappy", tone: "warning" },
  neutral: { label: "Feedback", tone: "info" },
};

export function CustomerSolution({ customerId }: { customerId: string }) {
  const query = useScopedQuery(["customers", customerId, "solution"], () =>
    apiRequest("GET", `/customers/${customerId}/solution`, solutionSchema),
  );
  const projects = query.data?.projects ?? [];
  if (!projects.length) return null;
  return (
    <Card>
      <CardHeader
        icon={<PackageCheck />}
        title="Your solution"
        description={
          projects.length === 1
            ? "What this customer asked for and bought"
            : `${projects.length} paid projects: what they asked for and bought`
        }
      />
      <CardBody className="space-y-3">
        {projects.map((project) => (
          <SolutionBlock key={project.lead_id} project={project} />
        ))}
      </CardBody>
    </Card>
  );
}

function SolutionBlock({ project }: { project: Project }) {
  const { bought, payment, delivery, notes } = project;
  const part = payment.status === "partially_paid";
  const mustHaves = notes.features ?? [];
  const said = project.feedback.at(-1);
  const extra = bought.proposal.sections.filter(
    (s) => s.points.length > 0 && s.title !== "Next steps",
  );
  return (
    <section className="min-w-0 rounded-lg border border-border p-3 sm:p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[13.5px] font-semibold break-words">
            {project.title}
          </h3>
          {project.service && (
            <p className="text-xs text-muted-foreground">{project.service}</p>
          )}
        </div>
        <Badge tone={part ? "warning" : "success"}>
          {part ? "Part paid" : "Paid"}
        </Badge>
      </header>

      {(notes.problem || notes.goal) && (
        <dl className="mt-2 space-y-1 text-[13px]">
          {notes.problem && (
            <div>
              <dt className="inline font-medium">Their problem: </dt>
              <dd className="inline text-muted-foreground">{notes.problem}</dd>
            </div>
          )}
          {notes.goal && (
            <div>
              <dt className="inline font-medium">Goal: </dt>
              <dd className="inline text-muted-foreground">{notes.goal}</dd>
            </div>
          )}
        </dl>
      )}

      <div className="mt-3">
        <p className="text-xs font-medium text-muted-foreground">
          What we&apos;re delivering ·{" "}
          <Link
            href={`/quotes/${bought.quote_id}`}
            className="font-mono text-primary hover:underline"
          >
            {bought.quote_number}
          </Link>
        </p>
        <ul className="mt-1 divide-y divide-border rounded-lg bg-surface-muted text-[13px]">
          {bought.lines.map((line, i) => (
            <li key={i} className="flex items-start gap-3 px-2.5 py-1.5">
              <span className="min-w-0 flex-1 break-words">
                {line.description}
                {Number(line.quantity) !== 1 && (
                  <span className="text-muted-foreground">
                    {" "}
                    × {Number(line.quantity)}
                  </span>
                )}
              </span>
              <span className="tabular shrink-0">
                {formatMoney(line.line_total, bought.currency)}
              </span>
            </li>
          ))}
          <li className="flex items-center gap-3 px-2.5 py-1.5 font-medium">
            <span className="flex-1">Total</span>
            <span className="tabular shrink-0">
              {formatMoney(bought.total, bought.currency)}
            </span>
          </li>
        </ul>
        {mustHaves.length > 0 && (
          <div className="mt-2 text-[13px]">
            <p className="text-xs font-medium text-muted-foreground">
              Must-haves
            </p>
            <ul className="mt-0.5 grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
              {mustHaves.map((item) => (
                <li key={item} className="flex min-w-0 gap-1.5">
                  <Check
                    className="mt-0.5 size-3.5 shrink-0 text-success"
                    aria-hidden="true"
                  />
                  <span className="min-w-0 break-words">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {extra.length > 0 && (
          <details className="mt-2 text-[13px]">
            <summary className="cursor-pointer text-xs font-medium text-primary select-none">
              The proposal in full ·{" "}
              {extra.map((s) => s.title.toLowerCase()).join(" · ")}
            </summary>
            {bought.proposal.intro && (
              <p className="mt-1.5 whitespace-pre-line text-muted-foreground">
                {bought.proposal.intro}
              </p>
            )}
            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
              {extra.map((section) => (
                <div key={section.title} className="min-w-0">
                  <p className="font-medium">{section.title}</p>
                  <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
                    {section.points.map((point, i) => (
                      <li key={i} className="flex gap-1.5">
                        <span aria-hidden="true">•</span>
                        <span className="min-w-0 break-words">{point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>

      <Progress steps={delivery.steps} />

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]">
        <span>
          <span className="font-medium">
            {formatMoney(payment.amount_paid, payment.currency)}
          </span>
          <span className="text-muted-foreground">
            {" "}
            paid of {formatMoney(payment.total, payment.currency)}
          </span>
          {Number(payment.balance) > 0 && (
            <span className="text-warning">
              {" "}
              · {formatMoney(payment.balance, payment.currency)} to go
            </span>
          )}
        </span>
        <Link
          href={`/billing/invoices/${payment.invoice_id}`}
          className="font-mono text-xs text-primary hover:underline"
        >
          {payment.invoice_number}
        </Link>
        {payment.receipts.map((receipt) => (
          <a
            key={receipt.file_id}
            href={customerFilesService.downloadUrl(receipt.file_id)}
            download
            className="inline-flex max-w-full min-w-0 items-center gap-1 text-xs text-primary hover:underline"
          >
            <Download className="size-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate">{receipt.name}</span>
          </a>
        ))}
      </div>

      {said && (
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-[13px]">
          <Badge tone={(MOOD[said.mood] ?? MOOD.neutral!).tone}>
            {(MOOD[said.mood] ?? MOOD.neutral!).label}
          </Badge>
          <span className="min-w-0 break-words text-muted-foreground">
            &ldquo;{said.words}&rdquo;
          </span>
          {said.at && (
            <span className="text-xs text-muted-foreground">
              {formatDate(said.at)}
            </span>
          )}
        </p>
      )}

      {project.next && (
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Next: </span>
          {project.next.title}
        </p>
      )}
    </section>
  );
}

/** Paid → Work started → Delivered, with the date each step happened. */
function Progress({ steps }: { steps: z.infer<typeof stepSchema>[] }) {
  if (!steps.length) return null;
  return (
    <ol className="mt-3 grid grid-cols-3 gap-1" aria-label="Progress">
      {steps.map((step, i) => (
        <li key={step.key} className="min-w-0">
          <div className="flex items-center gap-1">
            <span
              className={cn(
                "flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold",
                step.done
                  ? "border-success/40 bg-success-soft text-success"
                  : "border-border bg-surface-muted text-muted-foreground",
              )}
            >
              {step.done ? (
                <Check className="size-3" aria-hidden="true" />
              ) : (
                i + 1
              )}
            </span>
            {i < steps.length - 1 && (
              <span
                className={cn(
                  "h-px flex-1",
                  steps[i + 1]?.done ? "bg-success" : "bg-border",
                )}
                aria-hidden="true"
              />
            )}
          </div>
          <p
            className={cn(
              "mt-1 truncate text-xs font-medium",
              !step.done && "text-muted-foreground",
            )}
          >
            {step.label}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {step.at ? formatDate(step.at, "d MMM") : step.done ? "Done" : "—"}
          </p>
        </li>
      ))}
    </ol>
  );
}
