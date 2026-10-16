"use client";

/**
 * "Your solution", as in Owner OS: for a customer who paid, what they asked for and
 * what they bought, one block per paid project: their problem and goal, the proposal's
 * lines and must-haves, the work (Paid → Work started → Delivered), the payment with
 * its receipts, and their latest feedback. GET /customers/{id}/solution (saved records
 * only). Hidden until a project is paid.
 */

import { useQuery } from "@tanstack/react-query";
import { Check, Download, PackageCheck } from "lucide-react";
import Link from "next/link";

import { Badge, Card, CardSection, cn } from "@/components/ui";
import { fileDownloadUrl } from "@/features/customer-files";
import { get } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useBusinessKey, useCan } from "@/lib/session";

type Step = { key: string; label: string; done: boolean; at: string | null };

type Project = {
  lead_id: string;
  title: string;
  service?: string;
  notes?: {
    problem?: string;
    goal?: string;
    features?: string[];
  };
  bought: {
    quote_id: string;
    quote_number: string;
    currency: string;
    total: string;
    lines?: { description: string; quantity: string; line_total: string }[];
    proposal?: {
      intro?: string;
      sections?: { title: string; points: string[] }[];
    };
  };
  payment: {
    invoice_id: string;
    invoice_number: string;
    status: string;
    currency: string;
    total: string;
    amount_paid: string;
    balance: string;
    paid_at: string | null;
    receipts?: { file_id: string; name: string }[];
  };
  delivery: { steps?: Step[] };
  feedback?: { mood?: string; words?: string; at?: string }[];
  next?: { title: string; detail?: string } | null;
};

const MOOD: Record<
  string,
  { label: string; tone: "success" | "warning" | "info" }
> = {
  happy: { label: "Happy", tone: "success" },
  unhappy: { label: "Unhappy", tone: "warning" },
  neutral: { label: "Feedback", tone: "info" },
};

export function CustomerSolution({ id }: { id: string }) {
  const key = useBusinessKey();
  const query = useQuery({
    queryKey: key(["customer-solution", id]),
    queryFn: () => get<{ projects: Project[] }>(`/customers/${id}/solution`),
  });
  const projects = query.data?.projects ?? [];
  if (!projects.length) return null;
  return (
    <Card>
      <CardSection className="space-y-3">
        <div className="flex items-center gap-2">
          <PackageCheck className="size-5 text-accent" aria-hidden />
          <div className="min-w-0">
            <h2 className="font-semibold">Your solution</h2>
            <p className="text-xs text-muted-foreground">
              {projects.length === 1
                ? "What this customer asked for and bought"
                : `${projects.length} paid projects: what they asked for and bought`}
            </p>
          </div>
        </div>
        {projects.map((project) => (
          <SolutionBlock key={project.lead_id} project={project} />
        ))}
      </CardSection>
    </Card>
  );
}

