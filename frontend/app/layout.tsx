import type { Metadata } from "next";
import Header from "@/components/Header";
import AuthGate from "@/components/AuthGate";
import "./globals.css";
export const metadata: Metadata = { title: { default: "Net Billy | Offerte e bollette", template: "%s | Net Billy" }, description: "Carica le condizioni economiche e confronta le offerte luce e gas a partire dalla tua bolletta." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="it"><body><AuthGate><a className="skip-link" href="#main">Vai al contenuto</a><Header /><main id="main">{children}</main><footer className="footer shell"><span>NET BILLY<span className="brand-dot">.</span> <small>ENERGY WORKSPACE</small></span><p>Analizza bollette e condizioni economiche in un unico spazio.</p><span className="footer-label">LUCE & GAS</span></footer></AuthGate></body></html>;
}
