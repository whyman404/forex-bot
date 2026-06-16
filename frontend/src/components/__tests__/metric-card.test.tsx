import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCard } from "@/components/metric-card";

describe("MetricCard", () => {
  it("renders label and value", () => {
    render(<MetricCard label="P&L today" value="$1,234.56" />);
    expect(screen.getByText("P&L today")).toBeInTheDocument();
    expect(screen.getByText("$1,234.56")).toBeInTheDocument();
  });

  it("shows positive delta in profit class", () => {
    render(<MetricCard label="Return" value="$100" delta={2.5} />);
    const delta = screen.getByText(/\+2\.50%/);
    expect(delta.className).toContain("profit");
  });

  it("shows negative delta in loss class", () => {
    render(<MetricCard label="Return" value="-$50" delta={-1.2} />);
    const delta = screen.getByText(/-1\.20%/);
    expect(delta.className).toContain("loss");
  });
});
