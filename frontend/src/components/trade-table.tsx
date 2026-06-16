import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn, formatCurrency, pnlClass } from "@/lib/utils";
import type { Trade } from "@/types";

interface TradeTableProps {
  trades: Trade[];
  emptyLabel?: string;
}

export function TradeTable({ trades, emptyLabel = "No trades yet." }: TradeTableProps) {
  if (trades.length === 0) {
    return (
      <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
        {emptyLabel}
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Asset</TableHead>
          <TableHead>Side</TableHead>
          <TableHead className="text-right">Entry</TableHead>
          <TableHead className="text-right">Exit</TableHead>
          <TableHead className="text-right">Volume</TableHead>
          <TableHead className="text-right">P&amp;L</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {trades.map((t) => (
          <TableRow key={t.id}>
            <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
              {format(new Date(t.openedAt), "MMM dd, HH:mm")}
            </TableCell>
            <TableCell className="font-medium">{t.asset}</TableCell>
            <TableCell>
              <Badge variant={t.side === "buy" ? "profit" : "loss"}>{t.side.toUpperCase()}</Badge>
            </TableCell>
            <TableCell className="text-right tabular-nums">{t.entryPrice.toFixed(2)}</TableCell>
            <TableCell className="text-right tabular-nums">
              {t.exitPrice?.toFixed(2) ?? "—"}
            </TableCell>
            <TableCell className="text-right tabular-nums">{t.volume.toFixed(2)}</TableCell>
            <TableCell className={cn("text-right", pnlClass(t.pnl ?? 0))}>
              {t.pnl !== undefined ? formatCurrency(t.pnl) : "—"}
            </TableCell>
            <TableCell>
              <Badge variant={t.status === "closed" ? "outline" : "secondary"}>{t.status}</Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
