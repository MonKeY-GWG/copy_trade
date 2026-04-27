import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Copy Trade Console",
  description: "Operational console for Copy Trade foundation controls"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
