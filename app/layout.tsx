import type React from "react";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import Navbar from "@/components/navbar";
import { Noto_Sans_Thai } from "next/font/google"; // Import the font
import { Providers } from "@/lib/providers";
const inter = Inter({ subsets: ["latin"] });

// Configure the font
const notoSansThai = Noto_Sans_Thai({
  subsets: ["thai", "latin"], // IMPORTANT: Include 'thai' subset
  weight: ["100", "200", "300", "400", "500", "600", "700", "800", "900"], // Specify weights you need
  variable: "--font-noto-sans-thai", // Optional: for CSS variable usage
  display: "swap", // Recommended for performance
});

export const metadata: Metadata = {
  title: "RRS Audio Transcriber",
  description: "Transcribe your audio files with ease",
  generator: "v0.dev",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={notoSansThai.className}>
        <Providers>
          <ThemeProvider
            attribute="class"
            defaultTheme="system"
            enableSystem
            disableTransitionOnChange
          >
            <Navbar />
            <main className="container mx-auto py-6 px-4">{children}</main>
          </ThemeProvider>
        </Providers>
      </body>
    </html>
  );
}
