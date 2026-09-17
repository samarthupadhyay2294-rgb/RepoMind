"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bug,
  LayoutDashboard,
  Map,
  MessageSquare,
  Menu,
  Settings,
  Workflow,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  matchExact?: boolean;
}

const mainNavItems: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, matchExact: true },
  { href: "/chat", label: "Chat", icon: MessageSquare },
];

const bottomNavItems: NavItem[] = [
  { href: "/settings", label: "Settings", icon: Settings },
];

function isActive(pathname: string, href: string, exact?: boolean) {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(href + "/");
}

function extractRepoId(pathname: string): string | null {
  const match = pathname.match(/^\/repositories\/([^/]+)/);
  return match ? match[1] : null;
}

export function MobileHeader() {
  const pathname = usePathname();
  const repoId = extractRepoId(pathname);

  const repoNavItems: NavItem[] = repoId
    ? [
        { href: `/repositories/${repoId}`, label: "Overview", icon: Map, matchExact: true },
        { href: `/repositories/${repoId}/chat`, label: "Chat", icon: MessageSquare },
        { href: `/repositories/${repoId}/graph`, label: "Code Graph", icon: Workflow },
        { href: `/repositories/${repoId}/debug`, label: "Debug", icon: Bug },
      ]
    : [];

  const allNavItems = [...mainNavItems, ...repoNavItems, ...bottomNavItems];

  return (
    <MobileNav
      items={allNavItems}
      pathname={pathname}
    />
  );
}

function MobileNav({
  items,
  pathname,
}: {
  items: NavItem[];
  pathname: string;
}) {
  const openDrawer = () => {
    const drawer = document.getElementById("mobile-nav-drawer");
    const overlay = document.getElementById("mobile-nav-overlay");
    if (drawer && overlay) {
      drawer.classList.remove("translate-x-full");
      overlay.classList.remove("opacity-0", "pointer-events-none");
      overlay.classList.add("opacity-100");
      document.body.style.overflow = "hidden";
      drawer.focus();
    }
  };

  const closeDrawer = () => {
    const drawer = document.getElementById("mobile-nav-drawer");
    const overlay = document.getElementById("mobile-nav-overlay");
    if (drawer && overlay) {
      drawer.classList.add("translate-x-full");
      overlay.classList.add("opacity-0", "pointer-events-none");
      overlay.classList.remove("opacity-100");
      document.body.style.overflow = "";
    }
  };

  return (
    <>
      <div className="flex md:hidden items-center justify-between border-b border-border bg-card px-4 h-14">
        <div className="flex items-center gap-2 font-semibold">
          <img src="/logo.png" alt="RepoMind" className="h-6 w-6 shrink-0 rounded-md object-contain" />
          RepoMind
        </div>
        <button
          onClick={openDrawer}
          className="inline-flex items-center justify-center rounded-lg p-2 text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>
      </div>

      {/* Overlay */}
      <div
        id="mobile-nav-overlay"
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm opacity-0 pointer-events-none transition-opacity duration-200 md:hidden"
        onClick={closeDrawer}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div
        id="mobile-nav-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        tabIndex={-1}
        className="fixed inset-y-0 left-0 z-50 w-60 bg-card border-r border-border shadow-2xl -translate-x-full transition-transform duration-200 md:hidden"
        onKeyDown={(e) => {
          if (e.key === "Escape") closeDrawer();
        }}
      >
        <div className="flex h-14 items-center justify-between px-4 border-b border-border font-semibold">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="RepoMind" className="h-6 w-6 shrink-0 rounded-md object-contain" />
            RepoMind
          </div>
          <button
            onClick={closeDrawer}
            className="inline-flex items-center justify-center rounded-lg p-1.5 text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Close navigation menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 p-2" role="navigation" aria-label="Mobile navigation">
          {items.map((item) => {
            const active = isActive(pathname, item.href, item.matchExact);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={closeDrawer}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
                aria-current={active ? "page" : undefined}
              >
                <Icon className={cn("h-4 w-4 shrink-0", active ? "text-primary" : "text-muted-foreground")} />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </>
  );
}
