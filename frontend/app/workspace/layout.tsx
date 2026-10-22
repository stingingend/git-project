import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Workspace · CodeAtlas",
  robots: { index: false, follow: false },
};
export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
