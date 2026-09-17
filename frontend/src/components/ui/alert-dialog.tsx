"use client";

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

interface AlertDialogContextValue {
  open: boolean;
  setOpen: (v: boolean) => void;
}

const AlertDialogContext = createContext<AlertDialogContextValue>({
  open: false,
  setOpen: () => {},
});

export function AlertDialog({
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
  const setOpen = (v: boolean) => {
    onOpenChange?.(v);
    setInternalOpen(v);
  };

  return (
    <AlertDialogContext.Provider value={{ open, setOpen }}>
      {children}
    </AlertDialogContext.Provider>
  );
}

export function AlertDialogTrigger({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen } = useContext(AlertDialogContext);
  return (
    <button onClick={() => setOpen(true)} {...props}>
      {children}
    </button>
  );
}

export function AlertDialogContent({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  const { open, setOpen } = useContext(AlertDialogContext);
  const ref = useRef<HTMLDivElement>(null);

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div
        ref={ref}
        role="alertdialog"
        aria-modal="true"
        className={cn(
          "relative z-50 w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl",
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

export function AlertDialogHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-2 text-center sm:text-left", className)} {...props} />;
}

export function AlertDialogTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("text-lg font-semibold", className)} {...props} />;
}

export function AlertDialogDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export function AlertDialogFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:gap-2 mt-4", className)} {...props} />;
}

export function AlertDialogAction({
  className,
  onClick,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen } = useContext(AlertDialogContext);
  return (
    <button
      onClick={(e) => {
        onClick?.(e);
        setOpen(false);
      }}
      className={cn(
        "inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...props}
    />
  );
}

export function AlertDialogCancel({
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen } = useContext(AlertDialogContext);
  return (
    <button
      onClick={() => setOpen(false)}
      className={cn(
        "inline-flex items-center justify-center rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-accent transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...props}
    />
  );
}
