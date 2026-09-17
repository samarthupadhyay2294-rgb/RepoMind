import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "destructive";
}

const variantStyles: Record<string, string> = {
  default: "bg-card text-card-foreground border-border",
  destructive: "bg-destructive/10 text-destructive border-destructive/20",
};

export function Alert({ className, variant = "default", ...props }: AlertProps) {
  return (
    <div
      role="alert"
      className={cn(
        "relative w-full rounded-lg border px-4 py-3 text-sm",
        variantStyles[variant],
        className,
      )}
      {...props}
    />
  );
}

export function AlertTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h5 className={cn("font-medium leading-none tracking-tight", className)} {...props} />;
}

export function AlertDescription({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("text-sm text-muted-foreground [&_p]:leading-relaxed", className)} {...props} />;
}
