# Sistema combinado para futuros del S&P 500 en NinjaTrader 8

`SistemaCombinadoES.cs` es una estrategia automática de NinjaScript para los futuros del S&P 500:
**ES**, el contrato grande, o **MES**, el micro, que es 10 veces más pequeño. Reúne en un solo
archivo tres de los sistemas automáticos públicos mejor documentados. Cada uno se activa o
desactiva por separado, y los tres comparten la misma gestión de riesgo.

> **Aviso importante.** Esto es software educativo, no asesoramiento financiero. Los futuros están
> apalancados: puedes perder más de lo que tienes depositado. Ningún sistema de esta carpeta se ha
> probado con datos reales del ES. Desde el entorno donde se escribió no había acceso a datos de
> mercado, así que las rentabilidades citadas abajo son las que publican sus autores y las réplicas,
> y no las he verificado yo. La prueba que cuenta es tu propio backtest en *Strategy Analyzer*,
> seguido de varias semanas en cuenta simulada.

---

## 1. Investigación: qué sistemas se han combinado y por qué

| Módulo | Origen | Idea | Evidencia publicada | Estado por defecto |
|---|---|---|---|---|
| **1. Momentum intradía "Noise Area"** | Zarattini, Aziz y Barbon, *Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)*, 2024 | Cuando el precio sale de su "zona de ruido" habitual para esa hora del día, tiende a seguir en esa dirección hasta el cierre | SPY 2007–2024: +1.985 % total neto de costes, 19,6 % anual, Sharpe 1,33 (SFI). Las réplicas independientes en futuros ES/NQ salen más modestas: ≈8 % anual, Sharpe ≈0,9, 36 % de aciertos con ganancia media 2× la pérdida media (Quantitativo); Sharpe ≈0,7–0,8 en un foro de QuantConnect | **Activado**: es el sistema con mejor respaldo |
| **2. Opening Range Breakout (ORB) de 5 min** | Zarattini y Aziz, *Can Day Trading Really Be Profitable?*, 2023 (idea original de Toby Crabel) | La dirección de la primera vela de 5 minutos anticipa la del día | QQQ 2016–2023: 33,2 % anual frente a 14,9 % de comprar y mantener, **sin deslizamiento** (CXO). Las réplicas indican que la ventaja bruta existe pero **desaparece con los costes**: el objetivo de 10R sólo se alcanza en un 2–3 % de las operaciones, y un estudio en futuros con 16 años de datos concluye que no sobrevive a los costes | **Desactivado**: actívalo sólo si tu backtest con comisiones lo justifica |
| **3. Swing RSI(2) de Connors** | Larry Connors y Cesar Alvarez, *Short Term Trading Strategies That Work*, 2008 | En tendencia alcista, las caídas bruscas de 2–3 días tienden a rebotar | SPY 1993–2026: factor de beneficio 2,5–3,5 según el umbral (Quantified Strategies). Con un 71 % de aciertos rinde menos que comprar y mantener porque está poco tiempo en el mercado (Backtrex) | **Activado**: aporta operaciones distintas a las del momentum |

**Por qué combinarlos.** El momentum intradía gana en los días de tendencia y en las caídas fuertes,
porque también opera en corto, y siempre termina el día sin posición. El RSI(2) gana justo en los
retrocesos dentro de una tendencia alcista y mantiene la posición varios días. Son fuentes de
beneficio distintas y poco correlacionadas. El ORB se incluye porque es el sistema más citado, pero
queda apagado por la evidencia en contra una vez descontados los costes.

**Qué se descartó.** Los cruces de medias y los sistemas tendenciales tipo Turtle funcionan mejor en
carteras diversificadas de muchos mercados que en un solo índice. Los indicadores "mágicos" que se
venden en foros no tienen evidencia pública.

---

## 2. Reglas exactas de cada módulo

Todas las horas son **hora de Nueva York**. La estrategia convierte la hora de cada barra, así que
da igual que tu NinjaTrader esté en hora de España. En España suelen ser 6 horas más, y 5 durante
las semanas del año en que los cambios de horario no coinciden.

### Módulo 1 · Momentum intradía (Noise Area + VWAP)

1. Para cada hora del día *t* calcula **σ(t)**: la media, en los últimos 14 días, de
   `|precio a la hora t / apertura de ese día − 1|`.
2. Bandas de hoy:
   - `banda superior = max(apertura de hoy, cierre de ayer) × (1 + σ(t))`
   - `banda inferior = min(apertura de hoy, cierre de ayer) × (1 − σ(t))`
