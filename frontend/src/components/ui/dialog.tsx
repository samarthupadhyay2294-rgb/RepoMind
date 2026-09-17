"use client";

import React from "react";
import { cn } from "@/lib/utils";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from "react";

interface DialogContextValue {
  open: boolean;
  setOpen: (v: boolean) => void;
}

const DialogContext = createContext<DialogContextValue>({
  open: false,
  setOpen: () => {},
});

export function Dialog({
  open: controlledOpen,
  onOpenChange,
  children,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
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
    <DialogContext.Provider value={{ open, setOpen }}>
      {children}
    </DialogContext.Provider>
  );
}

export function DialogTrigger({
  children,
  asChild,
  render,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean; render?: React.ReactElement }) {
  const { setOpen } = useContext(DialogContext);
  if (render) {
    return (
      <span
        className="inline-flex shrink-0 w-full sm:w-auto"
        role="button"
        tabIndex={0}
        onClick={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(true); } }}
      >
        {children ? React.cloneElement(render, {}, children) : render}
      </span>
    );
  }
  if (asChild) {
    return (
      <span
        className="inline-flex shrink-0 w-full sm:w-auto"
        role="button"
        tabIndex={0}
        onClick={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(true); } }}
      >
        {children}
      </span>
    );
  }
  return (
    <button onClick={() => setOpen(true)} {...props}>
      {children}
    </button>
  );
}

export function DialogContent({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  const { open, setOpen } = useContext(DialogContext);
  const overlayRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    contentRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = prev;
    };
  }, [open, setOpen]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        ref={overlayRef}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />
      <div
        ref={contentRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          "relative z-50 w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-2xl",
          "focus-visible:outline-none",
          "animate-in fade-in-0 zoom-in-95",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    </div>
  );
}

export function DialogHeader({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1.5 text-center sm:text-left", className)} {...props} />;
}

export function DialogTitle({
  className,
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-lg font-semibold leading-none tracking-tight", className)} {...props} />;
}

export function DialogDescription({
  className,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function DialogFooter({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:gap-2 mt-4", className)} {...props} />;
}

export function DialogClose({
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen } = useContext(DialogContext);
  return (
    <button
      onClick={() => setOpen(false)}
      className={cn(
        "absolute right-4 top-4 rounded-md p-1 text-muted-foreground hover:text-foreground transition-colors",
        className,
      )}
      aria-label="Close"
      {...props}
    >
      <svg width="15" height="15" viewBox="0 0 15 15" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M11.7816 4.03157C12.0062 3.80702 12.0062 3.44295 11.7816 3.2184C11.5571 2.99385 11.193 2.99385 10.9685 3.2184L7.50005 6.68682L4.03164 3.2184C3.80708 2.99385 3.44301 2.99385 3.21846 3.2184C2.99391 3.44295 2.99391 3.80702 3.21846 4.03157L6.68688 7.49999L3.21846 10.9684C2.99391 11.193 2.99391 11.557 3.21846 11.7816C3.44301 12.0061 3.80708 12.0061 4.03164 11.7816L7.50005 8.31316L10.9685 11.7816C11.193 12.0061 11.5571 12.0061 11.7816 11.7816C12.0062 11.557 12.0062 11.193 11.7816 10.9684L8.31322 7.49999L11.7816 4.03157Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd" />
      </svg>
    </button>
  );
}
