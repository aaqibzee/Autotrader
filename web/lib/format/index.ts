// Two formatters, because "no pence when whole pounds" must not become "£12,495.5":
// a single min-0/max-2 formatter drops the trailing zero of 50p.
const GBP_WHOLE = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const GBP_WITH_PENCE = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const MILEAGE_FORMATTER = new Intl.NumberFormat("en-GB", {
  maximumFractionDigits: 0,
});

const DATE_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "Europe/London",
});

function asDate(value: Date | string): Date {
  if (value instanceof Date) return value;

  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly) {
    const [, year, month, day] = dateOnly;
    return new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), 12));
  }
  return new Date(value);
}

/** Money is always integer pence end to end; anything else is an upstream bug. */
export function formatPrice(pence: number): string {
  if (!Number.isSafeInteger(pence)) {
    throw new RangeError(
      `formatPrice expects integer pence, received ${pence}`,
    );
  }
  const formatter = pence % 100 === 0 ? GBP_WHOLE : GBP_WITH_PENCE;
  return formatter.format(pence / 100);
}

export function formatMileage(miles: number): string {
  if (!Number.isFinite(miles) || miles < 0) {
    throw new RangeError(
      `formatMileage expects a non-negative number, received ${miles}`,
    );
  }
  return `${MILEAGE_FORMATTER.format(miles)} miles`;
}

export function formatDate(value: Date | string): string {
  return DATE_FORMATTER.format(asDate(value));
}

export function formatRelativeTime(
  value: Date | string,
  now: Date = new Date(),
): string {
  const deltaSeconds = (asDate(value).getTime() - now.getTime()) / 1000;
  const absoluteSeconds = Math.abs(deltaSeconds);
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
    ["second", 1],
  ];
  const [unit, secondsPerUnit] = units.find(
    ([, seconds]) => absoluteSeconds >= seconds,
  ) ?? ["second", 1];
  const valueInUnits = Math.round(deltaSeconds / secondsPerUnit);

  return new Intl.RelativeTimeFormat("en-GB", { numeric: "always" }).format(
    valueInUnits,
    unit,
  );
}

function wholeSeconds(seconds: number): number {
  if (!Number.isFinite(seconds) || seconds < 0) {
    throw new RangeError(
      `expected a non-negative number of seconds, received ${seconds}`,
    );
  }
  return Math.ceil(seconds);
}

/** A visible countdown: "0:45", "12:00". Rounds up, so it never shows 0:00 early. */
export function formatCountdown(seconds: number): string {
  const total = wholeSeconds(seconds);
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

/**
 * A wait in words, for screen readers and sentences: "1 second", "45 seconds",
 * "1 minute", "3 minutes". A minute or more rounds up to whole minutes.
 */
export function formatWait(seconds: number): string {
  const total = wholeSeconds(seconds);
  if (total < 60) return total === 1 ? "1 second" : `${total} seconds`;
  const minutes = Math.ceil(total / 60);
  return minutes === 1 ? "1 minute" : `${minutes} minutes`;
}
