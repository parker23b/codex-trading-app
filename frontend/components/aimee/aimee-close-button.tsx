type AimeeCloseButtonProps = {
  label: string;
  onClick: () => void;
};

export function AimeeCloseButton({ label, onClick }: AimeeCloseButtonProps) {
  return (
    <button
      type="button"
      className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-[color:var(--glass-stroke)] bg-[color:var(--bg-muted)] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
      onClick={onClick}
      aria-label={label}
    >
      <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
        <path d="M5.22 5.22a.75.75 0 0 1 1.06 0L10 8.94l3.72-3.72a.75.75 0 1 1 1.06 1.06L11.06 10l3.72 3.72a.75.75 0 0 1-1.06 1.06L10 11.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06L8.94 10 5.22 6.28a.75.75 0 0 1 0-1.06Z" fill="currentColor" />
      </svg>
    </button>
  );
}
