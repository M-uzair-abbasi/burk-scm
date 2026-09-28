import type { Metadata } from "next";
import { JetBrains_Mono, Manrope } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";
import { TooltipProvider } from "@/components/ui/Tooltip";

// Manrope carries the UI voice; JetBrains Mono carries every figure, code and
// identifier (SKUs, barcodes, tracking numbers, threshold keys) so numeric
// columns align and references are unambiguous. Both are self-hosted by
// next/font at build time — no runtime request to Google.
const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Burk.pk SCM-OVS",
  description: "Supply Chain & Smart Order Verification System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`h-full antialiased ${manrope.variable} ${jetbrains.variable}`}
    >
      <body className="min-h-full flex flex-col">
        <TooltipProvider>
          <AuthProvider>{children}</AuthProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
