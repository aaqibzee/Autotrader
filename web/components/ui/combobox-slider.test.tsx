import { readFileSync } from "node:fs";
import path from "node:path";
import { formatMileage, formatPrice } from "@/lib/format";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Combobox, type ComboboxItem } from "./combobox";
import { PAGE_STEPS, RangeSlider } from "./range-slider";

const MAKES: ComboboxItem[] = [
  { id: "citroen", name: "Citroën" },
  { id: "ford", name: "Ford" },
  { id: "mercedes-benz", name: "Mercedes-Benz" },
  { id: "skoda", name: "Škoda" },
  { id: "vauxhall", name: "Vauxhall" },
];

describe("Combobox (Feature 03 §2, §8)", () => {
  it("selects with the keyboard alone, matching without accents", async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();
    render(<Combobox id="make" items={MAKES} label="Make" onSelectionChange={onSelectionChange} />);

    const input = screen.getByRole("combobox", { name: "Make" });
    await user.tab();
    expect(input).toHaveFocus();
    await user.keyboard("citroen");

    const listbox = screen.getByRole("listbox");
    expect(within(listbox).getAllByRole("option").map((option) => option.textContent)).toEqual(["Citroën"]);

    await user.keyboard("{ArrowDown}{Enter}");
    expect(onSelectionChange).toHaveBeenLastCalledWith("citroen");
    expect(input).toHaveValue("Citroën");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("exposes combobox, listbox and aria-activedescendant to screen readers", async () => {
    const user = userEvent.setup();
    render(<Combobox id="make" items={MAKES} label="Make" />);
    const input = screen.getByRole("combobox", { name: "Make" });

    await user.click(input);
    await user.keyboard("{ArrowDown}");
    const listbox = screen.getByRole("listbox");
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(input).toHaveAttribute("aria-controls", listbox.id);
    // Focus stays in the input; the highlighted option is announced through the id.
    expect(input).toHaveFocus();
    const active = input.getAttribute("aria-activedescendant");
    expect(active).toBeTruthy();
    expect(document.getElementById(active ?? "")).toHaveTextContent("Citroën");

    await user.keyboard("{ArrowDown}");
    expect(document.getElementById(input.getAttribute("aria-activedescendant") ?? "")).toHaveTextContent("Ford");
  });

  it("filters in the lookup normal form", async () => {
    const user = userEvent.setup();
    render(<Combobox id="make" items={MAKES} label="Make" />);
    await user.type(screen.getByRole("combobox"), "mercedes benz");
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(["Mercedes-Benz"]);
  });

  it("says when nothing matches, and says it is loading while items arrive", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <Combobox emptyMessage="No makes match" id="make" items={MAKES} label="Make" />,
    );
    await user.type(screen.getByRole("combobox"), "zzz");
    expect(screen.getByRole("status")).toHaveTextContent("No makes match");

    rerender(<Combobox emptyMessage="No makes match" id="make" isLoading items={[]} label="Make" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
  });

  it("links its hint and error to the input", () => {
    render(<Combobox error="Choose a make" hint="Start typing" id="make" items={MAKES} label="Make" />);
    const input = screen.getByRole("combobox", { name: "Make" });
    expect(input).toHaveAccessibleDescription(expect.stringContaining("Start typing"));
    expect(input).toHaveAccessibleDescription(expect.stringContaining("Choose a make"));
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("filters the full model list without noticeable lag", async () => {
    // Every model in the seed taxonomy (Feature 02), padded to 550 options.
    const csv = readFileSync(path.resolve(process.cwd(), "../backend/data/taxonomy/models.csv"), "utf8");
    const models: ComboboxItem[] = csv
      .trim()
      .split("\n")
      .slice(1)
      .map((line) => {
        const [make, slug, name] = line.split(",");
        return { id: `${make}/${slug}`, name: name ?? "" };
      });
    while (models.length < 550) models.push({ id: `pad-${models.length}`, name: `Model ${models.length}` });
    expect(models.length).toBeGreaterThanOrEqual(550);

    render(<Combobox id="model" items={models} label="Model" />);
    const input = screen.getByRole("combobox");
    input.focus();

    const started = performance.now();
    act(() => {
      fireEvent.change(input, { target: { value: "golf" } });
    });
    const options = screen.getAllByRole("option");
    const elapsed = performance.now() - started;

    expect(options.map((option) => option.textContent)).toContain("Golf");
    // A generous bound for a slow CI runner under jsdom; a real browser is far faster.
    expect(elapsed).toBeLessThan(1_000);
  });
});

function PriceSlider(props: { onChangeEnd?: (value: [number, number]) => void }) {
  return (
    <RangeSlider
      defaultValue={[500_000, 2_000_000]}
      formatValue={formatPrice}
      label="Price"
      maxValue={10_000_000}
      minValue={0}
      step={50_000}
      thumbLabels={["Minimum", "Maximum"]}
      {...props}
    />
  );
}

describe("RangeSlider (Feature 03 §2, §8)", () => {
  const thumbs = () => screen.getAllByRole("slider") as HTMLInputElement[];

  it("reads values in pounds through lib/format, from a value in pence", () => {
    render(<PriceSlider />);
    const [low, high] = thumbs();
    expect(low).toHaveAttribute("aria-valuetext", "£5,000");
    expect(high).toHaveAttribute("aria-valuetext", "£20,000");
    expect(low).toHaveAccessibleName("Minimum Price");
    expect(screen.getByRole("group", { name: "Price" })).toBeInTheDocument();
    expect(screen.getByText("£5,000 – £20,000")).toBeInTheDocument();
  });

  it("each key moves the documented amount", async () => {
    const user = userEvent.setup();
    const onChangeEnd = vi.fn();
    render(<PriceSlider onChangeEnd={onChangeEnd} />);
    const [low] = thumbs();
    act(() => low?.focus());

    await user.keyboard("{ArrowRight}");
    expect(low).toHaveValue(String(500_000 + 50_000));
    await user.keyboard("{ArrowLeft}");
    expect(low).toHaveValue("500000");
    await user.keyboard("{PageUp}");
    expect(low).toHaveValue(String(500_000 + PAGE_STEPS * 50_000));
    expect(low).toHaveAttribute("aria-valuetext", "£10,000");
    await user.keyboard("{PageDown}");
    expect(low).toHaveValue("500000");
    await user.keyboard("{Home}");
    expect(low).toHaveValue("0");
    expect(onChangeEnd).toHaveBeenLastCalledWith([0, 2_000_000]);
  });

  it("thumbs cannot cross", async () => {
    const user = userEvent.setup();
    render(<PriceSlider />);
    const [low, high] = thumbs();

    act(() => low?.focus());
    await user.keyboard("{End}");
    expect(low).toHaveValue("2000000");
    await user.keyboard("{ArrowRight}{PageUp}");
    expect(low).toHaveValue("2000000");
    expect(low).toHaveAttribute("max", "2000000");

    act(() => high?.focus());
    await user.keyboard("{Home}{ArrowLeft}");
    expect(high).toHaveValue("2000000");
    expect(high).toHaveAttribute("min", "2000000");
  });

  it("works for mileage with its own formatter", () => {
    render(
      <RangeSlider
        defaultValue={[10_000, 60_000]}
        formatValue={formatMileage}
        label="Mileage"
        maxValue={200_000}
        minValue={0}
        step={1_000}
        thumbLabels={["Minimum", "Maximum"]}
      />,
    );
    expect(thumbs()[1]).toHaveAttribute("aria-valuetext", "60,000 miles");
  });

  it("server markup positions thumbs with style attributes and inserts no <style> element", () => {
    const html = renderToString(<PriceSlider />);
    // style-src-attr allows attributes (Feature 03 A2); a <style> element would need a nonce.
    expect(html).toMatch(/style="[^"]*left:5%/);
    expect(html).not.toMatch(/<style/);
    expect(html).toContain('aria-valuetext="£5,000"');
  });
});