3. Revisa cada 30 minutos (10:00, 10:30 … 15:30):
   - sin posición: **compra** si el precio está por encima de la banda superior y **vende en corto**
     si está por debajo de la inferior;
   - en largo: sale si el precio cae por debajo de `max(banda superior, VWAP)`. Si además rompe la
     banda inferior, gira a corto en la barra siguiente;
   - en corto: la regla simétrica, con `min(banda inferior, VWAP)`.
4. Cierra todo a las **15:55**, o 15 minutos antes del fin de la sesión en los días de cierre
   anticipado.
5. Pone un **stop de emergencia** real en el mercado a 0,5 × el ATR diario, por si se corta la
   conexión. El paper no lo tiene; es protección extra.
6. Tamaño dinámico, opcional y como en el paper: `apalancamiento = min(4, 2 % / volatilidad diaria de 14 días)`.

### Módulo 2 · Opening Range Breakout (desactivado por defecto)

1. Toma la primera vela de 5 minutos (9:30–9:35). Si cierra por encima de su apertura opera en
   largo, si cierra por debajo opera en corto, y si es doji no opera.
2. Entra a la apertura de la vela siguiente, con el stop en el extremo opuesto de la primera vela.
3. Objetivo a 10 veces el riesgo (10R). Si no se alcanza, sale a las 15:55.
4. Tamaño dinámico: arriesga el 1 % del capital, con un apalancamiento máximo de 4.

### Módulo 3 · Swing RSI(2) de Connors

1. A las 16:00, al cierre, calcula el RSI de 2 periodos y las medias de 200 y 5 días con los
   cierres de la sesión regular.
2. **Compra** si `cierre > media de 200 días` y `RSI(2) < 10`.
3. **Vende** cuando `cierre > media de 5 días`, o al cabo de 10 días como máximo.
4. Stop de catástrofe a 3 × el ATR diario. El sistema original no lleva stop; si pones el
   parámetro a 0, se comporta como el original.
5. Variante en corto opcional, desactivada porque históricamente es débil en el S&P 500.

### Reglas comunes de riesgo

- **Sin señales contrarias.** Si un módulo está en largo, ningún otro puede abrir un corto, y al
  revés. Así se evita que NinjaTrader invierta la posición de otro módulo; la señal bloqueada
  simplemente no se opera. Los módulos sí pueden sumar posiciones en el mismo sentido.
- **Máximo de contratos** abiertos entre todos los módulos (3 por defecto).
- **Pérdida diaria máxima** en USD, desactivada por defecto. **Actívala antes de operar en real.**
  Al alcanzarla, la estrategia cierra todo y no vuelve a operar hasta el día siguiente.
- **Fechas excluidas**: días sin entradas nuevas, por ejemplo días de FOMC o IPC. Se escriben así:
  `2026-12-09;2027-01-27`.
- **Filtro de tendencia intradía**, opcional: momentum y ORB sólo operan en largo por encima de la
  media de 200 días y sólo en corto por debajo.
- **Días de cierre anticipado** (Black Friday, víspera del 4 de julio, etc.): la estrategia lee el
  fin real de la sesión de la plantilla de horario de NinjaTrader. Cierra lo intradía y toma la
  decisión del RSI(2) 15 minutos antes de ese fin.

---

## 3. Instalación en NinjaTrader 8

1. Copia `SistemaCombinadoES.cs` en
   `Documentos\NinjaTrader 8\bin\Custom\Strategies\`.
2. En NinjaTrader abre **New → NinjaScript Editor**, despliega *Strategies*, abre
   `SistemaCombinadoES` y pulsa **Compile (F5)**. Debe terminar sin errores.
3. Si se queja de otro archivo de tu carpeta *Custom*, ese error no es de esta estrategia: arregla o
   quita ese archivo, porque NinjaTrader compila todo junto.

### Backtest en Strategy Analyzer (primer paso obligatorio)

**New → Strategy Analyzer**, con esta configuración:

| Opción | Valor |
|---|---|
| Strategy | `SistemaCombinadoES` |
| Instrument | El contrato vigente, p. ej. `MES 12-26` (o `MES 03-27` tras el roll de diciembre). Para años de historia usa el continuo `ES ##-##` con *Merge policy* "Merge back adjusted" (Tools → Options → Data) |
| Type / Value | **Minute / 5** |
| Trading hours | **CME US Index Futures ETH** |
| Start date | Al menos 1 año antes del periodo que quieras evaluar: el RSI(2) necesita 200 sesiones para arrancar y el momentum 14 |
| Include commission | Sí, con tu plantilla de comisiones. Sin comisiones, el resultado no sirve |
| Slippage | 1 tick, el valor por defecto de la estrategia |
| Exit on session close | **false**. Si lo activas, cerrará cada día la posición del RSI(2) |
| Calculate | On bar close |

