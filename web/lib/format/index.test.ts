import { describe, expect, it } from "vitest";
import {
  formatDate,
  formatMileage,
  formatPrice,
  formatRelativeTime,
} from "./index";

describe("formatPrice", () => {
  it("omits pence for whole pounds", () => {
    expect(formatPrice(1_249_500)).toBe("£12,495");
    expect(formatPrice(0)).toBe("£0");
  });

  it("always shows two pence digits otherwise", () => {
    expect(formatPrice(1_249_599)).toBe("£12,495.99");
    expect(formatPrice(1_249_550)).toBe("£12,495.50");
    expect(formatPrice(5)).toBe("£0.05");
  });

  it("groups large prices and handles negatives (refunds, price drops)", () => {
    expect(formatPrice(12_500_000_00)).toBe("£12,500,000");
    expect(formatPrice(-50_000)).toBe("-£500");
  });

  it("rejects non-integer or non-finite pence", () => {
    expect(() => formatPrice(12.5)).toThrow(RangeError);
    expect(() => formatPrice(Number.NaN)).toThrow(RangeError);
    expect(() => formatPrice(Number.POSITIVE_INFINITY)).toThrow(RangeError);
  });
});

describe("formatMileage", () => {
  it("formats with UK grouping", () => {
    expect(formatMileage(42_150)).toBe("42,150 miles");
    expect(formatMileage(0)).toBe("0 miles");
  });

  it("rounds fractional odometer readings", () => {
    expect(formatMileage(42_150.6)).toBe("42,151 miles");
  });

  it("rejects negative or non-finite values", () => {
    expect(() => formatMileage(-1)).toThrow(RangeError);
    expect(() => formatMileage(Number.NaN)).toThrow(RangeError);
  });
});

describe("formatDate", () => {
  it("formats date-only values without shifting the calendar day", () => {
    expect(formatDate("2026-10-14")).toBe("14/10/2026");
  });

  it("converts instants to Europe/London, including across BST", () => {
    // 23:30 UTC on 14 Jul is 00:30 BST on 15 Jul.
    expect(formatDate("2026-07-14T23:30:00Z")).toBe("15/07/2026");
    // In winter London is UTC+0.
    expect(formatDate(new Date("2026-01-14T23:30:00Z"))).toBe("14/01/2026");
  });
});

describe("formatRelativeTime", () => {
  const now = new Date("2026-10-14T12:00:00Z");

  it("describes past times", () => {
    expect(formatRelativeTime("2026-10-11T12:00:00Z", now)).toBe("3 days ago");
    expect(formatRelativeTime("2026-10-14T11:59:30Z", now)).toBe(
      "30 seconds ago",
    );
    expect(formatRelativeTime("2026-09-30T12:00:00Z", now)).toBe("2 weeks ago");
    expect(formatRelativeTime("2025-10-14T12:00:00Z", now)).toBe("1 year ago");
  });

  it("describes future times and the present moment", () => {
    expect(formatRelativeTime("2026-10-14T14:00:00Z", now)).toBe("in 2 hours");
    expect(formatRelativeTime(now, now)).toBe("in 0 seconds");
  });
});
