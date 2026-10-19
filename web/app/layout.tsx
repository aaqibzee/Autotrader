import localFont from "next/font/local";
import type { Metadata } from "next";
import "./globals.css";

const archivo = localFont({
  src: "../node_modules/@fontsource-variable/archivo/files/archivo-latin-wght-normal.woff2",
  variable: "--font-archivo",
  display: "swap",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Autotrader | Foundation",
  description: "The foundation for a UK used-car marketplace.",
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