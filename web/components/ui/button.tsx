"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * shadcn-shaped Button, but wearing this app's tokens instead of shadcn's own
 * CSS variables — one theme layer, not two.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium " +
    "transition-[background-color,color,border-color,opacity,transform] duration-150 " +
    "disabled:pointer-events-none disabled:opacity-40 active:scale-[0.985] " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--text)] text-[var(--bg)] hover:opacity-90 shadow-[var(--shadow)]",
        secondary:
          "border border-[var(--border)] bg-[var(--surface)] text-[var(--text)] hover:border-[var(--border-strong)]",
        ghost:
          "text-[var(--text-muted)] hover:bg-[var(--surface-sunk)] hover:text-[var(--text)]",
        accent:
          "bg-[var(--accent)] text-white hover:opacity-90 shadow-[var(--shadow)]",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-base",
        icon: "size-9 p-0",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
