import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PhantomPilot — Run Your Team from WhatsApp",
  description: "Assign tasks, track progress, and manage your entire operation from WhatsApp. No app downloads. Built for Indian businesses.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
