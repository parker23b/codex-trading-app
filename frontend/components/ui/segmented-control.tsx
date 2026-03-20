"use client";

type SegmentedControlProps<T extends string> = {
  options: T[];
  value: T;
  onChange: (value: T) => void;
};

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: SegmentedControlProps<T>) {
  return (
    <div className="segmented-control" role="tablist" aria-label="Time filter">
      {options.map((option) => (
        <button
          type="button"
          key={option}
          className={`segmented-control__item ${value === option ? "is-active" : ""}`}
          onClick={() => onChange(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

