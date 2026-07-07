import { forwardRef, ButtonHTMLAttributes } from "react";
import { clsx } from "clsx";

type Variant = "primary" | "danger" | "success" | "ghost";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const variantStyles: Record<Variant, string> = {
  primary: "bg-[#F97316] text-white shadow-[0_0_20px_rgba(249,115,22,0.3)] hover:bg-[#EA6C10] active:scale-95",
  danger:  "bg-[#EF4444] text-white shadow-[0_0_20px_rgba(239,68,68,0.3)] hover:bg-[#DC2626] active:scale-95",
  success: "bg-[#22C55E] text-[#0B1D3A] hover:bg-[#16A34A] active:scale-95",
  ghost:   "bg-[#132B5A] text-[#E8EEF7] border border-[rgba(91,141,217,0.2)] hover:bg-[#1A3870] active:scale-95",
};

const sizeStyles: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm rounded-lg",
  md: "px-4 py-2.5 text-base rounded-xl",
  lg: "px-6 py-4 text-lg rounded-2xl",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, className, children, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={clsx(
          "inline-flex items-center justify-center gap-2 font-semibold transition-all duration-150 disabled:opacity-50 disabled:pointer-events-none",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        style={{ fontFamily: "Barlow Condensed, sans-serif", letterSpacing: "0.05em" }}
        {...props}
      >
        {loading && (
          <span className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
