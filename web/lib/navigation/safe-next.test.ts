import { describe, expect, it } from "vitest";
import { SAFE_NEXT_FALLBACK, safeNextPath } from "./safe-next";

describe("safeNextPath", () => {
  it.each([
    ["https://evil.example", "absolute URL"],
    ["http://evil.example/path", "absolute http URL"],
    ["//evil.example", "protocol-relative"],
    ["/\\evil.example", "backslash protocol-relative"],
    ["\\\\evil.example", "double backslash"],
    ["/foo\\..\\..\\evil", "backslash anywhere"],
    ["%2F%2Fevil.example", "encoded slashes without a leading slash"],
    ["javascript:alert(1)", "javascript scheme"],
    ["data:text/html,hi", "data scheme"],
    ["/\t/evil.example", "tab that browsers strip"],
    ["/\n/evil.example", "newline that browsers strip"],
    ["/\u0000/evil.example", "NUL"],
    ["/\u007f/evil.example", "DEL"],
    ["/..//evil.example", "dot segments normalising to //"],
    ["/./../..//evil.example", "nested dot segments"],
    ["evil.example", "bare host"],
    ["", "empty"],
    [`/${"a".repeat(2_048)}`, "over 2,048 characters"],
  ])("refuses %j (%s)", (raw) => {
    expect(safeNextPath(raw)).toBe(SAFE_NEXT_FALLBACK);
  });

  it.each([null, undefined])("falls back for %j", (raw) => {
    expect(safeNextPath(raw)).toBe(SAFE_NEXT_FALLBACK);
  });

  it.each([
    ["/", "/"],
    ["/dealer/stock", "/dealer/stock"],
    ["/ok?x=1#y", "/ok?x=1#y"],
    [
      "/search?make=ford&postcode=SW1A%201AA",
      "/search?make=ford&postcode=SW1A%201AA",
    ],
    ["/%2F%2Fevil.example", "/%2F%2Fevil.example"],
    ["/a/../b", "/b"],
  ])("keeps the same-origin path %j", (raw, expected) => {
    expect(safeNextPath(raw)).toBe(expected);
  });
});
