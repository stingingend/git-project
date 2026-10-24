import type { Metadata } from "next";
import "./globals.css";
import "./theme.css";
import "./workspace.css";

export const metadata: Metadata = {
  title: "CodeAtlas — Find your way through the code",
  description:
    "Turn a public GitHub repository into a connected map of Python, JavaScript, TypeScript, C, and C++ code. Explore dependencies, search symbols, and investigate changes with source-backed insights.",
  openGraph: {
    title: "CodeAtlas — Less searching. More understanding.",
    description:
      "Explore the structure, find answers, and see what a change could touch.",
    type: "website",
  },
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
