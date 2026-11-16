"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { CreditCard, FolderKanban, ListChecks, LogOut, MapPinned, Menu, Plus, ShieldCheck, Sparkles, Upload } from "lucide-react";
import { cn } from "cn";
import { AppProvider, useApp } from "@/components/app/app-context";
import { Logo } from "@/components/site/logo";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/hooks/use-session";

interface NavItem {
  href: string;
  label: string;
  icon: typeof FolderKanban;
  /** Extra prefix that keeps this item highlighted (detail pages). */
  prefix?: string;
  tag?: string;
}

const MEMO_NAV: NavItem[] = [
  { href: "/app/memos", label: "Memos", icon: MapPinned, prefix: "/app/memos/" },
  { href: "/app/memo", label: "New memo", icon: Plus },
  { href: "/app/memos/bulk", label: "Bulk upload", icon: Upload, prefix: "/app/memos/bulk/", tag: "Pro" },
];

const CHECKLIST_NAV: NavItem[] = [
  { href: "/app/plans", label: "Permit checklists", icon: ListChecks, prefix: "/app/plans/" },
  { href: "/app/new", label: "New checklist", icon: FolderKanban },
];

const ACCOUNT_NAV: NavItem[] = [{ href: "/app/billing", label: "Billing", icon: CreditCard }];

const ADMIN_NAV: NavItem[] = [{ href: "/app/admin", label: "Admin", icon: ShieldCheck }];

function isActive(pathname: string, item: NavItem): boolean {
  if (pathname === item.href) return true;
  if (!item.prefix || !pathname.startsWith(item.prefix)) return false;
  // "Memos" must not light up for the bulk pages, which have their own item.
  return !(item.href === "/app/memos" && pathname.startsWith("/app/memos/bulk"));
}

