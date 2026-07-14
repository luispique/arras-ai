export interface Ejemplo { id: string; etiqueta: string; texto: string; }

export const EJEMPLOS: Ejemplo[] = [
  {
    id: "penitenciales",
    etiqueta: "Penitenciales (bien redactado)",
    texto:
      "CONTRATO DE ARRAS PENITENCIALES. En Madrid, a 15 de marzo de 2025. Dña. María " +
      "Fernández (NIF 12345678Z), vendedora, y D. Javier López (NIF 87654321X), comprador, " +
      "sobre la vivienda en calle Goya 78, 3ºB, 28001 Madrid, referencia catastral " +
      "9872023VH5797S0001WX, libre de cargas, precio 280.000 €. El comprador entrega 28.000 € " +
      "en concepto de arras penitenciales conforme al artículo 1454 del Código Civil. La " +
      "escritura se otorgará antes del 15 de junio de 2025. La eficacia se condiciona a la " +
      "obtención de financiación hipotecaria en 45 días.",
  },
  {
    id: "confirmatorias",
    etiqueta: "Confirmatorias (con problemas)",
    texto:
      "CONTRATO PRIVADO DE COMPRAVENTA CON SEÑAL. En Valencia, a 3 de abril de 2025. D. Antonio " +
      "Martínez (DNI 44556677P), vendedor, y Dña. Laura Gómez (DNI 11223344Q), compradora, sobre " +
      "el piso en avenida del Puerto 210, 5º, Valencia. Precio 190.000 €. La compradora entrega " +
      "10.000 € en concepto de señal y a cuenta del precio total; dicha cantidad confirma el " +
      "contrato. Las partes elevarán a escritura pública en el plazo más breve posible. Los " +
      "gastos se distribuirán conforme a la ley.",
  },
];
