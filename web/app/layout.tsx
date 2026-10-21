import { BRAND } from "@/lib/brand";
import localFont from "next/font/local";
import type { Metadata } from "next";
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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-GB">
      <body className={archivo.variable}>{children}</body>
    </html>
  );
}
