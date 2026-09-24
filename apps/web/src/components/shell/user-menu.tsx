"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, Eye, Keyboard, LogOut, Moon, Plus, Sun, UserRound } from "lucide-react";
import { toast } from "sonner";
import { Avatar } from "@/components/ui/display";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { Button } from "@/components/ui/button";
import { useSession } from "@/features/auth/session-provider";
import { MODULE_MANIFESTS } from "@/features/modules/manifests";
import { demoRoles } from "@/demo/workspace";
import { isDemo } from "@/lib/data-mode";
import { useCommandMenu } from "./command-menu";
import { useTheme } from "./theme";

export function UserMenu() {
  const { session, logout, setDemoRole } = useSession();
  const { theme, setTheme } = useTheme();
  const { open } = useCommandMenu();
  const router = useRouter();
  if (!session) return null;
  const name = session.user.display_name;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center rounded-full ring-offset-2 ring-offset-surface focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Account menu for ${name}`}
        >
          <Avatar name={name} size="sm" className="size-7" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64">
        <div className="flex items-center gap-2.5 px-2 py-2">
          <Avatar name={name} size="md" />
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold">{name}</p>
            <p className="truncate text-xs text-muted-foreground">{session.user.email}</p>
          </div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/account">
            <UserRound /> Account & security
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? <Sun /> : <Moon />} {theme === "dark" ? "Light" : "Dark"} theme
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={open}>
          <Keyboard /> Search & shortcuts
          <span className="ml-auto text-2xs text-muted-foreground">Ctrl K</span>
        </DropdownMenuItem>
        {isDemo && (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              <Eye className="size-4 text-muted-foreground" /> View as role
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="w-56">
              <DropdownMenuLabel>Sample-data preview</DropdownMenuLabel>
              {demoRoles().map((role) => (
                <DropdownMenuItem
                  key={role.key}
                  onSelect={() =>
                    void setDemoRole(role.key).then(() => toast.success(`Viewing as ${role.name}`))
                  }
                >
                  <span className="flex-1">{role.name}</span>
                  {session.roles.includes(role.key) && <Check className="!text-primary" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            void logout().then(() => router.push("/login"));
          }}
        >
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function QuickCreate() {
  const { can } = useSession();
  const actions = MODULE_MANIFESTS.flatMap((m) => m.actions ?? []).filter(
    (a) => !a.permission || can(a.permission),
  );
  if (actions.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" className="gap-1 px-2 sm:px-2.5" aria-label="Create">
          <Plus /> <span className="hidden sm:inline">Create</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56">
        <DropdownMenuLabel>Create new</DropdownMenuLabel>
        {actions.map((a) => (
          <DropdownMenuItem key={a.id} asChild>
            <Link href={a.href}>
              <a.icon /> {a.label.replace(/^(Create|New|Add) /, "")}
            </Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
