"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SHELL_ROUTES } from "./routes";

/**
 * The header's signed-in/out slot (Feature 03 §5, A8): the only personal data in the
 * public shell, so it renders in the browser, never on the server, and public pages stay
 * cacheable. Its box is fixed at SSR, so swapping states shifts nothing (CLS < 0.01).
 *
 * `load` fetches the account. Feature 04 passes one calling `GET /users/me` once that path
 * is in the API contract; until then there is none, and the island renders signed-out
 * without a request. A 401 or 404 means signed out; any other failure also shows
 * signed-out, silently: a broken header must not block browsing.
 */
export type Account = { displayName: string };

type State =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "signed-in"; account: Account };

/** Fixed size: wide enough for "Sign in" and the signed-in pill at every breakpoint. */
const BOX = "flex h-11 w-28 shrink-0 items-center justify-end";

export function AccountIsland({
  load,
}: {
  load?: () => Promise<Account | null>;
}) {
  const [state, setState] = useState<State>(
    load ? { status: "loading" } : { status: "signed-out" },
  );

  useEffect(() => {
    if (!load) return;
    let cancelled = false;
    load().then(
      (account) => {
        if (!cancelled)
          setState(
            account
              ? { status: "signed-in", account }
              : { status: "signed-out" },
          );
      },
      () => {
        // 401/404 mean signed out; anything else is shown the same way, silently. The
        // API's own error reporting sees server failures; the header must stay usable.
        if (!cancelled) setState({ status: "signed-out" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load]);

  return (
    <div className={BOX} data-account-island={state.status}>
      {state.status === "loading" ? (
        <span
          aria-hidden="true"
          className="h-9 w-24 animate-pulse rounded-full bg-sunken motion-reduce:animate-none"
        />
      ) : state.status === "signed-in" ? (
        <Link
          className="inline-flex h-11 max-w-full items-center gap-2 rounded-full px-2 text-sm font-semibold text-ink hover-state:bg-sunken"
          href={SHELL_ROUTES.account}
        >
          <span
            aria-hidden="true"
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-tint text-brand-strong"
          >
            {state.account.displayName.slice(0, 1).toUpperCase()}
          </span>
          <span className="truncate">
            <span className="sr-only">
              Your account, signed in as {state.account.displayName}
            </span>
            <span aria-hidden="true">Account</span>
          </span>
        </Link>
      ) : (
        <Link
          className="inline-flex h-11 items-center rounded-md px-3 text-sm font-semibold text-brand-strong hover-state:bg-brand-tint"
          href={SHELL_ROUTES.signIn}
        >
          Sign in
        </Link>
      )}
    </div>
  );
}
