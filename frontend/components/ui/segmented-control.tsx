"use client";

type SegmentedControlProps<T extends string> = {
  options: T[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel?: string;
  renderLabel?: (value: T) => string;
};

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel = "Segmented control",
  renderLabel,
}: SegmentedControlProps<T>) {
  return (
    <div className="segmented-control" role="tablist" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          type="button"
          key={option}
          className={`segmented-control__item ${value === option ? "is-active" : ""}`}
          onClick={() => onChange(option)}
        >
          {renderLabel ? renderLabel(option) : option}
        </button>
      ))}
    </div>
  );
}