Mira sobre todo la **máxima caída (drawdown)**, el número de operaciones y la curva de capital, más
que el beneficio total. Prueba cada módulo por separado y luego juntos.

### Cuenta simulada y después real

1. Abre un gráfico de 5 minutos de **MES** (contrato vigente) con la plantilla ETH y al menos
   **365 días cargados**. En la pestaña *Data Series* del gráfico, pon *Days to load* a 365.
2. Clic derecho → **Strategies** → añade `SistemaCombinadoES` → cuenta **Sim101** → *Enabled*.
3. Verás tres líneas: la **banda superior** en azul, la **inferior** en rojo y el **VWAP** en
   dorado. Con *Depurar* = true, cada decisión aparece en *New → NinjaScript Output*.
4. Si tienes datos de *Market Replay*, puedes ensayar días pasados con la conexión **Playback**.
5. Sólo después de varias semanas en simulación que se parezcan al backtest, plantéate el real:
   - empieza con **MES y 1 contrato por módulo**;
   - pon **Pérdida diaria máxima**, por ejemplo un 1–2 % de la cuenta;
   - el PC (o un VPS) debe estar encendido y conectado durante la sesión, porque las salidas por
     VWAP y por hora las envía la estrategia;
   - **cambio de contrato (roll)**: el ES vence en marzo, junio, septiembre y diciembre. Unos días
     antes del vencimiento, cierra la posición, desactiva la estrategia, cambia el gráfico al
     contrato nuevo y vuelve a activarla.

### Tamaño de la posición

- **ContratosFijos**, por defecto: cada módulo opera los contratos que le indiques (1 por defecto).
  Es lo más sencillo de controlar.
- **Dinamico**: usa *Capital de la cuenta*. El momentum aplica el objetivo de volatilidad del paper
  y el ORB y el RSI(2) arriesgan un % fijo hasta su stop.
- Ten en cuenta el tamaño de cada contrato: un **ES vale 50 $ por punto** y un **MES 5 $ por
  punto**. Con el índice a 6.000 puntos, un ES equivale a unos 300.000 $ de exposición y un MES a
  unos 30.000 $. Con cuentas de menos de 100.000 $, usa **MES**.

---

## 4. Parámetros

Grupo **0. General**

| Parámetro | Defecto | Qué hace |
|---|---|---|
| Modo de tamaño | ContratosFijos | `ContratosFijos` o `Dinamico` |
| Capital de la cuenta (USD) | 50.000 | Base del tamaño dinámico |
| Reinvertir beneficios | false | Suma al capital el resultado cerrado. Pensado para backtests: en tiempo real incluiría las operaciones históricas simuladas |
| Máximo de contratos | 3 | Límite total entre los tres módulos |
| Pérdida diaria máxima (USD) | 0 (desactivado) | Cierra todo y bloquea el día |
| Inicio / fin sesión regular | 930 / 1600 | Horas en formato HHMM de Nueva York |
| Cierre posiciones intradía | 1555 | Hora de salida de momentum y ORB |
| Fechas excluidas | vacío | `yyyy-MM-dd;yyyy-MM-dd` |
| Filtro de tendencia intradía | false | Momentum y ORB a favor de la media de 200 días |
| SMA de tendencia | 200 | Periodo de ese filtro |
| ATR diario | 14 | Para los stops de emergencia y el tamaño |
| Depurar | false | Escribe cada decisión en la ventana Output |

Grupo **1. Momentum**: activar, 14 días, multiplicador 1, primera revisión 1000, cada 30 min,
última entrada 1530, stop con VWAP, 1 contrato, volatilidad objetivo 2 %, apalancamiento máximo 4
y stop de emergencia 0,5 × ATR.

Grupo **2. ORB**: activar (false), 5 minutos, objetivo 10R, 1 contrato, riesgo 1 % y
apalancamiento máximo 4.

Grupo **3. RSI(2)**: activar, periodo 2, entrada con RSI < 10, media de 200 días, salida por la
media de 5 días, máximo 10 días, stop 3 × ATR, cortos (false), decisión a las 1600, 1 contrato,
riesgo 1 % y apalancamiento máximo 1.

