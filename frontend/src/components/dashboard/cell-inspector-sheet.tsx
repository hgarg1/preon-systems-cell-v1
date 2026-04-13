"use client";

import { ArrowLeft, ExternalLink, Filter } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { getCell, getCellEvents, type CellEvent, type CellState } from "@/lib/api";

import { formatNumber, lineageColor } from "./format";
import { StatusBadge } from "./status-badge";

interface CellInspectorSheetProps {
  runId: string;
  cellId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectCell: (cellId: string) => void;
}

export function CellInspectorSheet({
  runId,
  cellId,
  open,
  onOpenChange,
  onSelectCell,
}: CellInspectorSheetProps) {
  const [cell, setCell] = useState<CellState | null>(null);
  const [events, setEvents] = useState<CellEvent[]>([]);
  const [eventDetail, setEventDetail] = useState<{ cellId: string; event: CellEvent } | null>(null);
  const [error, setError] = useState<{ cellId: string; message: string } | null>(null);
  const [scope, setScope] = useState<"self" | "lineage" | "descendants">("lineage");
  const [eventQuery, setEventQuery] = useState("");

  useEffect(() => {
    if (!open || !cellId) {
      return;
    }

    const controller = new AbortController();

    Promise.all([
      getCell(runId, cellId, controller.signal),
      getCellEvents(runId, cellId, scope, controller.signal),
    ])
      .then(([nextCell, nextEvents]) => {
        setCell(nextCell);
        setEvents(nextEvents);
        setError(null);
      })
      .catch((caught) => {
        if (!controller.signal.aborted) {
          setError({
            cellId,
            message: caught instanceof Error ? caught.message : "Unable to load cell details",
          });
        }
      });

    return () => controller.abort();
  }, [cellId, open, runId, scope]);

  const selectedEvent = eventDetail?.cellId === cellId ? eventDetail.event : null;
  const visibleError = error?.cellId === cellId ? error.message : null;
  const loading = open && !!cellId && cell?.id !== cellId && !visibleError;

  const linkedCellIds = useMemo(() => {
    if (!selectedEvent) {
      return [];
    }

    const ids = new Set<string>();
    for (const key of ["cell_id", "parent_id"]) {
      const value = selectedEvent.values[key];
      if (typeof value === "string") {
        ids.add(value);
      }
    }
    const daughterIds = selectedEvent.values.daughter_ids;
    if (Array.isArray(daughterIds)) {
      daughterIds.forEach((value) => {
        if (typeof value === "string") {
          ids.add(value);
        }
      });
    }
    return [...ids];
  }, [selectedEvent]);

  const eventTypeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      counts.set(event.type, (counts.get(event.type) ?? 0) + 1);
    }
    return [...counts.entries()].sort((left, right) => right[1] - left[1]).slice(0, 5);
  }, [events]);

  const visibleEvents = useMemo(() => {
    const needle = eventQuery.trim().toLowerCase();
    if (!needle) {
      return events;
    }
    return events.filter((event) =>
      [event.type, event.message, event.step.toString(), JSON.stringify(event.values)]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [eventQuery, events]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-hidden border-white/10 bg-neutral-950 p-0 text-white sm:max-w-xl">
        <SheetHeader className="border-b border-white/10 px-5 py-5 text-left">
          <SheetTitle className="flex items-center gap-3 text-white">
            <span
              className="block size-3 rounded-full"
              style={{ backgroundColor: cellId ? lineageColor(cellId, cell?.generation ?? 0) : "#86efac" }}
            />
            {cellId ?? "Cell"}
          </SheetTitle>
          <SheetDescription className="text-neutral-400">
            {selectedEvent ? "Event details" : "Lifecycle, state, and lineage-relevant events"}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-[calc(100vh-5.5rem)]">
          <div className="grid gap-5 px-5 py-5">
            {visibleError ? (
              <div className="rounded-lg border border-rose-300/30 bg-rose-300/10 p-4 text-sm text-rose-100">
                {visibleError}
              </div>
            ) : null}

            {loading ? (
              <div className="text-sm text-neutral-400">Loading cell details...</div>
            ) : selectedEvent ? (
              <EventDetail
                event={selectedEvent}
                linkedCellIds={linkedCellIds}
                onBack={() => setEventDetail(null)}
                onSelectCell={(nextCellId) => {
                  onSelectCell(nextCellId);
                  setEventDetail(null);
                }}
              />
            ) : cell ? (
              <>
                <section className="rounded-lg border border-white/10 bg-white/5 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-xs uppercase text-neutral-500">Status</div>
                      <div className="mt-2">
                        <StatusBadge status={cell.status} />
                      </div>
                    </div>
                    <div className="font-mono text-sm text-neutral-300">
                      gen {cell.generation} / born step {cell.birth_step}
                    </div>
                  </div>
                  <Separator className="my-4 bg-white/10" />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Fact label="Parent" value={cell.parent_id ?? "root"} />
                    <Fact label="Death step" value={cell.death_step?.toString() ?? "-"} />
                    <Fact label="ATP" value={formatNumber(cell.energy.atp, 3)} />
                    <Fact label="ADP" value={formatNumber(cell.energy.adp, 3)} />
                    <Fact label="Biomass" value={formatNumber(cell.biomass, 3)} />
                    <Fact label="Membrane" value={formatNumber(cell.membrane_integrity, 3)} />
                  </div>
                </section>

                <section className="rounded-lg border border-white/10 bg-white/5 p-4">
                  <h3 className="text-sm font-medium text-white">Cytosol</h3>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <Fact label="Glucose" value={formatNumber(cell.cytosol.glucose, 3)} />
                    <Fact label="Pyruvate" value={formatNumber(cell.cytosol.pyruvate, 3)} />
                    <Fact label="NADH" value={formatNumber(cell.cytosol.nadh, 3)} />
                    <Fact label="NAD+" value={formatNumber(cell.cytosol.nad_plus, 3)} />
                    <Fact label="FAD" value={formatNumber(cell.cytosol.fad, 3)} />
                    <Fact label="FADH2" value={formatNumber(cell.cytosol.fadh2, 3)} />
                    <Fact label="Acetyl-CoA" value={formatNumber(cell.cytosol.acetyl_coa, 3)} />
                    <Fact label="CO2" value={formatNumber(cell.cytosol.co2, 3)} />
                  </div>
                </section>

                <section className="rounded-lg border border-white/10 bg-white/5">
                  <div className="border-b border-white/10 px-4 py-4">
                    <h3 className="text-sm font-medium text-white">Cell events</h3>
                    <p className="mt-1 text-xs text-neutral-400">
                      {visibleEvents.length} of {events.length} events for the selected scope.
                    </p>
                  </div>
                  <div className="grid gap-3 border-b border-white/10 px-4 py-4">
                    <div className="flex flex-wrap gap-2">
                      {(["self", "lineage", "descendants"] as const).map((nextScope) => (
                        <Button
                          key={nextScope}
                          variant={scope === nextScope ? "default" : "outline"}
                          className={
                            scope === nextScope
                              ? "rounded-lg bg-emerald-300 text-neutral-950 hover:bg-emerald-200"
                              : "rounded-lg border-white/10 bg-white/5 text-white hover:bg-white/10"
                          }
                          onClick={() => {
                            setScope(nextScope);
                            setEventDetail(null);
                          }}
                        >
                          {nextScope}
                        </Button>
                      ))}
                    </div>
                    <div className="relative">
                      <Filter className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-neutral-500" aria-hidden="true" />
                      <Input
                        aria-label="Filter cell events"
                        value={eventQuery}
                        onChange={(event) => setEventQuery(event.target.value)}
                        placeholder="Filter events"
                        className="h-9 rounded-lg border-white/10 bg-neutral-950/70 pl-9 text-white placeholder:text-neutral-500"
                      />
                    </div>
                    {eventTypeCounts.length ? (
                      <div className="flex flex-wrap gap-2">
                        {eventTypeCounts.map(([type, count]) => (
                          <span
                            key={type}
                            className="rounded-md border border-white/10 bg-white/5 px-2 py-1 font-mono text-[11px] text-neutral-300"
                          >
                            {type} {count}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="max-h-96 overflow-y-auto">
                    {visibleEvents.length ? (
                      visibleEvents.map((event, index) => (
                        <button
                          key={`${event.step}-${event.type}-${index}`}
                          type="button"
                          className="block w-full border-b border-white/8 px-4 py-3 text-left transition hover:bg-white/8"
                          onClick={() => setEventDetail({ cellId: cell.id, event })}
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-mono text-xs text-emerald-200">step {event.step}</span>
                            <span className="rounded-md border border-white/10 px-2 py-0.5 font-mono text-[11px] uppercase text-neutral-300">
                              {event.type}
                            </span>
                          </div>
                          <div className="mt-2 text-sm leading-5 text-neutral-200">{event.message}</div>
                        </button>
                      ))
                    ) : (
                      <div className="px-4 py-6 text-sm text-neutral-400">No events match this scope and filter.</div>
                    )}
                  </div>
                </section>
              </>
            ) : (
              <div className="text-sm text-neutral-400">Select a cell to inspect its details.</div>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-xs uppercase text-neutral-500">{label}</div>
      <div className="mt-1 break-words font-mono text-sm text-neutral-100">{value}</div>
    </div>
  );
}

function EventDetail({
  event,
  linkedCellIds,
  onBack,
  onSelectCell,
}: {
  event: CellEvent;
  linkedCellIds: string[];
  onBack: () => void;
  onSelectCell: (cellId: string) => void;
}) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/5 p-4">
      <Button
        variant="ghost"
        className="mb-4 rounded-lg px-0 text-neutral-300 hover:bg-transparent hover:text-white"
        onClick={onBack}
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to cell details
      </Button>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-mono text-xs text-emerald-200">step {event.step}</div>
          <h3 className="mt-2 text-lg font-medium text-white">{event.type}</h3>
        </div>
        <div className="font-mono text-xs text-neutral-400">t={formatNumber(event.time, 3)}</div>
      </div>
      <p className="mt-4 leading-6 text-neutral-200">{event.message}</p>

      {linkedCellIds.length ? (
        <div className="mt-5">
          <div className="text-xs uppercase text-neutral-500">Linked cells</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {linkedCellIds.map((linkedCellId) => (
              <Button
                key={linkedCellId}
                variant="outline"
                className="rounded-lg border-white/10 bg-white/5 font-mono text-xs text-white hover:bg-white/10"
                onClick={() => onSelectCell(linkedCellId)}
              >
                <ExternalLink className="size-3" aria-hidden="true" />
                {linkedCellId}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-5 rounded-lg border border-white/10 bg-neutral-950/70 p-3">
        <div className="mb-2 text-xs uppercase text-neutral-500">Payload</div>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-5 text-neutral-200">
          {JSON.stringify(event.values, null, 2)}
        </pre>
      </div>
    </section>
  );
}
