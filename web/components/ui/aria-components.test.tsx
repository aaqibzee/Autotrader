import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { Button } from "./button";
import { DialogTrigger, Modal, Sheet, TriggerButton } from "./overlay";
import { Accordion, Tabs } from "./tabs";
import { MAX_VISIBLE_TOASTS, showToast, toastQueue, useToast } from "./toast";
import { ToastRegion } from "./toast-region";

function SheetFixture() {
  return (
    <>
      <button type="button">Before</button>
      <DialogTrigger>
        <TriggerButton>Filters</TriggerButton>
        <Sheet
          footer={(close) => <Button onClick={close}>Apply</Button>}
          title="Filters"
        >
          <label htmlFor="make">Make</label>
          <input id="make" />
        </Sheet>
      </DialogTrigger>
      <button type="button">After</button>
    </>
  );
}

describe("Sheet and Modal (Feature 03 §8 focus rules)", () => {
  it("opens from the keyboard, moves focus in, traps Tab, and returns focus on Escape", async () => {
    const user = userEvent.setup();
    render(<SheetFixture />);
    const trigger = screen.getByRole("button", { name: "Filters" });

    trigger.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Filters" });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    // Tab many times: focus never leaves the dialog for the page behind it.
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    // React Aria restores focus on the next animation frame.
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("the close button and a footer action close it and return focus", async () => {
    const user = userEvent.setup();
    render(<SheetFixture />);
    const trigger = screen.getByRole("button", { name: "Filters" });

    await user.click(trigger);
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Close",
      }),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(trigger).toHaveFocus());

    await user.click(trigger);
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Apply",
      }),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a modal is named by its title; a hidden title still names it", async () => {
    const user = userEvent.setup();
    render(
      <DialogTrigger>
        <TriggerButton>Delete</TriggerButton>
        <Modal hideTitle title="Delete this saved search?">
          {(close) => <Button onClick={close}>Keep it</Button>}
        </Modal>
      </DialogTrigger>,
    );
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      await screen.findByRole("dialog", { name: "Delete this saved search?" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Delete this saved search?" }),
    ).toHaveClass("sr-only");
    await user.click(screen.getByRole("button", { name: "Keep it" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("toasts (Feature 03 §2, §8)", () => {
  // The queue is global: drain it completely, or toasts waiting behind the visible three
  // move up and leak into the next test.
  afterEach(() => {
    act(() => {
      while (toastQueue.visibleToasts.length > 0) {
        for (const toast of [...toastQueue.visibleToasts])
          toastQueue.close(toast.key);
      }
    });
  });

  it("errors are assertive alerts; info and success are polite status messages", async () => {
    render(<ToastRegion />);
    act(() => {
      showToast("We could not save your search.", "error");
      showToast("Search saved.", "success");
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We could not save your search.",
    );
    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
    expect(screen.getByRole("status")).toHaveTextContent("Search saved.");
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it("ten identical toasts render once", async () => {
    render(<ToastRegion />);
    const keys: Array<string | undefined> = [];
    act(() => {
      for (let i = 0; i < 10; i += 1)
        keys.push(showToast("We could not save your search.", "error"));
    });
    expect(await screen.findAllByRole("alert")).toHaveLength(1);
    expect(keys.filter(Boolean)).toHaveLength(1);
  });

  it("shows at most three at once; the rest wait", async () => {
    render(<ToastRegion />);
    act(() => {
      for (let i = 1; i <= 5; i += 1) useToast().show(`Message ${i}`, "info");
    });
    expect(await screen.findAllByRole("status")).toHaveLength(
      MAX_VISIBLE_TOASTS,
    );
  });

  it("can be dismissed", async () => {
    const user = userEvent.setup();
    render(<ToastRegion />);
    act(() => {
      showToast("Your listing is now live.");
    });
    await user.click(
      await screen.findByRole("button", { name: "Dismiss notification" }),
    );
    expect(screen.queryByText("Your listing is now live.")).toBeNull();
  });
});

describe("Tabs and Accordion", () => {
  it("arrow keys move between tabs and show the matching panel", async () => {
    const user = userEvent.setup();
    render(
      <Tabs
        items={[
          { id: "a", label: "Overview", content: "Overview panel" },
          { id: "b", label: "Specification", content: "Spec panel" },
        ]}
        label="Listing details"
      />,
    );
    expect(
      screen.getByRole("tablist", { name: "Listing details" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Overview" }));
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Specification" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Spec panel");
  });

  it("accordion sections expand and report it", async () => {
    const user = userEvent.setup();
    render(
      <Accordion
        defaultExpandedKeys={["one"]}
        items={[
          { id: "one", title: "Equipment", content: "Heated seats" },
          { id: "two", title: "Running costs", content: "Road tax £190" },
        ]}
      />,
    );
    const equipment = screen.getByRole("button", { name: "Equipment" });
    const running = screen.getByRole("button", { name: "Running costs" });
    expect(equipment).toHaveAttribute("aria-expanded", "true");
    expect(running).toHaveAttribute("aria-expanded", "false");
    await user.click(running);
    expect(running).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Road tax £190")).toBeVisible();
  });
});
