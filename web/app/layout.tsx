import { Providers } from "@/components/providers";
import { BRAND } from "@/lib/brand";
import localFont from "next/font/local";
import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

const archivo = localFont({
  src: "../node_modules/@fontsource-variable/archivo/files/archivo-latin-wght-normal.woff2",
  variable: "--font-archivo",
  display: "swap",
  weight: "100 900",
  // Metric-matched Arial fallback, so the swap to Archivo shifts no layout (Feature 03 §1).
  adjustFontFallback: "Arial",
  fallback: ["ui-sans-serif", "system-ui", "sans-serif"],
});

export const metadata: Metadata = {
  title: BRAND.name,
  description: BRAND.description,
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // The per-request CSP nonce (middleware.ts). React Aria inserts one <style> at runtime
  // (usePress's touch-action rule) and takes its nonce from this meta tag; without it the
  // CSP blocks the rule (slice 3.7). The value goes in the `nonce` attribute, which the
  // browser hides from the DOM once parsed, rather than in `content`, which it would not.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en-GB">
      <head>
        <meta name="csp-nonce" nonce={nonce} />
      </head>
      <body className={archivo.variable}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
