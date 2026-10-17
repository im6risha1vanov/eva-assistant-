import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ева — диалог в контексте",
  description: "Полная переписка, ответы администратора и черновики Евы. Общие корректировки вместо правки каждого сообщения.",
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
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  );
}
