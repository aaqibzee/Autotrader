"use client";

import {
  type Account,
  AccountIsland,
} from "@/components/layout/account-island";
import { requestApi } from "@/lib/api/response";

// Module-level, so the island's effect runs once. Passes the page's `?delay=` through.
const load = () =>
  requestApi<Account>(`/dev/account-probe${window.location.search}`, {
    timeoutMs: 10_000,
  });

export function DevAccountIsland() {
  return <AccountIsland load={load} />;
}
