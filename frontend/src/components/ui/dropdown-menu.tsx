"use client";

import React from "react";
import { cn } from "@/lib/utils";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from "react";

interface DropdownContextValue {
  open: boolean;
  setOpen: (v: boolean) => void;
  triggerRef: React.RefObject<HTMLDivElement | null>;
}

const DropdownContext = createContext<DropdownContextValue>({
  open: false,
  setOpen: () => {},
  triggerRef: { current: null },
});

export function DropdownMenu({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", keyHandler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", keyHandler);
    };
  }, [open]);

  return (
    <DropdownContext.Provider value={{ open, setOpen, triggerRef }}>
      <div className="relative inline-block">{children}</div>
    </DropdownContext.Provider>
  );
}

export function DropdownMenuTrigger({
  children,
  asChild,
  render,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean; render?: React.ReactElement }) {
  const { open, setOpen, triggerRef } = useContext(DropdownContext);
  if (render) {
    const triggerProps = { onClick: () => setOpen(!open) } as Record<string, unknown>;
    return (
      <div ref={triggerRef}>
        {children
          ? React.cloneElement(render, triggerProps, children)
          : React.cloneElement(render, triggerProps)}
      </div>
    );
  }
  if (asChild) {
    return (
      <div ref={triggerRef} role="button" tabIndex={0} onClick={() => setOpen(!open)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(!open); } }}>
        {children}
      </div>
    );
  }
  return (
    <div ref={triggerRef}>
      <button onClick={() => setOpen(!open)} aria-expanded={open} {...props}>
        {children}
      </button>
    </div>
  );
}

export function DropdownMenuContent({
  className,
  align = "center",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { align?: "start" | "center" | "end" }) {
  const { open, triggerRef } = useContext(DropdownContext);
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open || !triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const alignOffset = align === "end" ? rect.width : align === "start" ? 0 : rect.width / 2;
    setPos({
      top: rect.bottom + 4 + window.scrollY,
      left: rect.left + window.scrollX - alignOffset,
    });
  }, [open, align, triggerRef]);

  if (!open) return null;

  return (
    <div
      ref={ref}
      className={cn(
        "absolute z-50 min-w-[8rem] overflow-hidden rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-xl",
        "animate-in fade-in-0 zoom-in-95",
        className,
      )}
      style={{ top: pos.top, left: pos.left }}
      {...props}
    >
      {children}
    </div>
  );
}

export function DropdownMenuItem({
  className,
  children,
  onClick,
  ...props
}: HTMLAttributes<HTMLDivElement> & { onClick?: () => void }) {
  const { setOpen } = useContext(DropdownContext);
  return (
    <div
      role="menuitem"
      tabIndex={0}
      className={cn(
        "relative flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none",
        "hover:bg-accent hover:text-accent-foreground",
        "focus:bg-accent focus:text-accent-foreground",
        className,
      )}
      onClick={(e) => {
        onClick?.(e as React.MouseEvent<HTMLDivElement>);
        setOpen(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick?.();
          setOpen(false);
        }
      }}
      {...props}
    >
      {children}
    </div>
  );
}

export function DropdownMenuSeparator({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("-mx-1 my-1 h-px bg-border", className)} {...props} />;
}
