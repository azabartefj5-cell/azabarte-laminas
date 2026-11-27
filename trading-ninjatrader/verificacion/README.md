# Verificación de SistemaCombinadoES fuera de NinjaTrader

Esta carpeta **no** hace falta para usar la estrategia en NinjaTrader. Sirve para compilarla y
ejercitar su lógica en Linux, macOS o Windows con el SDK de .NET 8.

- `Stub/`: una imitación mínima de la API de NinjaTrader 8, con sólo lo que usa la estrategia.
  Incluye un motor de órdenes sencillo: las órdenes a mercado se ejecutan a la apertura de la barra
  siguiente con 1 tick de deslizamiento, y los stops y objetivos se comparan con el máximo y el
  mínimo de la barra, contando primero el stop. **No es NinjaTrader**: sus resultados en dólares no
  predicen los de Strategy Analyzer.
- `Estrategia/`: compila `../SistemaCombinadoES.cs` y `../SistemaCombinadoESAjuste.cs` con **C# 5**, con los avisos tratados como
  errores.
- `Pruebas/`: genera barras sintéticas (paseo aleatorio con días de tendencia, festivos, días de
  cierre anticipado y cambios de horario de EE. UU. y Europa). Ejecuta diez escenarios (barras de 1, 2 y 5 minutos) y comprueba
  las reglas con cálculos independientes.

```bash
cd trading-ninjatrader/verificacion/Pruebas
dotnet run -c Release
```

Debe terminar con `RESULTADO: todas las comprobaciones correctas`.
