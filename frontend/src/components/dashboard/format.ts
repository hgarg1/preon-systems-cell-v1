export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }

  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function lineageDepth(cellId: string): number {
  return Math.max(cellId.split(".").length - 1, 0);
}

export function lineageColor(cellId: string, generation = lineageDepth(cellId)): string {
  const parts = cellId.split(".");
  const branchSeed = parts.reduce((hash, part) => {
    for (const char of part) {
      hash = (hash * 31 + char.charCodeAt(0)) % 360;
    }
    return hash;
  }, 136);
  const hue = (branchSeed + generation * 23) % 360;
  return `hsl(${hue} 72% ${Math.max(48, 68 - generation * 5)}%)`;
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${formatNumber(count, 0)} ${count === 1 ? singular : plural}`;
}
