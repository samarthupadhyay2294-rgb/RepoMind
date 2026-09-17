"use client";

import { cn } from "@/lib/utils";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import React from "react";

interface TooltipContextValue {
  open: boolean;
  setOpen: (v: boolean) => void;
}

const TooltipContext = createContext<TooltipContextValue>({
  open: false,
  setOpen: () => {},
});

export function TooltipProvider({ children }: { children: ReactNode; delay?: number }) {
  return <>{children}</>;
}

export function Tooltip({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <TooltipContext.Provider value={{ open, setOpen }}>
      <span className="relative inline-flex">{children}</span>
    </TooltipContext.Provider>
  );
}

export function TooltipTrigger({
  children,
  asChild,
  render,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean; render?: React.ReactElement }) {
  const { setOpen } = useContext(TooltipContext);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const show = useCallback(() => {
    timeoutRef.current = setTimeout(() => setOpen(true), 400);
  }, [setOpen]);

  const hide = useCallback(() => {
    clearTimeout(timeoutRef.current);
    setOpen(false);
  }, [setOpen]);

  useEffect(() => () => clearTimeout(timeoutRef.current), []);

  const triggerProps = {
    onMouseEnter: show,
    onMouseLeave: hide,
    onFocus: show,
    onBlur: hide,
  };

  if (render) {
    return children
      ? React.cloneElement(render, triggerProps, children)
      : React.cloneElement(render, triggerProps);
  }

  if (asChild) {
    return (
      <span
        {...triggerProps}
        {...(props as React.HTMLAttributes<HTMLSpanElement>)}
      >
        {children}
      </span>
    );
  }

  return (
    <button
      {...triggerProps}
      {...props}
    >
      {children}
    </button>
  );
}

export function TooltipContent({
  className,
  children,
  side = "top",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { side?: "top" | "bottom" | "left" | "right" }) {
  const { open } = useContext(TooltipContext);

  if (!open) return null;

  const positionClasses = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  };

  return (
    <div
      role="tooltip"
      className={cn(
        "absolute z-50 whitespace-nowrap rounded-md bg-foreground px-3 py-1.5 text-xs text-background shadow-md pointer-events-none",
        "animate-in fade-in-0 zoom-in-95",
        positionClasses[side],
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
