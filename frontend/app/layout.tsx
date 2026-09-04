import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PM Copilot — AI 产品经理助手",
  description: "需求决策、PRD 生成、压力测试的 Multi-Agent 协作平台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark h-full overflow-hidden">
      <body
        className={`${inter.className} h-full overflow-hidden bg-background text-foreground`}
      >
        {children}
      </body>
    </html>
  );
}
