import {
  reportNetworkFailure,
  reportNetworkSuccess,
} from "@/lib/api/connectivity";
import {
  ApiError,
  ApiNetworkError,
  ApiTimeoutError,
  type ProblemCode,
} from "@/lib/api/error";
import {
  PROBLEM_UI,
  type ProblemUiKind,
  problemUi,
} from "@/lib/api/problem-ui";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OfflineBanner } from "./offline-banner";
import { ProblemView } from "./problem-view";
import { EmptyState, ErrorState, NotFound, PermissionDenied } from "./states";

const apiError = (
  code: ProblemCode,
  status: number,
  retryAfterSeconds?: number,
) =>
  new ApiError({ code, title: code }, status, `req_${code}`, {
    retryAfterSeconds,
  });

/** One error per UI kind. A kind added to problem-ui without a case here fails typecheck. */
const ERROR_FOR_KIND: Record<ProblemUiKind, unknown> = {
  "field-errors": apiError("invalid_input", 422),
  conflict: apiError("stale_update", 409),
  "rate-limited": apiError("rate_limited", 429, 30),
  unavailable: apiError("integration_unavailable", 503),
  "sign-in": new ApiError({}, 401),
  permission: new ApiError({}, 403),
  "not-found": apiError("not_found", 404),
  invalid: apiError("bad_request", 400),
  retryable: apiError("internal_error", 500),
  timeout: new ApiTimeoutError(10_000),
  offline: new ApiNetworkError(new TypeError("Failed to fetch")),
};

afterEach(() => {
  vi.useRealTimers();
  reportNetworkSuccess();
});

