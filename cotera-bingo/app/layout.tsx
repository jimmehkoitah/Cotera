import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cotera · Booth Bingo",
  description: "Match three live Bingo calls, or share three work problems. Compare notes with Cotera over hot chocolate.",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
