"use client";

import React from "react";
import { cn } from "@/lib/utils";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from "react";

interface SheetContextValue {
  open: boolean;
  setOpen: (v: boolean) => void;
}

const SheetContext = createContext<SheetContextValue>({
  open: false,
  setOpen: () => {},
});

export function Sheet({
  open: controlledOpen,
  onOpenChange,
  children,
}: {
  open?: boolean;
  onOpenChange?: (v: boolean) => void;
  children: ReactNode;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = useCallback(
    (v: boolean) => {
      onOpenChange?.(v);
      setInternalOpen(v);
    },
    [onOpenChange],
  );

  return (
    <SheetContext.Provider value={{ open, setOpen }}>
      {children}
    </SheetContext.Provider>
  );
}

export function SheetTrigger({
  children,
  render,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { render?: React.ReactElement }) {
  const { setOpen } = useContext(SheetContext);
  const triggerProps = {
    onClick: () => setOpen(true),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpen(true);
      }
    },
  };
  if (render) {
    return (
      <div role="button" tabIndex={0} {...triggerProps}>
        {children ? React.cloneElement(render, {}, children) : render}
      </div>
    );
  }
  return (
    <button onClick={() => setOpen(true)} {...props}>
      {children}
    </button>
  );
}

export function SheetContent({
  className,
  children,
  side = "right",
  ...props
}: HTMLAttributes<HTMLDivElement> & { side?: "left" | "right" | "top" | "bottom" }) {
  const { open, setOpen } = useContext(SheetContext);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = "";
    };
  }, [open, setOpen]);

  if (!open) return null;

  const sideClasses = {
    left: "inset-y-0 left-0 h-full w-3/4 max-w-sm border-r",
    right: "inset-y-0 right-0 h-full w-3/4 max-w-sm border-l",
    top: "inset-x-0 top-0 border-b",
    bottom: "inset-x-0 bottom-0 border-t",
  };

  const slideClasses = {
    left: "animate-in slide-in-from-left",
    right: "animate-in slide-in-from-right",
    top: "animate-in slide-in-from-top",
    bottom: "animate-in slide-in-from-bottom",
  };

  return (
    <div className="fixed inset-0 z-50">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div
        className={cn(
          "fixed z-50 bg-card shadow-2xl",
          sideClasses[side],
          slideClasses[side],
          className,
        )}
        {...props}
      >
        {children}
      </div>
    </div>
  );
}
