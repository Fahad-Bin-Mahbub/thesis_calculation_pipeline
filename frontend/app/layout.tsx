import "./globals.css";
import type { Metadata } from "next";
import { Manrope, Source_Serif_4 } from "next/font/google";

const bodyFont = Manrope({
  subsets: ["latin"],
  variable: "--font-body"
});

const serifFont = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-serif"
});

export const metadata: Metadata = {
  title: "Email Analysis Pipeline",
  description: "Key-value analysis pipeline for the email encryption study"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${bodyFont.variable} ${serifFont.variable} font-[var(--font-body)]`}>{children}</body>
    </html>
  );
}
