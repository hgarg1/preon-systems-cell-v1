import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
}

const statusClassName: Record<string, string> = {
  completed: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  running: "border-cyan-300/40 bg-cyan-300/10 text-cyan-100",
  queued: "border-amber-300/40 bg-amber-300/10 text-amber-100",
  failed: "border-rose-300/40 bg-rose-300/10 text-rose-100",
  cancelled: "border-neutral-300/30 bg-neutral-300/10 text-neutral-200",
  alive: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  dead: "border-rose-300/40 bg-rose-300/10 text-rose-100",
  divided: "border-amber-300/40 bg-amber-300/10 text-amber-100",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "h-6 rounded-md px-2 font-mono text-[11px] uppercase tracking-normal",
        statusClassName[status] ?? "border-neutral-300/30 bg-neutral-300/10 text-neutral-200",
      )}
    >
      {status}
    </Badge>
  );
}
