import { describe, expect, it } from "vitest";
import { galleryEnabled } from "./gallery";

describe("galleryEnabled", () => {
  it("is on only for the exact value 1", () => {
    expect(galleryEnabled({ ENABLE_COMPONENT_GALLERY: "1" })).toBe(true);
    for (const value of [undefined, "", "0", "true", "yes", " 1"]) {
      expect(galleryEnabled({ ENABLE_COMPONENT_GALLERY: value })).toBe(false);
    }
  });

  it("does not follow NODE_ENV (staging is a production build)", () => {
    expect(galleryEnabled({ NODE_ENV: "development" })).toBe(false);
  });
});