describe("ProblemView (Feature 03 §3 table)", () => {
  it.each(Object.entries(ERROR_FOR_KIND))(
    "%s renders its own state and copy",
    (kind, error) => {
      const { container } = render(
        <ProblemView error={error} onRetry={() => {}} />,
      );
      expect(
        container.querySelector(`[data-problem-kind="${kind}"]`),
      ).not.toBeNull();
      expect(
        screen.getByRole("heading", { name: problemUi(error).title }),
      ).toBeInTheDocument();
    },
  );

  it.each(Object.keys(PROBLEM_UI) as ProblemCode[])(
    "problem code %s renders its title",
    (code) => {
      // Generic codes take their copy from the status, so give each a fitting one.
      render(
        <ProblemView
          error={apiError(code, code === "internal_error" ? 500 : 400)}
        />,
      );
      expect(
        screen.getByRole("heading", { name: PROBLEM_UI[code].title }),
      ).toBeInTheDocument();
    },
  );

  it("503 integration_unavailable offers to continue manually, with retry second", () => {
    render(
      <ProblemView
        continueAction={<button type="button">Enter details manually</button>}
        error={apiError("integration_unavailable", 503)}
        onRetry={() => {}}
      />,
    );
    const buttons = screen
      .getAllByRole("button")
      .map((button) => button.textContent);
    expect(buttons).toEqual(["Enter details manually", "Try again"]);
    expect(screen.getByText(/enter the details yourself/)).toBeInTheDocument();
  });

  it("a server error offers retry and shows the request id small, for support", () => {
    const onRetry = vi.fn();
    render(
      <ProblemView error={apiError("internal_error", 500)} onRetry={onRetry} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(screen.getByText("req_internal_error")).toBeInTheDocument();
  });

  it("no retry where retrying cannot help, and no continue action outside 'unavailable'", () => {
    render(
      <ProblemView
        continueAction={<button type="button">Enter details manually</button>}
        error={apiError("bad_request", 400)}
        onRetry={() => {}}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("a 401 shows the caller's sign-in action", () => {
    render(
      <ProblemView
        error={new ApiError({}, 401)}
        signInAction={<button type="button">Sign in</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("Retry-After countdown", () => {
  function announcementsDuring(run: () => void) {
    const seen: string[] = [];
    const region = screen.getByRole("status");
    const observer = new MutationObserver(() => {
      if (region.textContent) seen.push(region.textContent);
    });
    observer.observe(region, {
      childList: true,
      characterData: true,
      subtree: true,
    });
    run();
    observer.takeRecords().forEach(() => {});
    observer.disconnect();
    return seen;
  }

  it("counts down, enables retry at zero, and announces twice in total", async () => {
    vi.useFakeTimers();
    const onRetry = vi.fn();
    render(
      <ProblemView
        error={apiError("rate_limited", 429, 3)}
        onRetry={onRetry}
      />,
    );
    const retry = screen.getByRole("button", { name: "Try again" });
    expect(retry).toBeDisabled();
    expect(screen.getByText("0:03")).toBeInTheDocument();

    const seen: string[] = [];
    const region = screen.getByRole("status");
    const record = () => {
      if (region.textContent && region.textContent !== seen.at(-1))
        seen.push(region.textContent);
    };
    for (let tick = 0; tick <= 4; tick += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(tick === 0 ? 0 : 1_000);
      });
      record();
      if (tick === 1) expect(screen.getByText("0:02")).toBeInTheDocument();
    }

    expect(seen).toEqual([
      "You can try again in 3 seconds.",
      "You can try again now.",
    ]);
    expect(retry).toBeEnabled();
    expect(screen.queryByText(/Try again in/)).toBeNull();
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("a new 429 restarts the wait, even with the same number of seconds", async () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <ProblemView
        error={apiError("rate_limited", 429, 2)}
        onRetry={() => {}}
      />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();

    rerender(
      <ProblemView
        error={apiError("rate_limited", 429, 2)}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
    expect(screen.getByText("0:02")).toBeInTheDocument();
  });

  it("without Retry-After, retry is available at once and nothing is announced", () => {
    render(
      <ProblemView error={apiError("rate_limited", 429)} onRetry={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
    expect(screen.getByRole("status")).toHaveTextContent("");
    expect(announcementsDuring(() => {})).toEqual([]);
  });
});

describe("offline banner", () => {
  const setOnline = (online: boolean) => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(online);
    act(() => {
      window.dispatchEvent(new Event(online ? "online" : "offline"));
    });
  };

  it("follows the browser's online and offline events", () => {
    render(<OfflineBanner />);
    const region = screen.getByRole("status");
    expect(region).toBeEmptyDOMElement();

    setOnline(false);
    expect(region).toHaveTextContent("You appear to be offline");
    setOnline(true);
    expect(region).toBeEmptyDOMElement();
  });

  it("shows after a network error while navigator.onLine is still true; the next success hides it", () => {
    render(<OfflineBanner />);
    act(() => reportNetworkFailure());
    expect(navigator.onLine).toBe(true);
    expect(screen.getByRole("status")).toHaveTextContent(
      "You appear to be offline",
    );

    act(() => reportNetworkSuccess());
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("coming back online clears a network failure", () => {
    render(<OfflineBanner />);
    act(() => reportNetworkFailure());
    setOnline(true);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("renders empty on the server, which cannot know", () => {
    expect(renderToString(<OfflineBanner />)).toBe(
      '<div aria-live="polite" data-offline-banner="" role="status"></div>',
    );
  });
});

describe("static states", () => {
  it("EmptyState shows its message and one action", () => {
    render(
      <EmptyState
        action={<button type="button">Clear filters</button>}
        headingLevel={3}
        message="Try widening your search."
        title="No cars match"
      />,
    );
    expect(
      screen.getByRole("heading", { level: 3, name: "No cars match" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Clear filters" }),
    ).toBeInTheDocument();
  });

  it("PermissionDenied and NotFound take their copy from problem-ui", () => {
    render(
      <>
        <PermissionDenied action={<button type="button">Home</button>} />
        <NotFound action={<button type="button">Search</button>} />
      </>,
    );
    expect(
      screen.getByRole("heading", { name: "You do not have access" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: PROBLEM_UI.not_found.title }),
    ).toBeInTheDocument();
  });

  it("ErrorState hides retry without a handler, and renders on the server", () => {
    const html = renderToString(
      <ErrorState requestId="req_1" ui={PROBLEM_UI.internal_error} />,
    );
    expect(html).toContain("Something went wrong");
    expect(html).toContain("req_1");
    expect(html).not.toContain("Try again</button>");
  });
});
