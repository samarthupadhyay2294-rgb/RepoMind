import { cn } from "@/lib/utils";
import { type ButtonHTMLAttributes, forwardRef } from "react";

type ButtonVariant = "default" | "outline" | "secondary" | "ghost" | "destructive" | "link";
type ButtonSize = "default" | "sm" | "lg" | "icon";

const variantStyles: Record<ButtonVariant, string> = {
  default: "bg-primary text-primary-foreground hover:bg-primary/90",
  outline: "border border-border bg-transparent hover:bg-accent text-foreground",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
  ghost: "hover:bg-accent text-foreground",
  destructive: "bg-destructive/10 text-destructive hover:bg-destructive/20",
  link: "text-primary underline-offset-4 hover:underline",
};

const sizeStyles: Record<ButtonSize, string> = {
  default: "h-9 px-4 py-2",
  sm: "h-8 rounded-md px-3 text-sm",
  lg: "h-10 rounded-md px-6",
  icon: "h-9 w-9",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export function buttonVariants(
  props: { variant?: ButtonVariant; size?: ButtonSize; className?: string } = {},
) {
  const { variant = "default", size = "default", className } = props;
  return cn(
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "disabled:pointer-events-none disabled:opacity-50",
    variantStyles[variant],
    sizeStyles[size],
    className,
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:pointer-events-none disabled:opacity-50",
        "active:scale-[0.98]",
        variantStyles[variant],
        sizeStyles[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
