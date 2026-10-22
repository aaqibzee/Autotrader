import type { Route } from "next";

/**
 * Links the shell renders to pages later features build (Feature 03 §5). Typed routes
 * reject paths that do not exist yet, so they are cast here, in one list, and each
 * owning feature removes its cast when the page lands.
 */
export const SHELL_ROUTES = {
  home: "/" as Route,
  search: "/search" as Route, // Feature 07
  valuation: "/value-my-car" as Route, // Feature 12
  forDealers: "/dealer" as Route,
  signIn: "/sign-in" as Route, // Feature 04
  account: "/account" as Route,
  terms: "/terms" as Route, // Feature 15
  privacy: "/privacy" as Route, // Feature 15
  cookies: "/cookies" as Route, // Feature 15
  dealerStock: "/dealer/stock" as Route, // Feature 05
  dealerLeads: "/dealer/leads" as Route, // Feature 10
  dealerTeam: "/dealer/team" as Route, // Feature 04
  dealerSettings: "/dealer/settings" as Route, // Feature 04
} as const;