> Con la plantilla de horario **RTH** en lugar de ETH, pon *Hora de decisión* del RSI(2) a 1555 y
> *Cierre intradía* a 1550. Así las órdenes se ejecutan antes de que acabe la sesión, y no a la
> apertura del día siguiente.

**Sobre la optimización.** Resiste la tentación de optimizar los parámetros hasta que el backtest
quede perfecto, porque eso fabrica resultados que no se repiten. Los valores por defecto son los de
los papers originales. Si cambias algo, compruébalo en un periodo que no hayas usado para elegirlo.

---

## 5. Cómo se ha comprobado el código

La carpeta [`verificacion/`](verificacion/) contiene una imitación mínima de la API de
NinjaTrader 8 y un banco de pruebas con datos **sintéticos**. Lo que verifica:

- que la estrategia **compila con C# 5**, el nivel más conservador de NinjaTrader 8, sin errores ni
  avisos;
- que en más de 2.000 operaciones simuladas, con barras de 5 y de 1 minuto, no hay órdenes
  ignoradas, duplicadas ni inversiones de posición entre módulos, y que el seguimiento interno de
  posiciones coincide con la posición real;
- que cada entrada de momentum ocurre en una hora de revisión y fuera de las bandas, recalculadas de
  forma independiente;
- que las entradas del RSI(2) coinciden fecha por fecha con una simulación independiente de las
  reglas de Connors;
- que el ORB respeta la dirección y el stop de la primera vela;
- que nada intradía pasa la noche, incluidos los días de cierre anticipado (esto destapó un fallo
  que ya está corregido);
- que se obtienen **las mismas operaciones** con NinjaTrader en hora de Madrid y en hora de Nueva
  York, y aunque los stops lleguen sin `FromEntrySignal`, algo que ocurre en algunas versiones de
  NinjaTrader 8.

Lo que **no** verifica: la rentabilidad con datos reales, ni el comportamiento exacto del motor de
órdenes de NinjaTrader. Para eso están Strategy Analyzer y la cuenta Sim.

---

## 6. Fuentes

- Zarattini, Aziz y Barbon, *Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)*:
  [SFI](https://www.sfi.ch/fr/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy),
  [Concretum](https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/),
  [resumen de CXO Advisory](https://www.cxoadvisory.com/momentum-investing/complex-intraday-time-series-momentum-strategy-applied-to-spy/)
- Réplicas del momentum intradía:
  [Quantitativo, ES y NQ](https://www.quantitativo.com/p/intraday-momentum-for-es-and-nq),
  [svettelnova/intraday-momentum-spy](https://github.com/svettelnova/intraday-momentum-spy),
  [oleksandr123456787654321/spy_intraday_momentum](https://github.com/oleksandr123456787654321/spy_intraday_momentum),
  [foro de QuantConnect](https://www.quantconnect.com/forum/discussion/15192)
- Zarattini y Aziz, *Can Day Trading Really Be Profitable?*:
  [SSRN 4416622](https://papers.ssrn.com/abstract=4416622),
  [resumen de CXO Advisory](https://www.cxoadvisory.com/technical-trading/day-trading-with-an-opening-range-breakout-strategy)
- Críticas y réplicas del ORB:
  [réplica en QQQ con costes](https://github.com/giovannibrusco/zarattini-2023-orb-qqq),
  [réplica en cinco índices (MQL5)](https://www.mql5.com/en/blogs/post/776235),
  [estudio prerregistrado en futuros](https://www.researchgate.net/publication/414294507_Opening-Range_Breakout_Does_Not_Survive_Trading_Costs_A_Pre-Registered_225-Cell_Study_on_Sixteen_Years_of_Futures_Data),
  [QuantInsti](https://www.quantinsti.com/articles/opening-range-breakout-strategy/)
- RSI(2) de Connors:
  [StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2),
  [Quantified Strategies](https://www.quantifiedstrategies.com/what-is-the-best-rsi-oversold-level-we-tested-1-through-50/),
  [Backtrex](https://backtrex.com/en/backtests/connors-rsi-2-sp-500)
- NinjaTrader:
  [zona horaria de las barras](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1258776-how-to-convert-tradinghours-sessions-i-begintime-to-chart-timezone-or-vice-versa),
  [stops sin `FromEntrySignal`](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1037818-correlating-order-signal-name-with-exit-on-session-close-and-stop-loss-executions)
