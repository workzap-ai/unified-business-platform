import { Bot, Boxes, ShieldCheck, Sparkles } from "lucide-react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_minmax(0,560px)]">
      <aside className="relative hidden overflow-hidden bg-sidebar p-10 text-sidebar-foreground lg:flex lg:flex-col">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-sidebar-active text-sidebar-active-foreground">
            <Boxes className="size-4.5" aria-hidden="true" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">
            Workspace
          </span>
        </div>
        <div className="my-auto max-w-lg">
          <p className="text-2xs font-semibold tracking-[0.18em] text-sidebar-muted uppercase">
            One operating system for the business
          </p>
          <h2 className="mt-4 text-3xl leading-tight font-semibold tracking-tight">
            Customers, catalog, orders and money in one place, with an AI
            assistant that works from your real data.
          </h2>
          <ul className="mt-10 space-y-5 text-sm">
            <li className="flex gap-3">
              <Bot
                className="mt-0.5 size-5 shrink-0 text-pi"
                aria-hidden="true"
              />
              <span>
                <span className="font-semibold">PI answers on WhatsApp</span>
                <span className="block text-sidebar-muted">
                  Checks approved offerings and prices, drafts quotes, and hands
                  off to your team when a person should decide.
                </span>
              </span>
            </li>
            <li className="flex gap-3">
              <Sparkles
                className="mt-0.5 size-5 shrink-0 text-sidebar-muted"
                aria-hidden="true"
              />
              <span>
                <span className="font-semibold">Every module connected</span>
                <span className="block text-sidebar-muted">
                  Turn customer requirements into quotes, service orders and
                  invoices linked to one customer record.
                </span>
              </span>
            </li>
            <li className="flex gap-3">
              <ShieldCheck
                className="mt-0.5 size-5 shrink-0 text-sidebar-muted"
                aria-hidden="true"
              />
              <span>
                <span className="font-semibold">Isolated by design</span>
                <span className="block text-sidebar-muted">
                  Each workspace and environment is separated, and every action
                  is permission checked and audited.
                </span>
              </span>
            </li>
          </ul>
        </div>
        <p className="text-xs text-sidebar-muted">
          Secure session · HttpOnly cookies · CSRF protected
        </p>
      </aside>
      <main className="flex items-center justify-center bg-surface px-5 py-10 sm:px-10">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
