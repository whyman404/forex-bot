"use client";

import * as React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TVRecommendationBadge } from "@/components/tv-recommendation-badge";
import type { TVTimeframeAnalysis } from "@/types";

interface TVTimeframeTableProps {
  rows: readonly TVTimeframeAnalysis[];
  caption?: string;
}

/**
 * Accessible per-timeframe TradingView analysis table.
 * - Uses semantic <caption> for screen-reader context
 * - Counts are tabular-nums for alignment
 * - Recommendation conveyed via badge (text+icon+colour)
 */
export function TVTimeframeTable({ rows, caption }: TVTimeframeTableProps): React.ReactElement {
  return (
    <div className="rounded-md border">
      <Table>
        {caption && (
          <caption className="caption-bottom px-3 py-2 text-left text-xs text-muted-foreground">
            {caption}
          </caption>
        )}
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Timeframe</TableHead>
            <TableHead scope="col">Recommendation</TableHead>
            <TableHead scope="col" className="text-right">
              Buy
            </TableHead>
            <TableHead scope="col" className="text-right">
              Sell
            </TableHead>
            <TableHead scope="col" className="text-right">
              Neutral
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">
                No timeframes selected yet.
              </TableCell>
            </TableRow>
          ) : (
            rows.map((r) => (
              <TableRow key={r.interval}>
                <TableCell className="font-medium uppercase">{r.interval}</TableCell>
                <TableCell>
                  <TVRecommendationBadge recommendation={r.recommendation} size="sm" />
                </TableCell>
                <TableCell className="text-right tabular-nums">{r.buy_count}</TableCell>
                <TableCell className="text-right tabular-nums">{r.sell_count}</TableCell>
                <TableCell className="text-right tabular-nums">{r.neutral_count}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
