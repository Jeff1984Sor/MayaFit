import { Archivo, Cormorant_Garamond, Fraunces } from "next/font/google";

// Fontes de título dos 3 temas. Sem preload: o navegador só baixa a do tema em uso (as outras nem são pedidas).
const fraunces = Fraunces({ variable: "--font-fraunces", subsets: ["latin"], display: "swap", preload: false });
const cormorant = Cormorant_Garamond({
  variable: "--font-cormorant",
  subsets: ["latin"],
  weight: ["500", "600"],
  display: "swap",
  preload: false,
});
const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin"], display: "swap", preload: false });

export const FONTES_SITE = `${fraunces.variable} ${cormorant.variable} ${archivo.variable}`;
