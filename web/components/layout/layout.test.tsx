import { ApiError } from "@/lib/api/error";
import { act, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let pathname = "/dealer/leads";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

const { AccountIsland } = await import("./account-island");
const { AdminChrome } = await import("./admin-chrome");
const { DealerChrome } = await import("./dealer-chrome");
const { PageSkeleton } = await import("./page-skeleton");
const { PublicChrome } = await import("./public-chrome");

const island = (container: HTMLElement) =>
  container.querySelector("[data-account-island]");

describe("AccountIsland (A8)", () => {
  it("renders signed-out without a request while there is no loader", () => {
    const { container } = render(<AccountIsland />);
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/sign-in",
    );
    expect(island(container)).toHaveAttribute(
      "data-account-island",
      "signed-out",
    );
  });

  it("holds its box while loading, then shows the account in the same box", async () => {
    let resolve: (value: { displayName: string }) => void = () => {};
    const load = () =>
      new Promise<{ displayName: string }>((done) => (resolve = done));
    const { container } = render(<AccountIsland load={load} />);
    const box = island(container);
    expect(box).toHaveAttribute("data-account-island", "loading");
    expect(box).toHaveClass("h-11", "w-28");

    await act(async () => resolve({ displayName: "sam" }));
    expect(island(container)).toBe(box);
    expect(box).toHaveClass("h-11", "w-28");
    expect(
      screen.getByRole("link", { name: /signed in as sam/ }),
    ).toHaveAttribute("href", "/account");
    expect(screen.getByText("S")).toBeInTheDocument();
  });

  it.each([
    ["no account", () => Promise.resolve(null)],
    ["a 401", () => Promise.reject(new ApiError({}, 401))],
    ["a 404", () => Promise.reject(new ApiError({}, 404))],
    ["a 500, silently", () => Promise.reject(new ApiError({}, 500))],
  ])("%s renders signed-out", async (_case, load) => {
    render(<AccountIsland load={load} />);
    expect(
      await screen.findByRole("link", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("ignores an answer that arrives after it unmounted", async () => {
    const answers: Array<() => void> = [];
    const load = (outcome: "ok" | "fail") => () =>
      new Promise<{ displayName: string }>((resolve, reject) => {
        answers.push(() =>
          outcome === "ok"
            ? resolve({ displayName: "Sam" })
            : reject(new Error("x")),
        );
      });
    const first = render(<AccountIsland load={load("ok")} />);
    const second = render(<AccountIsland load={load("fail")} />);
    first.unmount();
    second.unmount();
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    await act(async () => answers.forEach((answer) => answer()));
    expect(errors).not.toHaveBeenCalled();
  });
});

describe("PublicChrome", () => {
  it("starts with a skip link to main, and hides 'Value my car' by default", () => {
    render(<PublicChrome>Page</PublicChrome>);
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveTextContent("Skip to content");
    expect(links[0]).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
    expect(screen.queryByRole("link", { name: "Value my car" })).toBeNull();
    expect(screen.getByRole("link", { name: "Search cars" })).toHaveAttribute(
      "href",
      "/search",
    );
    expect(
      screen.queryByRole("navigation", { name: "Cars by make" }),
    ).toBeNull();
    const legal = screen.getByRole("navigation", { name: "Legal" });
    expect(
      within(legal)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Terms", "Privacy", "Cookies"]);
  });

  it("shows valuation, make links and a custom account slot when given", () => {
    render(
      <PublicChrome
        account={<span>Account slot</span>}
        makeLinks={<span>Ford</span>}
        showValuation
      >
        Page
      </PublicChrome>,
    );
    expect(
      screen.getByRole("link", { name: "Value my car" }),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("navigation", { name: "Cars by make" }),
      ).getByText("Ford"),
    ).toBeInTheDocument();
    expect(screen.getByText("Account slot")).toBeInTheDocument();
  });
});

describe("DealerChrome", () => {
  it("marks the current section in both navs", () => {
    pathname = "/dealer/leads/42";
    render(<DealerChrome>Page</DealerChrome>);
    const navs = screen.getAllByRole("navigation", { name: "Dealer" });
    expect(navs).toHaveLength(2);
    for (const nav of navs) {
      expect(
        within(nav).getByRole("link", { current: "page" }),
      ).toHaveTextContent("Leads");
      expect(
        within(nav)
          .getAllByRole("link")
          .map((link) => link.textContent),
      ).toEqual(["Stock", "Leads", "Team", "Settings"]);
    }
  });

  it.each([
    ["pending", "Awaiting approval: you can create drafts but not publish."],
    [
      "suspended",
      "Your dealership is suspended, so your listings are hidden. Contact support.",
    ],
  ] as const)("a %s dealer sees the banner", (status, text) => {
    render(
      <DealerChrome dealerName="Bristol Motors" dealerStatus={status}>
        Page
      </DealerChrome>,
    );
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.getByText("Bristol Motors")).toBeInTheDocument();
  });

  it("no banner for an approved dealer, or before Feature 04 supplies a status", () => {
    const { container, rerender } = render(
      <DealerChrome dealerStatus="approved">Page</DealerChrome>,
    );
    expect(container.querySelector("[data-dealer-banner]")).toBeNull();
    rerender(<DealerChrome>Page</DealerChrome>);
    expect(container.querySelector("[data-dealer-banner]")).toBeNull();
  });
});

describe("AdminChrome and PageSkeleton", () => {
  it("admin chrome has a skip link and main", () => {
    render(<AdminChrome>Admin page</AdminChrome>);
    expect(screen.getByRole("main")).toHaveTextContent("Admin page");
    expect(
      screen.getByRole("link", { name: "Skip to content" }),
    ).toBeInTheDocument();
  });

  it("the skeleton is busy and says so once", () => {
    render(<PageSkeleton label="Loading listings" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading listings…");
  });
});
