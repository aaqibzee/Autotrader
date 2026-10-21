import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button, IconButton } from "./button";
import { cx } from "./cx";
import { Badge, ListingBadges, Skeleton, Tag } from "./display";
import { describedBy } from "./field";
import { Checkbox, RadioGroup, Select, TextInput, Toggle } from "./inputs";
import { Breadcrumbs, Pagination, pageItems } from "./navigation";

describe("labelled fields (Feature 03 §8)", () => {
  it("labels the input and links hint and error with aria-describedby", () => {
    render(
      <TextInput
        error="Enter a full postcode."
        hint="Used for distances."
        id="pc"
        label="Postcode"
      />,
    );
    const input = screen.getByLabelText("Postcode");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", "pc-hint pc-error");
    expect(input).toHaveAccessibleDescription(
      "Used for distances. Enter a full postcode.",
    );
  });

  it("has no aria-invalid or aria-describedby without hint or error", () => {
    render(<TextInput id="plain" label="Plain" />);
    const input = screen.getByLabelText("Plain");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(input).not.toHaveAttribute("aria-describedby");
  });

  it("describedBy lists only what exists", () => {
    expect(describedBy({ id: "x" })).toBeUndefined();
    expect(describedBy({ id: "x", hint: "h" })).toBe("x-hint");
    expect(describedBy({ id: "x", error: "e" })).toBe("x-error");
  });

  it("select has its label, placeholder and error", () => {
    render(
      <Select
        error="Choose one."
        id="fuel"
        label="Fuel type"
        options={[{ value: "petrol", label: "Petrol" }]}
        placeholder="Any"
      />,
    );
    const select = screen.getByLabelText("Fuel type");
    expect(select).toHaveAccessibleDescription("Choose one.");
    expect(screen.getByRole("option", { name: "Any" })).toHaveValue("");
  });

  it("select without a placeholder lists only its options", () => {
    render(
      <Select
        id="f2"
        label="Fuel"
        options={[{ value: "diesel", label: "Diesel" }]}
      />,
    );
    expect(screen.getAllByRole("option")).toHaveLength(1);
  });

  it("checkbox and toggle are labelled; toggle is a switch", () => {
    render(
      <>
        <Checkbox error="Required." id="terms" label="I accept the terms" />
        <Toggle hint="Daily digest." id="alerts" label="Email me new matches" />
      </>,
    );
    expect(
      screen.getByRole("checkbox", { name: "I accept the terms" }),
    ).toHaveAccessibleDescription("Required.");
    expect(
      screen.getByRole("switch", { name: "Email me new matches" }),
    ).toHaveAccessibleDescription("Daily digest.");
  });

  it("radio group is a named group with one radio per option", () => {
    render(
      <RadioGroup
        defaultValue="manual"
        error="Pick one."
        hint="Choose one."
        legend="Gearbox"
        name="gearbox"
        options={[
          { value: "manual", label: "Manual" },
          { value: "automatic", label: "Automatic" },
        ]}
      />,
    );
    const group = screen.getByRole("group", { name: "Gearbox" });
    expect(group).toHaveAttribute(
      "aria-describedby",
      "gearbox-hint gearbox-error",
    );
    expect(group).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("radio", { name: "Manual" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Automatic" })).not.toBeChecked();
  });

  it("controlled radio group reports the chosen value", () => {
    const chosen: string[] = [];
    render(
      <RadioGroup
        legend="Gearbox"
        name="g2"
        onChange={(value) => chosen.push(value)}
        options={[
          { value: "manual", label: "Manual" },
          { value: "automatic", label: "Automatic" },
        ]}
        value="manual"
      />,
    );
    screen.getByRole("radio", { name: "Automatic" }).click();
    expect(chosen).toEqual(["automatic"]);
  });
});

describe("buttons", () => {
  it("loading disables the button, marks it busy and keeps the label", () => {
    render(<Button loading>Saving</Button>);
    const button = screen.getByRole("button", { name: "Saving" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" })).toHaveAttribute(
      "type",
      "button",
    );
    expect(screen.getByRole("button", { name: "Go" })).not.toHaveAttribute(
      "aria-busy",
    );
  });

  it("icon button is named by its label", () => {
    render(<IconButton icon={<svg />} label="Save this car" />);
    expect(screen.getByRole("button", { name: "Save this car" })).toHaveClass(
      "size-11",
    );
  });

  it("small icon button is 36px", () => {
    render(<IconButton icon={<svg />} label="Save" size="sm" />);
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("size-9");
  });

  it("an icon button without a label does not compile", () => {
    // @ts-expect-error `label` is required: an icon alone has no accessible name.
    const element = <IconButton icon={<svg />} />;
    expect(element).toBeTruthy();
  });
});

describe("display", () => {
  it("listing badges use the agreed wording", () => {
    render(
      <>
        <ListingBadges.Example />
        <ListingBadges.Reserved />
        <ListingBadges.Sold />
      </>,
    );
    for (const text of ["Example listing", "Reserved", "Sold"]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
  });

  it("badge, tag and skeleton render", () => {
    const { container } = render(
      <>
        <Badge>neutral</Badge>
        <Tag>Automatic</Tag>
        <Skeleton className="h-4" />
      </>,
    );
    expect(screen.getByText("neutral")).toHaveClass("bg-sunken");
    expect(screen.getByText("Automatic")).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toHaveClass("h-4");
  });

  it("cx skips falsy values", () => {
    expect(cx("a", false, undefined, null, "b")).toBe("a b");
  });
});

describe("pageItems", () => {
  it.each<[number, number, Array<number | "gap">]>([
    [1, 1, [1]],
    [1, 3, [1, 2, 3]],
    [1, 20, [1, 2, "gap", 20]],
    [10, 20, [1, "gap", 9, 10, 11, "gap", 20]],
    [20, 20, [1, "gap", 19, 20]],
    // A one-page gap is shown as the page itself.
    [4, 7, [1, 2, 3, 4, 5, 6, 7]],
    [3, 20, [1, 2, 3, 4, "gap", 20]],
  ])("page %i of %i", (current, total, expected) => {
    expect(pageItems(current, total)).toEqual(expected);
  });

  it("clamps out-of-range pages and handles no pages", () => {
    expect(pageItems(0, 5)).toEqual(pageItems(1, 5));
    expect(pageItems(99, 5)).toEqual(pageItems(5, 5));
    expect(pageItems(1, 0)).toEqual([]);
  });
});

describe("Pagination", () => {
  const hrefFor = (page: number) => `/search?page=${page}`;

  it("marks the current page and links the rest", () => {
    render(<Pagination current={10} hrefFor={hrefFor} total={20} />);
    expect(
      screen.getByRole("navigation", { name: "Pagination" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Page 10" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Page 9" })).toHaveAttribute(
      "href",
      "/search?page=9",
    );
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
      "href",
      "/search?page=9",
    );
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
      "href",
      "/search?page=11",
    );
  });

  it("disables previous on the first page and next on the last", () => {
    const { rerender } = render(
      <Pagination current={1} hrefFor={hrefFor} total={3} />,
    );
    expect(screen.queryByRole("link", { name: "Previous" })).toBeNull();
    expect(screen.getByText("Previous")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    rerender(<Pagination current={3} hrefFor={hrefFor} total={3} />);
    expect(screen.queryByRole("link", { name: "Next" })).toBeNull();
  });

  it("renders nothing for a single page", () => {
    const { container } = render(
      <Pagination current={1} hrefFor={hrefFor} total={1} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Breadcrumbs", () => {
  it("links all but the last crumb, which is the current page", () => {
    render(
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "Ford" },
          { label: "Fiesta", href: "/ignored-because-last" },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.queryByRole("link", { name: "Ford" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Fiesta" })).toBeNull();
    expect(screen.getByText("Fiesta")).toHaveAttribute("aria-current", "page");
  });

  it("renders nothing without items", () => {
    const { container } = render(<Breadcrumbs items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
