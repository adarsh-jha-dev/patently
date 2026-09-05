"use client";

import * as RadioGroup from "@radix-ui/react-radio-group";
import { AnimatePresence, motion } from "motion/react";
import { Check, HelpCircle } from "lucide-react";
import { useId, useState } from "react";
import { cn } from "@/lib/utils";
import { UNSURE } from "@/lib/rubric";

/**
 * Shared form parts on Radix primitives, wearing the page's own tokens rather
 * than a second theme layer. An "unsure" answer is styled as a deliberate
 * choice (dashed, ticked when active), never as a skip or a disabled state.
 */

/** A disclosure rather than a tooltip, so it works on touch and by keyboard. */
export function Help({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={id}
        aria-label={open ? "Hide explanation" : "Why this is asked"}
        className={cn(
          "inline-flex size-[18px] shrink-0 items-center justify-center rounded-full transition-colors",
          open
            ? "text-[var(--accent)]"
            : "text-[var(--text-faint)] hover:text-[var(--text-muted)]",
        )}
      >
        <HelpCircle size={14} strokeWidth={1.75} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.p
            id={id}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="basis-full overflow-hidden text-[12px] leading-relaxed text-[var(--text-muted)]"
          >
            <span className="block pt-1.5">{text}</span>
          </motion.p>
        )}
      </AnimatePresence>
    </>
  );
}

export function FieldShell({
  label,
  help,
  answered,
  children,
}: {
  label: string;
  help: string;
  answered: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="py-4 first:pt-0 last:pb-0">
      <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
        <span
          aria-hidden
          className={cn(
            "size-1.5 shrink-0 rounded-full transition-colors",
            answered ? "bg-[var(--accent)]" : "bg-[var(--border-strong)]",
          )}
        />
        <span className="text-[13px] font-medium">{label}</span>
        <Help text={help} />
      </div>
      {children}
    </div>
  );
}

/** A chip. Shared by the choice options and the "not sure" escape hatch so the
 *  two read as the same class of thing. */
const chip = (selected: boolean, dashed = false) =>
  cn(
    "rounded-full px-3 py-1.5 text-[12.5px] transition-all duration-150",
    "border focus-visible:outline-2 focus-visible:outline-offset-2",
    dashed ? "border-dashed" : "border-solid",
    selected
      ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--text)] font-medium"
      : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)]",
  );

export function ChoiceAnswer({
  options,
  value,
  onChange,
  unsureLabel,
  disabled,
}: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
  unsureLabel: string;
  disabled?: boolean;
}) {
  return (
    // Radix gives real radio semantics: roving focus, one tab stop, correct
    // announcement.
    <RadioGroup.Root
      value={value}
      onValueChange={onChange}
      disabled={disabled}
      className="flex flex-wrap gap-1.5"
    >
      {options.map((opt) => (
        <RadioGroup.Item key={opt} value={opt} className={chip(value === opt)}>
          {opt}
        </RadioGroup.Item>
      ))}
      <RadioGroup.Item
        value={UNSURE}
        className={cn(chip(value === UNSURE, true), "ml-auto")}
      >
        <span className="inline-flex items-center gap-1">
          {value === UNSURE && <Check size={11} strokeWidth={2.5} />}
          {unsureLabel}
        </span>
      </RadioGroup.Item>
    </RadioGroup.Root>
  );
}

export function TextAnswer({
  value,
  onChange,
  placeholder,
  unsureLabel,
  disabled,
  rows = 3,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  unsureLabel: string;
  disabled?: boolean;
  rows?: number;
}) {
  const isUnsure = value === UNSURE;

  return (
    <div>
      <div
        className={cn(
          "rounded-lg border bg-[var(--surface)] transition-colors",
          isUnsure
            ? "border-dashed border-[var(--border)]"
            : "border-[var(--border)] focus-within:border-[var(--border-strong)]",
        )}
      >
        <textarea
          value={isUnsure ? "" : value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled || isUnsure}
          rows={rows}
          placeholder={isUnsure ? "" : placeholder}
          className="w-full resize-none bg-transparent p-3 text-[13.5px] leading-relaxed outline-none placeholder:text-[var(--text-faint)] disabled:cursor-not-allowed"
        />
      </div>
      <button
        type="button"
        onClick={() => onChange(isUnsure ? "" : UNSURE)}
        disabled={disabled}
        className={cn(
          "mt-1.5 inline-flex items-center gap-1 rounded-full border border-dashed px-2.5 py-1 text-[11.5px] transition-colors",
          isUnsure
            ? "border-[var(--accent)] bg-[var(--accent)]/10 font-medium text-[var(--text)]"
            : "border-[var(--border)] text-[var(--text-faint)] hover:border-[var(--border-strong)] hover:text-[var(--text-muted)]",
        )}
      >
        {isUnsure && <Check size={11} strokeWidth={2.5} />}
        {unsureLabel}
      </button>
    </div>
  );
}
