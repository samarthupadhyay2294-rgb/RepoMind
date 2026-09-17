import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "outline" | "destructive";
}

const variantStyles: Record<string, string> = {
  default: "bg-primary/15 text-primary border-primary/20",
  secondary: "bg-secondary text-secondary-foreground border-secondary",
  outline: "bg-transparent text-foreground border-border",
  destructive: "bg-destructive/10 text-destructive border-destructive/20",
};

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        variantStyles[variant],
        className,
      )}
      {...props}
    />
  );
}
