import { PropsWithChildren } from "react";

export function Card({ children, className = "" }: PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={`rounded-xl border border-[rgba(0,132,140,0.2)] bg-[#edebd9] p-5 shadow-[0_2px_12px_rgba(28,31,76,0.08)] ${className}`}
    >
      {children}
    </div>
  );
}

export function Label({
  children,
  htmlFor,
}: PropsWithChildren<{ htmlFor?: string }>) {
  return (
    <label htmlFor={htmlFor} className="text-sm font-medium text-[#037272]">
      {children}
    </label>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={[
        "h-10 w-full rounded-lg border border-[rgba(0,132,140,0.35)] bg-[#edebd9] px-3 text-sm text-[#1c1f4c]",
        "placeholder:text-[#037272]/60",
        "focus:border-[#00848c] focus:outline-none focus:ring-2 focus:ring-[#00848c]/25",
        props.className ?? "",
      ].join(" ")}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={[
        "h-10 w-full rounded-lg border border-[rgba(0,132,140,0.35)] bg-[#edebd9] px-3 text-sm text-[#1c1f4c]",
        "focus:border-[#00848c] focus:outline-none focus:ring-2 focus:ring-[#00848c]/25",
        props.className ?? "",
      ].join(" ")}
    />
  );
}

export function Button(
  props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "primary" | "secondary" | "cta";
  },
) {
  const v = props.variant ?? "primary";
  const styles =
    v === "cta"
      ? "bg-[#fccf17] text-[#1c1f4c] hover:bg-[#fec20f] font-semibold"
      : v === "secondary"
        ? "border border-[#00848c] bg-transparent text-[#037272] hover:bg-[#00848c]/10"
        : "bg-[#00848c] text-white hover:bg-[#037272]";
  return (
    <button
      {...props}
      className={[
        "inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-medium transition-colors",
        styles,
        "disabled:cursor-not-allowed disabled:opacity-60",
        props.className ?? "",
      ].join(" ")}
    />
  );
}
