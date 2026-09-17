"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bug,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  MessageSquare,
  Map,
  Settings,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";

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

const repoNavItems: NavItem[] = [
  { href: "/overview", label: "Overview", icon: Map },
  { href: "/graph", label: "Code Graph", icon: Workflow },
  { href: "/debug", label: "Debug", icon: Bug },
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

interface SidebarProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function Sidebar({ collapsed = false, onToggleCollapse }: SidebarProps) {
  const pathname = usePathname();
  const repoId = extractRepoId(pathname);

  const resolvedRepoNavItems = repoId
    ? repoNavItems.map((item) => ({
        ...item,
        href: `/repositories/${repoId}${item.href}`,
      }))
    : [];

  function renderNavItem(item: NavItem) {
    const active = isActive(pathname, item.href, item.matchExact);
    const Icon = item.icon;

    const linkContent = (
      <Link
        href={item.href}
        className={cn(
          "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          active
            ? "bg-primary/15 text-primary"
            : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          collapsed && "justify-center px-2",
        )}
        aria-current={active ? "page" : undefined}
      >
        {active && (
          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-full bg-primary" />
        )}
        <Icon
          className={cn(
            "h-4 w-4 shrink-0",
            active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
          )}
        />
        {!collapsed && <span className="truncate">{item.label}</span>}
      </Link>
    );

    if (collapsed) {
      return (
        <Tooltip key={item.href}>
          <TooltipTrigger render={linkContent} />
          <TooltipContent side="right">{item.label}</TooltipContent>
        </Tooltip>
      );
    }

    return (
      <div key={item.href}>
        {linkContent}
      </div>
    );
  }

  return (
    <TooltipProvider>
      <aside
        className={cn(
          "hidden md:flex flex-col border-r border-border bg-card text-card-foreground transition-all duration-200",
          collapsed ? "w-16" : "w-56",
        )}
      >
        {/* Logo */}
        <div
          className={cn(
            "flex h-14 items-center gap-2 border-b border-border font-semibold",
            collapsed ? "justify-center px-2" : "px-4",
          )}
        >
          <img src="/logo.png" alt="RepoMind" className="h-7 w-7 shrink-0 rounded-md object-contain" />
          {!collapsed && <span className="truncate">RepoMind</span>}
        </div>

        {/* Main navigation */}
        <nav className="flex-1 space-y-1 p-2" role="navigation" aria-label="Main navigation">
          {mainNavItems.map(renderNavItem)}

          {resolvedRepoNavItems.length > 0 && (
            <>
              <Separator className="my-2" />
              {!collapsed && (
                <p className="px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/60">
                  Repository
                </p>
              )}
              {resolvedRepoNavItems.map(renderNavItem)}
            </>
          )}
        </nav>

        {/* Collapse toggle */}
        {onToggleCollapse && (
          <>
            <Separator />
            <div className={cn("p-2", collapsed && "flex justify-center")}>
              <button
                onClick={onToggleCollapse}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors",
                  "hover:bg-accent/50 hover:text-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                  collapsed && "justify-center px-2",
                )}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {collapsed ? (
                  <ChevronRight className="h-4 w-4 shrink-0" />
                ) : (
                  <>
                    <ChevronLeft className="h-4 w-4 shrink-0" />
                    <span>Collapse</span>
                  </>
                )}
              </button>
            </div>
          </>
        )}

        {/* Bottom navigation */}
        <Separator />
        <div className={cn("p-2", collapsed && "flex justify-center")}>
          {bottomNavItems.map(renderNavItem)}
        </div>
      </aside>
    </TooltipProvider>
  );
}
