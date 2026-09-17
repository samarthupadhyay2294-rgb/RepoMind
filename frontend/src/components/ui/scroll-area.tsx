"use client";

import { cn } from "@/lib/utils";
import { forwardRef, type HTMLAttributes } from "react";

interface ScrollAreaProps extends HTMLAttributes<HTMLDivElement> {
  orientation?: "vertical" | "horizontal";
}

export const ScrollArea = forwardRef<HTMLDivElement, ScrollAreaProps>(({ className, children, ...props }, ref) => {
  return (
    <div ref={ref} className={cn("relative overflow-hidden", className)} {...props}>
      <div className="h-full w-full overflow-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
        {children}
      </div>
    </div>
  );
});
ScrollArea.displayName = "ScrollArea";
