import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";

import { AppHeader } from "@/components/AppHeader";
import "./globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-jakarta",
});

export const metadata: Metadata = {
  title: "Lab Occupancy System",
  description: "VNRVJIET lab availability and timetable management",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${jakarta.variable} h-full`}>
      <body className="flex min-h-full flex-col antialiased">
        <AppHeader />
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
