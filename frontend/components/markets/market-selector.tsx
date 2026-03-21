"use client";

import { SegmentedControl } from "@/components/ui/segmented-control";
import { MarketCategory, MarketSummary } from "@/lib/types";

type MarketSelectorProps = {
  summaries: MarketSummary[];
  selectedCategory: MarketCategory;
  onSelect: (category: MarketCategory) => void;
};

export function MarketSelector({ summaries, selectedCategory, onSelect }: MarketSelectorProps) {
  return (
    <div className="market-selector">
      <SegmentedControl
        options={summaries.map((summary) => summary.category)}
        value={selectedCategory}
        onChange={onSelect}
        ariaLabel="Market category"
        renderLabel={(category) => summaries.find((summary) => summary.category === category)?.label ?? category}
      />
    </div>
  );
}