function SolutionBlock({ project }: { project: Project }) {
  const can = useCan();
  const { bought, payment, delivery } = project;
  const notes = project.notes ?? {};
  const part = payment.status === "partially_paid";
  const mustHaves = notes.features ?? [];
  const said = project.feedback?.at(-1);
  const mood = MOOD[said?.mood ?? ""] ?? MOOD.neutral;
  const extra = (bought.proposal?.sections ?? []).filter(
    (s) => s.points.length > 0 && s.title !== "Next steps",
  );
  return (
    <section className="min-w-0 rounded-lg border border-border p-3 sm:p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="break-words text-sm font-semibold" data-user-text>
            {project.title}
          </h3>
          {project.service ? (
            <p className="text-xs text-muted-foreground" data-user-text>
              {project.service}
            </p>
          ) : null}
        </div>
        <Badge tone={part ? "warning" : "success"}>
          {part ? "Part paid" : "Paid"}
        </Badge>
      </header>

      {notes.problem || notes.goal ? (
        <dl className="mt-2 space-y-1 text-sm">
          {notes.problem ? (
            <div>
              <dt className="inline font-medium">Their problem: </dt>
              <dd className="inline text-muted-foreground" data-user-text>
                {notes.problem}
              </dd>
            </div>
          ) : null}
          {notes.goal ? (
            <div>
              <dt className="inline font-medium">Goal: </dt>
              <dd className="inline text-muted-foreground" data-user-text>
                {notes.goal}
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      <div className="mt-3">
        <p className="text-xs font-medium text-muted-foreground">
          What we&apos;re delivering ·{" "}
          {can("sales.read") ? (
            <Link
              href={`/deals/${project.lead_id}`}
              className="font-mono text-accent hover:underline"
            >
              {bought.quote_number}
            </Link>
          ) : (
            <span className="font-mono">{bought.quote_number}</span>
          )}
        </p>
        <ul className="mt-1 divide-y divide-border rounded-lg bg-surface-muted text-sm">
          {(bought.lines ?? []).map((line, i) => (
            <li key={i} className="flex items-start gap-3 px-3 py-1.5">
              <span className="min-w-0 flex-1 break-words" data-user-text>
                {line.description}
                {Number(line.quantity) !== 1 ? (
                  <span className="text-muted-foreground">
                    {" "}
                    × {Number(line.quantity)}
                  </span>
                ) : null}
              </span>
              <span className="shrink-0 tabular-nums">
                {money(line.line_total, bought.currency)}
              </span>
            </li>
          ))}
          <li className="flex items-center gap-3 px-3 py-1.5 font-medium">
            <span className="flex-1">Total</span>
            <span className="shrink-0 tabular-nums">
              {money(bought.total, bought.currency)}
            </span>
          </li>
        </ul>
        {mustHaves.length > 0 ? (
          <div className="mt-2 text-sm">
            <p className="text-xs font-medium text-muted-foreground">
              Must-haves
            </p>
            <ul className="mt-0.5 grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
              {mustHaves.map((item) => (
                <li key={item} className="flex min-w-0 gap-1.5">
                  <Check
                    className="mt-0.5 size-4 shrink-0 text-success"
                    aria-hidden
                  />
                  <span className="min-w-0 break-words" data-user-text>
                    {item}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {extra.length > 0 ? (
          <details className="mt-2 text-sm">
            <summary className="cursor-pointer select-none py-1 text-xs font-medium text-accent">
              The proposal in full ·{" "}
              {extra.map((s) => s.title.toLowerCase()).join(" · ")}
            </summary>
            {bought.proposal?.intro ? (
              <p
                className="mt-1.5 whitespace-pre-line text-muted-foreground"
                data-user-text
              >
                {bought.proposal.intro}
              </p>
            ) : null}
            <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
              {extra.map((section) => (
                <div key={section.title} className="min-w-0">
                  <p className="font-medium" data-user-text>
                    {section.title}
                  </p>
                  <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
                    {section.points.map((point, i) => (
                      <li key={i} className="flex gap-1.5">
                        <span aria-hidden>•</span>
                        <span className="min-w-0 break-words" data-user-text>
                          {point}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>

      <WorkSteps steps={delivery.steps ?? []} />

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
        <span>
          <span className="font-medium">
            {money(payment.amount_paid, payment.currency)}
          </span>
          <span className="text-muted-foreground">
            {" "}
            paid of {money(payment.total, payment.currency)}
          </span>
          {Number(payment.balance) > 0 ? (
            <span className="text-warning">
              {" "}
              · {money(payment.balance, payment.currency)} to go
            </span>
          ) : null}
        </span>
        <span className="font-mono text-xs text-muted-foreground">
          {payment.invoice_number}
        </span>
        {(payment.receipts ?? []).map((receipt) => (
          <a
            key={receipt.file_id}
            href={fileDownloadUrl(receipt.file_id)}
            download
            className="inline-flex min-h-8 min-w-0 max-w-full items-center gap-1 text-xs text-accent hover:underline"
          >
            <Download className="size-4 shrink-0" aria-hidden />
            <span className="truncate" data-user-text>
              {receipt.name}
            </span>
          </a>
        ))}
      </div>

      {said ? (
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-sm">
          <Badge tone={mood.tone}>{mood.label}</Badge>
          <span
            className="min-w-0 break-words text-muted-foreground"
            data-user-text
          >
            &ldquo;{said.words}&rdquo;
          </span>
          {said.at ? (
            <span className="text-xs text-muted-foreground">
              {date(said.at)}
            </span>
          ) : null}
        </p>
      ) : null}

      {project.next ? (
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Next: </span>
          {project.next.title}
        </p>
      ) : null}
    </section>
  );
}

/** Paid → Work started → Delivered, with the date each step happened. */
function WorkSteps({ steps }: { steps: Step[] }) {
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
              {step.done ? <Check className="size-3" aria-hidden /> : i + 1}
            </span>
            {i < steps.length - 1 ? (
              <span
                className={cn(
                  "h-px flex-1",
                  steps[i + 1]?.done ? "bg-success" : "bg-border",
                )}
                aria-hidden
              />
            ) : null}
          </div>
          <p
            className={cn(
              "mt-1 truncate text-xs font-medium",
              !step.done && "text-muted-foreground",
            )}
          >
            {step.label}
            <span className="sr-only">{step.done ? " (done)" : ""}</span>
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {step.at ? date(step.at) : step.done ? "Done" : "—"}
          </p>
        </li>
      ))}
    </ol>
  );
}
