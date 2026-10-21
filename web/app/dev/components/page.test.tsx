import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ComponentGalleryPage from "./page";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("/dev/components (Feature 03 A3)", () => {
  it("is a 404 without ENABLE_COMPONENT_GALLERY", () => {
    vi.stubEnv("ENABLE_COMPONENT_GALLERY", "");
    expect(() => ComponentGalleryPage()).toThrow(
      expect.objectContaining({ digest: expect.stringMatching(/404/) }),
    );
  });

  it("renders every section, each anchored, when enabled", () => {
    vi.stubEnv("ENABLE_COMPONENT_GALLERY", "1");
    render(ComponentGalleryPage());
    const sections = [
      "buttons",
      "icon-buttons",
      "text-inputs",
      "selects",
      "choices",
      "badges",
      "cards",
      "skeletons",
      "pagination",
      "breadcrumbs",
      "overlays",
      "toasts",
      "tabs",
      "accordion",
      "combobox",
      "range-slider",
    ];
    for (const id of sections) {
      expect(document.getElementById(id), id).not.toBeNull();
    }
    expect(
      screen.getByRole("heading", { level: 1, name: "Component gallery" }),
    ).toBeInTheDocument();
  });

  it("ids are unique, so every label points at exactly one control", () => {
    vi.stubEnv("ENABLE_COMPONENT_GALLERY", "1");
    const { container } = render(ComponentGalleryPage());
    const ids = [...container.querySelectorAll("[id]")].map(
      (element) => element.id,
    );
    expect(ids.filter((id, index) => ids.indexOf(id) !== index)).toEqual([]);
  });
});
