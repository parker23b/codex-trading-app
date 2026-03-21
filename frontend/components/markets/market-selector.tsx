"use client";

import { SegmentedControl } from "@/components/ui/segmented-control";
import { MarketCategory } from "@/lib/types";

type MarketSelectorProps = {
  categories: MarketCategory[];
  selectedCategory: MarketCategory;
  onSelect: (category: MarketCategory) => void;
};

const marketLabels: Record<MarketCategory, string> = {
  forex: "Forex",
  indices: "Indices",
  commodities: "Commodities",
  stocks: "Stocks",
  crypto: "Crypto",
};

export function MarketSelector({ categories, selectedCategory, onSelect }: MarketSelectorProps) {
  return (
    <div className="market-selector">
      <SegmentedControl
        options={categories}
        value={selectedCategory}
        onChange={onSelect}
        ariaLabel="Market category"
        renderLabel={(category) => marketLabels[category]}
      />
    </div>
  );
}
