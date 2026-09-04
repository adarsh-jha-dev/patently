import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Patently — prior art analysis",
  description:
    "Describe an invention in plain English. Get a claim-element map of the prior art that reads on it.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