function NavGroup({ title, items, onNavigate }: { title?: string; items: NavItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <div>
      {title && <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">{title}</p>}
      <div className="flex flex-col gap-0.5">
        {items.map((item) => {
          const active = isActive(pathname, item);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active ? "bg-sidebar-accent text-sidebar-foreground" : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
              )}
            >
              <item.icon className="size-4" aria-hidden />
              {item.label}
              {item.tag && <span className="ml-auto rounded-full border border-signal/50 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-signal">{item.tag}</span>}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const { me } = useApp();
  return (
    <nav className="flex flex-col gap-5" aria-label="App">
      <NavGroup title="Location Risk Memos" items={MEMO_NAV} onNavigate={onNavigate} />
      <NavGroup title="Free tier" items={CHECKLIST_NAV} onNavigate={onNavigate} />
      <NavGroup items={me?.is_admin ? [...ACCOUNT_NAV, ...ADMIN_NAV] : ACCOUNT_NAV} onNavigate={onNavigate} />
    </nav>
  );
}

function Entitlement() {
  const { me, meLoading } = useApp();
  if (meLoading && !me) return <Skeleton className="h-14 w-full bg-sidebar-accent" />;
  if (!me) return null;
  const kind = me.entitlement.kind;
  const pro = me.pro_status === "active" || me.pro_status === "trialing";
  return (
    <Link href="/app/billing" className="block rounded-lg border border-sidebar-border bg-sidebar-accent/50 p-3 text-xs transition-colors hover:bg-sidebar-accent">
      <div className="mb-2 border-b border-sidebar-border pb-2">
        {pro ? (
          <>
            <p className="inline-flex items-center gap-1.5 font-semibold text-sidebar-foreground">
              <Sparkles className="size-3.5 text-signal" aria-hidden /> Pro · unlimited memos
            </p>
            <p className="mt-0.5 text-sidebar-foreground/60">{me.pro_status === "trialing" ? "Trial active" : "Bulk upload included"}</p>
          </>
        ) : (
          <>
            <p className="font-semibold text-sidebar-foreground">
              {me.memo_credits > 0 ? `${me.memo_credits} memo credit${me.memo_credits === 1 ? "" : "s"}` : `${me.free_teasers_remaining} free memo teaser${me.free_teasers_remaining === 1 ? "" : "s"}`}
            </p>
            <p className="mt-0.5 text-sidebar-foreground/60">{me.memo_credits > 0 ? `${me.free_teasers_remaining} free teaser${me.free_teasers_remaining === 1 ? "" : "s"} left` : "Full memo $499 · Pro $299/mo"}</p>
          </>
        )}
      </div>
      {me.is_admin ? (
        <>
          <p className="inline-flex items-center gap-1.5 font-semibold text-sidebar-foreground">
            <Sparkles className="size-3.5 text-signal" aria-hidden /> Unlimited checklists and memos
          </p>
          <p className="mt-0.5 text-sidebar-foreground/60">Owner account</p>
        </>
      ) : kind === "subscription" ? (
        <>
          <p className="inline-flex items-center gap-1.5 font-semibold text-sidebar-foreground">
            <Sparkles className="size-3.5 text-signal" aria-hidden /> Unlimited checklists
          </p>
          <p className="mt-0.5 text-sidebar-foreground/60">Subscription {me.entitlement.subscription_status ?? "active"}</p>
        </>
      ) : kind === "credits" ? (
        <>
          <p className="font-semibold text-sidebar-foreground">{me.entitlement.plan_credits} checklist credit{me.entitlement.plan_credits === 1 ? "" : "s"}</p>
          <p className="mt-0.5 text-sidebar-foreground/60">{me.free_plans_remaining} free remaining</p>
        </>
      ) : (
        <>
          <p className="font-semibold text-sidebar-foreground">
            {me.free_plans_remaining} of {me.free_limit} free checklists left
          </p>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sidebar-border">
            <div
              className="h-full rounded-full bg-signal"
              style={{ width: `${Math.min(100, (me.plans_created / Math.max(1, me.free_limit)) * 100)}%` }}
            />
          </div>
        </>
      )}
    </Link>
  );
}

function Account() {
  const { user, signOut } = useApp();
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex items-center gap-2 rounded-lg px-1 py-1">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-signal text-xs font-bold uppercase text-white" aria-hidden>
        {(user.email ?? "?").slice(0, 1)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-sidebar-foreground">{user.email ?? "Signed in"}</p>
        <p className="text-[11px] text-sidebar-foreground/50">Account</p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground"
        aria-label="Sign out"
        title="Sign out"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await signOut();
        }}
      >
        <LogOut />
      </Button>
    </div>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-6 p-4">
      <div className="px-1">
        <Logo inverted href="/app/memos" />
      </div>
      <NavLinks onNavigate={onNavigate} />
      <div className="mt-auto space-y-3">
        <Entitlement />
        <Account />
      </div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh bg-sidebar text-sidebar-foreground lg:block">
        <SidebarBody />
      </aside>
      <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-sidebar-border bg-sidebar px-3 text-sidebar-foreground lg:hidden">
        <Logo inverted href="/app/memos" />
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground" aria-label="Open menu">
              <Menu />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 border-sidebar-border bg-sidebar p-0 text-sidebar-foreground [&>button]:text-sidebar-foreground">
            <SheetHeader className="sr-only">
              <SheetTitle>Navigation</SheetTitle>
            </SheetHeader>
            <SidebarBody onNavigate={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
      </header>
      <main className="min-w-0 bg-background">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>
      </main>
    </div>
  );
}

export function AppShellSkeleton() {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="hidden h-dvh bg-sidebar lg:block" />
      <div className="mx-auto w-full max-w-6xl space-y-4 px-4 py-8 sm:px-6 lg:px-8">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-80" />
        <div className="grid gap-4 pt-4 sm:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </div>
    </div>
  );
}

/** Client wrapper for /app: waits for the Supabase session, then provides it to every page. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { loading, user, accessToken, configured } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!configured || (!loading && !user)) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [configured, loading, user, pathname, router]);

  if (loading || !user || !accessToken) return <AppShellSkeleton />;

  return (
    <AppProvider user={user} accessToken={accessToken}>
      <Shell>{children}</Shell>
    </AppProvider>
  );
}
