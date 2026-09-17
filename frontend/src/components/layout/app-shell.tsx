"use client";

import { useState } from "react";
import { Sidebar } from "./sidebar";
import { MobileHeader } from "./mobile-header";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((c) => !c)}
      />
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        <MobileHeader />
        <main className="flex-1 overflow-y-auto min-w-0">{children}</main>
      </div>
    </div>
  );
}
