"use client";

import { cn } from "@/lib/utils";
import { createContext, useContext, useState, type HTMLAttributes } from "react";

interface TabsContextValue {
  value: string;
  onValueChange: (v: string) => void;
}

const TabsContext = createContext<TabsContextValue>({
  value: "",
  onValueChange: () => {},
});

export function Tabs({
  defaultValue,
  value: controlledValue,
  onValueChange,
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  defaultValue?: string;
  value?: string;
  onValueChange?: (v: string) => void;
}) {
  const [internalValue, setInternalValue] = useState(defaultValue ?? "");
  const value = controlledValue ?? internalValue;
  const setValue = onValueChange ?? setInternalValue;

  return (
    <TabsContext.Provider value={{ value, onValueChange: setValue }}>
      <div className={cn("flex flex-col gap-2", className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export function TabsList({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({
  className,
  value,
  children,
  ...props
}: HTMLAttributes<HTMLButtonElement> & { value: string }) {
  const ctx = useContext(TabsContext);
  const isActive = ctx.value === value;

  return (
    <button
      role="tab"
      aria-selected={isActive}
      data-state={isActive ? "active" : "inactive"}
      onClick={() => ctx.onValueChange(value)}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isActive
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function TabsContent({
  className,
  value,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { value: string }) {
  const ctx = useContext(TabsContext);
  if (ctx.value !== value) return null;

  return (
    <div
      role="tabpanel"
      className={cn("mt-2 focus-visible:outline-none", className)}
      {...props}
    >
      {children}
    </div>
  );
}
