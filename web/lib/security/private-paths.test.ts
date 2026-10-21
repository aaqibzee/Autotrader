import { describe, expect, it } from "vitest";
import { isPrivatePath } from "./private-paths";

describe("isPrivatePath", () => {
  it.each(["/dealer", "/dealer/", "/dealer/stock/123", "/account", "/account/saved", "/admin", "/admin/dealers"])(
    "%s is private",
    (path) => {
      expect(isPrivatePath(path)).toBe(true);
    },
  );

  it.each(["/", "/dealers-near-me", "/accounting-cars", "/administrator", "/cars/dealer", "/search"])(
    "%s is public",
    (path) => {
      expect(isPrivatePath(path)).toBe(false);
    },
  );
});
