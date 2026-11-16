import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";
import { env } from "@/lib/env";
import { APP_NAME } from "@/lib/brand";
import { SITE_CLAIM } from "@/lib/site-copy";
import { fontVariables } from "./fonts";
import "./globals.css";

// The product's main claim, word for word: the landing page headline is the same sentence (SITE_CLAIM).
const TITLE = `${APP_NAME} — every approval your concept needs at an address`;

export const metadata: Metadata = {
  metadataBase: new URL(env.siteUrl),
  title: {
    default: TITLE,
    template: `%s · ${APP_NAME}`,
  },
  description: `${SITE_CLAIM} Location Risk Memos for San Francisco bars, restaurants and cafes, built from SF Planning, Entertainment Commission, ABC and Planning Commission records. Plus a free permit checklist for any US city.`,
  applicationName: APP_NAME,
  openGraph: {
    title: TITLE,
    description: `${SITE_CLAIM} Built from SF Planning, Entertainment Commission, ABC and Planning Commission records.`,
    url: env.siteUrl,
    siteName: APP_NAME,
    type: "website",
  },
  twitter: {
    card: "summary",
    title: TITLE,
    description: SITE_CLAIM,
  },
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  themeColor: "#141b2d",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={fontVariables}>
      <body className="min-h-dvh font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
