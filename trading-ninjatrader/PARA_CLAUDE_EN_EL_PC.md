# Traspaso para Claude en el PC: estrategia SistemaCombinadoES para NinjaTrader 8

> **Para ti, usuario:** abre Claude en tu PC (Claude Code o la app de escritorio con acceso a
> archivos), adjunta este documento y escribe:
> *"Lee este documento entero y sigue la sección 2, Instrucciones para Claude."*
>
> **Para ti, Claude del PC:** este documento lo escribió otra sesión de Claude en la nube, que no
> tenía acceso a este PC ni a NinjaTrader. Contiene todo lo necesario: contexto, tareas, reglas de
> seguridad y el código completo (sección 8). Trabaja en español con el usuario.

---

## 1. Contexto

- **Lo que pidió el usuario:** un sistema de trading automático para NinjaTrader 8, sobre los
  futuros del S&P 500, que combine en uno los mejores sistemas automáticos públicos.
- **Lo que se construyó:** `SistemaCombinadoES.cs`, una estrategia NinjaScript (C#) para **ES** o
  **MES**, que reúne tres módulos:
  1. **Momentum intradía "Noise Area" + VWAP** (Zarattini, Aziz y Barbon, 2024). Activado.
  2. **Opening Range Breakout de 5 minutos** (Zarattini y Aziz, 2023). Desactivado por defecto,
     porque las réplicas indican que no sobrevive a los costes.
  3. **Swing RSI(2) de Connors**. Activado.
- **Dónde está:** repositorio público `azabartefj5-cell/azabarte-laminas`, carpeta
  `trading-ninjatrader/`, en la rama `claude/kind-hypatia-y1q8gz`. Hay un PR en borrador:
  https://github.com/azabartefj5-cell/azabarte-laminas/pull/9. Cuando se fusione, estará en `main`.
- **Estado:**
  - Compila con C# 5 contra una imitación de la API de NinjaTrader 8.
  - La lógica se verificó con datos sintéticos, y pasan las 7 pruebas.
  - **Nunca se ha compilado en un NinjaTrader real**, ni se ha probado con datos reales del ES.
  - Tu trabajo es dar esos dos pasos con el usuario.

---

## 2. Instrucciones para Claude (en este orden)

### Reglas de seguridad (obligatorias)

1. **Nunca actives la estrategia en una cuenta real**, es decir, cualquier cuenta que no sea
   `Sim101` u otra cuenta *Sim* o *Playback*. Tampoco cambies la cuenta de una estrategia ya activa.
   Las dos cosas requieren que el usuario lo confirme expresamente en ese momento.
2. No envíes órdenes manuales ni toques posiciones abiertas.
3. No modifiques ni borres otros scripts de `bin\Custom`. Antes de sobrescribir un archivo, haz una
   copia de seguridad.
4. Si editas `SistemaCombinadoES.cs`, mantén la **sintaxis C# 5**: nada de `$"..."`, `?.`,
   `nameof`, `=>` en propiedades, `out var` ni tuplas. Algunas versiones de NinjaTrader 8 no lo
   compilan.
5. No optimices parámetros hasta que el backtest quede perfecto: eso fabrica resultados que no se
   repiten. Si se cambia algo, hay que validarlo en un periodo que no se haya usado para elegirlo.
6. No prometas rentabilidad: los números de la sección 6 son de los autores, no están verificados.

### Tarea 1. Localizar la carpeta de estrategias de NinjaTrader

La carpeta *Documentos* puede estar redirigida a OneDrive, así que no la supongas.

```powershell
$docs = [Environment]::GetFolderPath('MyDocuments')
$dest = Join-Path $docs 'NinjaTrader 8\bin\Custom\Strategies'
Test-Path $dest
$dest
```

Si `Test-Path` devuelve `False`, búscala:

```powershell
Get-ChildItem -Path $env:USERPROFILE -Directory -Recurse -Depth 4 -Filter 'NinjaTrader 8' -ErrorAction SilentlyContinue | Select-Object FullName
```

### Tarea 2. Instalar el archivo

**Opción A, recomendada:** descargarlo de GitHub tal cual, con su BOM UTF-8 incluido.

```powershell
$archivo = Join-Path $dest 'SistemaCombinadoES.cs'
if (Test-Path $archivo) { Copy-Item $archivo "$archivo.bak" -Force }
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/azabartefj5-cell/azabarte-laminas/claude/kind-hypatia-y1q8gz/trading-ninjatrader/SistemaCombinadoES.cs' -OutFile $archivo
(Get-FileHash $archivo -Algorithm SHA256).Hash
```

El hash esperado es
`EFD1AB14B106134A467D272461E0257C95F56FB3EA764FB21EE12B2813571AAC`. Si la rama ya no existe porque
el PR se fusionó, cambia `claude/kind-hypatia-y1q8gz` por `main` en la URL.

**Opción B, sin internet:** copia el bloque de código de la sección 8 en `$archivo`. Después vuelve a
guardarlo en UTF-8 con BOM, para que las tildes de los textos se lean bien:

```powershell
$t = [IO.File]::ReadAllText($archivo)
[IO.File]::WriteAllText($archivo, $t, (New-Object System.Text.UTF8Encoding $true))
```

Con la opción B el hash puede variar por los saltos de línea, y no pasa nada.

### Tarea 3. Compilar

1. Pide al usuario que abra NinjaTrader, si no está abierto, y después **New → NinjaScript Editor**.
2. En el panel derecho: **Strategies → SistemaCombinadoES**, doble clic, y **Compile (F5)**.
3. Si aparecen errores, pide al usuario el **texto exacto** de la lista de errores: archivo, línea y
   mensaje. Una captura de pantalla también sirve.
4. **Un error en otro archivo** de `bin\Custom` también impide compilar, porque NinjaTrader compila
   todo junto. En ese caso, el arreglo es en ese otro archivo y no en este.

### Tarea 4. Si hay errores de compilación en SistemaCombinadoES.cs

El código usa la API estándar de NinjaTrader 8, pero no se ha compilado nunca en NinjaTrader real.
Estos son los puntos con más riesgo, con un arreglo para cada uno:

| Síntoma | Arreglo |
|---|---|
| Error en `IsOverlay = true;` | Borra esa línea: las líneas dibujadas pueden quedar en otro panel, pero la lógica no cambia |
| Error en `Core.Globals.GeneralOptions.TimeZoneInfo` | Sustitúyelo por `TimeZoneInfo.Local`. Es válido mientras la zona de NinjaTrader (Tools → Options → General) sea la de Windows |
| Error en `SessionIterator`, `GetNextSession`, `ActualSessionEnd` o `Bars.IsFirstBarOfSession` | Son de `NinjaTrader.Data`. Comprueba que el `using NinjaTrader.Data;` está presente. Si no se puede resolver, quita el campo `sesiones`, la línea `sesiones = new SessionIterator(Bars);` y la llamada `ActualizarSesion();` con su método. Así sólo se pierde el ajuste de los días de cierre anticipado |
| Error en `Instrument.MasterInstrument.RoundToTickSize` | Usa `Math.Round(precio / TickSize) * TickSize` |
| Error en `SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit` | Es la ruta estándar de NinjaTrader 8. Revisa la ortografía antes de tocar la lógica |
| Errores de firma en `OnOrderUpdate` u `OnExecutionUpdate` | Copia la firma exacta de la ayuda de NinjaTrader 8 de tu versión, sin cambiar el cuerpo |
| `The type or namespace ... already contains a definition` | Otro script define un tipo con el mismo nombre. Renombra el espacio de nombres `SistemaCombinadoESComun` a uno único |

Después de cada cambio, vuelve a compilar. No cambies la lógica de trading para quitar un error de
compilación sin explicárselo al usuario.

### Tarea 5. Backtest en Strategy Analyzer

Pide al usuario que abra **New → Strategy Analyzer** con esta configuración:

| Opción | Valor |
|---|---|
| Strategy | `SistemaCombinadoES` |
| Instrument | `MES 12-26` (o `MES 03-27` tras el roll de diciembre). Para varios años usa el continuo `ES ##-##` con Tools → Options → Data → *Merge policy* = "Merge back adjusted" |
| Data series | Minute, 5 |
| Trading hours | **CME US Index Futures ETH** |
| Start date | Al menos 1 año antes del periodo a evaluar: el RSI(2) necesita 200 sesiones y el momentum 14 |
| Include commission | **Sí**, con la plantilla de comisiones de su bróker |
| Slippage | 1 tick |
| Exit on session close | **false**. Si se activa, cierra cada día la posición del RSI(2) |
| Calculate | On bar close |

Plan de pruebas que conviene seguir:

1. **Cada módulo por separado**: sólo momentum (RSI2 apagado), sólo RSI2 (momentum apagado) y sólo
   ORB. Después los activados por defecto juntos.
2. Para cada prueba, apunta: beneficio neto, **máxima caída (drawdown)**, número de operaciones,
   % de aciertos, beneficio medio por operación, factor de beneficio y la curva de capital.
3. Divide el histórico en dos mitades. Si una mitad gana y la otra pierde mucho, no es robusto.
4. Recuerda al usuario que el momentum gana poco por operación: si el resultado neto depende de
   tener comisiones o deslizamiento casi nulos, no sirve.

Si el usuario puede exportar los resultados (clic derecho en *Trades* → Export), analízalos con él.

### Tarea 6. Simulación en tiempo real

1. Gráfico de 5 minutos de **MES** (contrato vigente), plantilla ETH y **Days to load = 365** en
   *Data Series*.
2. Clic derecho → **Strategies** → añadir `SistemaCombinadoES` → cuenta **Sim101** → marcar
   **Enabled**.
3. Se deben ver tres líneas: la **banda superior** en azul, la **inferior** en rojo y el **VWAP** en
   dorado. Con el parámetro *Depurar* = true, las decisiones aparecen en
   **New → NinjaScript Output**.
4. Si hay datos de *Market Replay*, la conexión **Playback** permite ensayar días pasados.
5. Déjala varias semanas en Sim y compara su comportamiento con el backtest.

### Tarea 7. Paso a dinero real (sólo si el usuario lo decide)

Esta decisión es del usuario; tú sólo le recuerdas la lista:

- **MES**, 1 contrato por módulo y *Máximo de contratos* 2–3.
- **Pérdida diaria máxima** puesta, por ejemplo en el 1–2 % de la cuenta.
- PC o VPS encendido y conectado durante la sesión: las salidas por VWAP y por hora las envía la
  estrategia.
- **Roll trimestral** (marzo, junio, septiembre y diciembre): unos días antes del vencimiento,
  cerrar la posición, desactivar la estrategia, pasar el gráfico al contrato nuevo y reactivarla.
- Fechas de FOMC e IPC en *Fechas excluidas*, si el usuario quiere evitarlas.

---

## 3. Reglas de la estrategia

Todas las horas son **hora de Nueva York**. La estrategia convierte la hora de cada barra desde la
zona configurada en NinjaTrader, así que funciona igual en hora de España. En España suelen ser
6 horas más, y 5 durante las semanas en que los cambios de horario no coinciden.

### Módulo 1 · Momentum intradía (activado)

1. Para cada hora del día *t*: `σ(t)` = media, en los últimos 14 días, de
   `|precio a la hora t / apertura del día − 1|`.
2. Bandas: `superior = max(apertura, cierre de ayer) × (1 + σ(t))` e
   `inferior = min(apertura, cierre de ayer) × (1 − σ(t))`.
3. Revisa cada 30 minutos, de 10:00 a 15:30:
   - sin posición: compra por encima de la superior y vende en corto por debajo de la inferior;
   - en largo: sale si el precio cae por debajo de `max(superior, VWAP)`, y si además rompe la
     inferior, gira a corto en la barra siguiente;
   - en corto: lo simétrico, con `min(inferior, VWAP)`.
4. Cierra todo a las 15:55, o 15 minutos antes del fin de sesión en los días de cierre anticipado.
5. Stop de emergencia real en el mercado a 0,5 × el ATR diario.
6. Tamaño dinámico, opcional: `apalancamiento = min(4, 2 % / volatilidad diaria de 14 días)`.

### Módulo 2 · ORB de 5 minutos (desactivado)

1. Mira la primera vela de 5 minutos (9:30–9:35): si es alcista opera en largo, si es bajista en
   corto, y si es doji no opera.
2. Entra a la apertura de la vela siguiente, con el stop en el extremo opuesto de la primera vela.
3. Objetivo 10R. Si no se alcanza, sale a las 15:55.

### Módulo 3 · Swing RSI(2) de Connors (activado)

1. A las 16:00 compra si `cierre > media de 200 días` y `RSI(2) < 10`.
2. Sale cuando `cierre > media de 5 días`, o como máximo a los 10 días.
3. Stop de catástrofe a 3 × el ATR diario (0 = sin stop, como el original).
4. Cortos opcionales, desactivados.

### Reglas comunes

- **Sin señales contrarias.** Si un módulo está en largo, ningún otro abre un corto, y al revés: la
  señal bloqueada no se opera. Las posiciones en el mismo sentido sí se suman.
- **Máximo de contratos** total (3), **pérdida diaria máxima** (desactivada por defecto) y
  **fechas excluidas** (`yyyy-MM-dd;yyyy-MM-dd`).
- **Filtro de tendencia intradía**, opcional: momentum y ORB sólo a favor de la media de 200 días.
- `IsExitOnSessionCloseStrategy = false`, `StartBehavior = WaitUntilFlat` y 1 tick de deslizamiento
  en el backtest.

---

## 4. Parámetros (grupos en la ventana de la estrategia)

| Grupo | Parámetro | Defecto |
|---|---|---|
| 0. General | Modo de tamaño | ContratosFijos (o Dinamico) |
| | Capital de la cuenta (USD) | 50.000 |
| | Reinvertir beneficios | false (pensado sólo para backtest) |
| | Máximo de contratos | 3 |
| | Pérdida diaria máxima (USD) | 0 = desactivado |
| | Inicio / fin sesión regular (HHMM NY) | 930 / 1600 |
| | Cierre posiciones intradía | 1555 |
| | Fechas excluidas | vacío |
| | Filtro de tendencia intradía / SMA | false / 200 |
| | ATR diario (días) | 14 |
| | Depurar | false |
| 1. Momentum | Activar / días / multiplicador | true / 14 / 1,0 |
| | Primera revisión / frecuencia / última entrada | 1000 / 30 min / 1530 |
| | Stop con VWAP | true |
| | Contratos / vol. objetivo / apal. máx. | 1 / 2 % / 4 |
| | Stop de emergencia (× ATR) | 0,5 |
| 2. ORB | Activar / minutos / objetivo R | false / 5 / 10 |
| | Contratos / riesgo % / apal. máx. | 1 / 1 % / 4 |
| 3. RSI(2) | Activar / periodo / umbral | true / 2 / 10 |
| | SMA filtro / SMA salida / máx. días | 200 / 5 / 10 |
| | Stop (× ATR) / cortos | 3,0 / false |
| | Hora de decisión | 1600 (con la plantilla RTH: 1555, y cierre intradía 1550) |
| | Contratos / riesgo % / apal. máx. | 1 / 1 % / 1 |

Tamaño de los contratos: un **ES vale 50 $ por punto** y un **MES 5 $ por punto**. Con cuentas de
menos de 100.000 $, usa MES.

---

## 5. Cómo funciona el código por dentro (para depurar)

- **Datos diarios propios.** No usa series diarias de NinjaTrader. Con las barras de minutos
  construye cada sesión regular (apertura, máximo, mínimo, cierre y el movimiento a cada minuto) y
  guarda las últimas 400 en `historial`.
- **Señales por módulo.** Cada módulo tiene sus nombres de señal: `MOM_L`, `MOM_S`, `ORB_L`,
  `ORB_S`, `RSI2_L` y `RSI2_S`. Usa el enfoque gestionado de NinjaTrader con
  `EntryHandling.UniqueEntries`, y salidas `ExitLong` / `ExitShort` con nombre `<señal>_X`.
- **Posición por señal.** Se sigue en `OnExecutionUpdate`. Si un stop llega sin `FromEntrySignal`,
  la señal se deduce del orden de las entradas o del lado. Cada barra se compara con
  `Position`, y si la posición real es plana se pone todo a cero.
- **Fin de sesión.** `SessionIterator` da el fin real de la sesión según la plantilla de horario.
- **Conversión horaria.** `ANuevaYork()` pasa la hora de la barra (zona de NinjaTrader) a UTC y de
  ahí a Nueva York.
- **Ventana Output.** Con *Depurar* activado, cada entrada, salida y bloqueo se escribe allí.

---

## 6. Investigación y fuentes (resumen)

| Sistema | Evidencia publicada |
|---|---|
| Momentum intradía | SPY 2007–2024: +1.985 % neto, 19,6 % anual, Sharpe 1,33 (paper). Réplicas en futuros: Sharpe ≈0,7–0,9, ≈8 % anual, 36 % de aciertos |
| ORB 5 min | QQQ 2016–2023: 33,2 % anual sin deslizamiento. Réplicas: el objetivo de 10R se alcanza en el 2–3 % de las operaciones, y la ventaja neta de costes es casi nula |
| RSI(2) | SPY 1993–2026: factor de beneficio 2,5–3,5. Gana el 71 % de las veces, pero rinde menos que comprar y mantener porque está poco tiempo en el mercado |

Fuentes:
- https://www.sfi.ch/fr/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy
- https://www.quantitativo.com/p/intraday-momentum-for-es-and-nq
- https://papers.ssrn.com/abstract=4416622
- https://github.com/giovannibrusco/zarattini-2023-orb-qqq
- https://www.mql5.com/en/blogs/post/776235
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2
- https://www.quantifiedstrategies.com/what-is-the-best-rsi-oversold-level-we-tested-1-through-50/

---

## 7. Qué se verificó y qué no

Se verificó, con una imitación de NinjaTrader y datos sintéticos (carpeta
`trading-ninjatrader/verificacion/` del repositorio):

- la compilación con C# 5, sin avisos;
- que en más de 2.000 operaciones no hay órdenes ignoradas, duplicadas ni inversiones de posición;
- que las bandas de momentum coinciden con un cálculo independiente;
- que las entradas del RSI(2) coinciden con una simulación independiente;
- que el ORB respeta su vela y su stop;
- que nada intradía pasa la noche, tampoco en los días de cierre anticipado;
- que las operaciones son idénticas con la plataforma en hora de Madrid o de Nueva York.

**No se verificó:**
- la compilación en NinjaTrader real (tarea 3);
- el comportamiento exacto de su motor de órdenes;
- la rentabilidad con datos reales del ES (tarea 5).

---

## 8. Código completo: `SistemaCombinadoES.cs`

Guárdalo como `SistemaCombinadoES.cs` en `Documentos\NinjaTrader 8\bin\Custom\Strategies\`
(opción B de la tarea 2).

```csharp
// =====================================================================================
//  SistemaCombinadoES  -  Estrategia automática para futuros del S&P 500 (ES / MES)
//  Plataforma: NinjaTrader 8 (NinjaScript, C#)
// -------------------------------------------------------------------------------------
//  Combina en una sola estrategia tres sistemas públicos y documentados:
//
//   1) MOMENTUM INTRADÍA "NOISE AREA" (Zarattini, Aziz y Barbon, "Beat the Market: An
//      Effective Intraday Momentum Strategy for S&P500 ETF (SPY)", 2024).
//      Bandas de ruido según la hora del día (media de |cierre_t / apertura - 1| de los
//      últimos 14 días). Se compra si el precio rompe la banda superior y se vende en corto
//      si rompe la inferior; revisión cada 30 min; stop dinámico en max(banda, VWAP);
//      cierre obligatorio antes del final de la sesión regular.
//
//   2) OPENING RANGE BREAKOUT de 5 minutos (Zarattini y Aziz, "Can Day Trading Really Be
//      Profitable?", 2023; idea original de Toby Crabel). Dirección de la primera vela de
//      5 min; stop al otro extremo de la vela; objetivo 10R; salida al cierre.
//      Desactivado por defecto: las réplicas independientes indican que su ventaja
//      desaparece con costes reales. Actívalo sólo si tu backtest con costes lo justifica.
//
//   3) REVERSIÓN A LA MEDIA RSI(2) (Larry Connors y Cesar Alvarez, "Short Term Trading
//      Strategies That Work", 2008). Compra al cierre si el precio está por encima de su
//      media de 200 días y el RSI de 2 periodos es < 10; vende cuando cierra por encima de
//      la media de 5 días. Mantiene posición varios días (swing).
//
//  Los tres módulos se pueden activar o desactivar por separado. Comparten la gestión de
//  riesgo: tamaño fijo o dinámico, máximo de contratos, pérdida diaria máxima, fechas
//  excluidas (FOMC, IPC, etc.) y bloqueo de señales opuestas (nunca se invierte la
//  posición de otro módulo).
//
//  REQUISITOS DE USO
//   - Gráfico de minutos (recomendado 5 min) de ES o MES, plantilla de horario
//     "CME US Index Futures ETH" y al menos 300 días cargados (la media de 200 días del
//     módulo RSI(2) necesita ese histórico).
//   - Las horas de los parámetros están en HORA DE NUEVA YORK, sea cual sea la zona horaria
//     configurada en NinjaTrader (la estrategia convierte la hora de cada barra).
//   - Calculate = On bar close.
//
//  AVISO: esto es software educativo, no asesoramiento financiero. Los futuros son
//  apalancados y pueden hacer perder más del capital depositado. Pruébalo primero en
//  Strategy Analyzer y después en una cuenta Sim (Playback / Sim101) durante semanas
//  antes de plantearte dinero real.
// =====================================================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
using SistemaCombinadoESComun;
#endregion

// Tipos auxiliares en un espacio de nombres propio (recomendación de NinjaTrader para
// enumeraciones definidas por el usuario).
namespace SistemaCombinadoESComun
{
    public enum ModoTamanoPosicion
    {
        ContratosFijos,
        Dinamico
    }

    /// <summary>Datos de una sesión regular (RTH, 9:30-16:00 Nueva York).</summary>
    public class DiaRth
    {
        public DateTime Fecha;
        public bool TieneApertura;
        public double Apertura;
        public double Maximo;
        public double Minimo;
        public double Cierre;
        /// <summary>minuto del día (NY) -> |cierre de la barra / apertura del día - 1|</summary>
        public Dictionary<int, double> Movimientos = new Dictionary<int, double>();
    }

    /// <summary>Cálculos puros (sin dependencias de NinjaTrader).</summary>
    public static class Calculos
    {
        public static int HhmmAMinutos(int hhmm)
        {
            return (hhmm / 100) * 60 + (hhmm % 100);
        }

        /// <summary>Media simple de los últimos n valores; NaN si no hay datos suficientes.</summary>
        public static double MediaUltimos(IList<double> v, int n)
        {
            if (v == null || n <= 0 || v.Count < n)
                return double.NaN;
            double s = 0;
            for (int i = v.Count - n; i < v.Count; i++)
                s += v[i];
            return s / n;
        }

        /// <summary>RSI con suavizado de Wilder, calculado sobre como mucho maxDatos valores.</summary>
        public static double RsiWilder(IList<double> c, int periodo, int maxDatos)
        {
            if (c == null || periodo < 1 || c.Count < periodo + 1)
                return double.NaN;
            int inicio = Math.Max(1, c.Count - Math.Max(maxDatos, periodo + 1));
            if (c.Count - inicio < periodo)
                inicio = c.Count - periodo;

            double ganancia = 0, perdida = 0;
            int i = inicio;
            for (int k = 0; k < periodo; k++, i++)
            {
                double d = c[i] - c[i - 1];
                if (d > 0) ganancia += d; else perdida -= d;
            }
            ganancia /= periodo;
            perdida /= periodo;
            for (; i < c.Count; i++)
            {
                double d = c[i] - c[i - 1];
                double sube = d > 0 ? d : 0;
                double baja = d < 0 ? -d : 0;
                ganancia = (ganancia * (periodo - 1) + sube) / periodo;
                perdida = (perdida * (periodo - 1) + baja) / periodo;
            }
            if (perdida <= 0)
                return ganancia <= 0 ? 50 : 100;
            return 100 - 100 / (1 + ganancia / perdida);
        }

        /// <summary>Desviación típica muestral de los últimos n rendimientos diarios.</summary>
        public static double DesvRetornos(IList<double> c, int n)
        {
            if (c == null || n < 2 || c.Count < n + 1)
                return double.NaN;
            double[] r = new double[n];
            double media = 0;
            for (int k = 0; k < n; k++)
            {
                int i = c.Count - n + k;
                r[k] = c[i] / c[i - 1] - 1;
                media += r[k];
            }
            media /= n;
            double s = 0;
            for (int k = 0; k < n; k++)
                s += (r[k] - media) * (r[k] - media);
            return Math.Sqrt(s / (n - 1));
        }

        /// <summary>ATR diario (rango verdadero medio) de las últimas n sesiones.</summary>
        public static double AtrDiario(IList<DiaRth> d, int n)
        {
            if (d == null || n < 1 || d.Count < n + 1)
                return double.NaN;
            double s = 0;
            for (int i = d.Count - n; i < d.Count; i++)
            {
                double cierrePrevio = d[i - 1].Cierre;
                s += Math.Max(d[i].Maximo, cierrePrevio) - Math.Min(d[i].Minimo, cierrePrevio);
            }
            return s / n;
        }

        /// <summary>
        /// Sigma del "noise area" para un minuto del día: media de |cierre/apertura - 1| a esa
        /// hora en las últimas 'dias' sesiones. NaN si hay menos de minMuestras observaciones.
        /// </summary>
        public static double SigmaRuido(IList<DiaRth> d, int minuto, int dias, int minMuestras)
        {
            if (d == null || dias < 1 || d.Count < dias)
                return double.NaN;
            double s = 0, v;
            int k = 0;
            for (int i = d.Count - dias; i < d.Count; i++)
            {
                if (d[i].Movimientos.TryGetValue(minuto, out v))
                {
                    s += v;
                    k++;
                }
            }
            if (k == 0 || k < minMuestras)
                return double.NaN;
            return s / k;
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public class SistemaCombinadoES : Strategy
    {
        // ---- Nombres de señal (uno por módulo y dirección) ----
        private const string MomL = "MOM_L";
        private const string MomS = "MOM_S";
        private const string OrbL = "ORB_L";
        private const string OrbS = "ORB_S";
        private const string SwL = "RSI2_L";
        private const string SwS = "RSI2_S";
        private static readonly string[] Senales = { MomL, MomS, OrbL, OrbS, SwL, SwS };
        private static readonly string[] SenalesIntradia = { MomL, MomS, OrbL, OrbS };

        private const int MaxDiasHistorial = 400;
        private const int BarrasCaducidadOrden = 3;
        private const int MargenFinSesionMin = 15;   // cierre intradía como tarde 15 min antes del fin de sesión

        // ---- Zona horaria y sesión ----
        private TimeZoneInfo tzPlataforma;
        private TimeZoneInfo tzNuevaYork;
        private SessionIterator sesiones;
        private DateTime finSesionPlataforma = DateTime.MinValue;
        private DateTime fechaFinSesionNy = DateTime.MinValue;
        private int minutoFinSesionNy;

        // ---- Horas en minutos desde medianoche (NY) ----
        private int iniRth, finRth, cierreIntradia, momPrimera, momUltima, swingDecision;

        // ---- Datos diarios ----
        private List<DiaRth> historial;
        private DiaRth hoy;
        private bool hoyFinalizado;
        private DateTime fechaActual = DateTime.MinValue;
        private int diasCompletados;
        private double vwapPV, vwapV;

        // ---- Estado de los módulos ----
        private double orApertura, orMaximo, orMinimo, orCierre;
        private bool orTieneDatos, orbDecididoHoy;
        private int momGiroPendiente;
        private bool swingDecididoHoy;
        private int swingDiaEntrada;

        // ---- Seguimiento de posiciones por señal ----
        private Dictionary<string, int> qty;
        private Dictionary<string, int> pendEntQty;
        private Dictionary<string, int> pendEntBarra;
        private Dictionary<string, int> pendSalBarra;
        private Dictionary<string, DateTime> fechaEntrada;
        private Dictionary<Order, string> ordenSenal;
        private string ultimaEntrada;

        // ---- Riesgo ----
        private double equityInicioDia;
        private bool equityInicioFijado;
        private bool bloqueadoHoy;
        private HashSet<DateTime> fechasExcluidas;
        private bool avisoDesfase;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Sistema combinado para futuros del S&P 500 (ES/MES): momentum intradía " +
                              "con bandas de ruido + VWAP, Opening Range Breakout de 5 min y reversión " +
                              "a la media RSI(2) de Connors.";
                Name = "SistemaCombinadoES";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.UniqueEntries;
                IsExitOnSessionCloseStrategy = false;   // el swing RSI(2) mantiene posiciones overnight
                ExitOnSessionCloseSeconds = 30;
                IsFillLimitOnTouch = false;
                MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;
                OrderFillResolution = OrderFillResolution.Standard;
                Slippage = 1;                           // 1 tick por orden en backtest (prudente)
                StartBehavior = StartBehavior.WaitUntilFlat;
                TimeInForce = TimeInForce.Gtc;
                TraceOrders = false;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade = 20;
                IsInstantiatedOnEachOptimizationIteration = true;
                IsOverlay = true;

                // 0. General
                ModoTamano = ModoTamanoPosicion.ContratosFijos;
                CapitalCuenta = 50000;
                Reinvertir = false;
                MaxContratos = 3;
                MaxPerdidaDiaria = 0;
                HoraInicioRth = 930;
                HoraFinRth = 1600;
                HoraCierreIntradia = 1555;
                FechasExcluidas = string.Empty;
                FiltroTendenciaIntradia = false;
                SmaTendencia = 200;
                AtrDias = 14;
                Depurar = false;

                // 1. Momentum intradía
                MomActivo = true;
                MomDias = 14;
                MomMultiplicador = 1.0;
                MomPrimeraHora = 1000;
                MomFrecuenciaMin = 30;
                MomUltimaEntrada = 1530;
                MomUsarVwap = true;
                MomContratos = 1;
                MomVolObjetivoPct = 2.0;
                MomApalancamientoMax = 4.0;
                MomStopEmergenciaAtr = 0.5;

                // 2. Opening Range Breakout
                OrbActivo = false;
                OrbMinutos = 5;
                OrbObjetivoR = 10;
                OrbContratos = 1;
                OrbRiesgoPct = 1.0;
                OrbApalancamientoMax = 4.0;

                // 3. Swing RSI(2)
                SwingActivo = true;
                SwingRsiPeriodo = 2;
                SwingRsiEntrada = 10;
                SwingSmaFiltro = 200;
                SwingSmaSalida = 5;
                SwingMaxDias = 10;
                SwingStopAtr = 3.0;
                SwingCortos = false;
                SwingHoraDecision = 1600;
                SwingContratos = 1;
                SwingRiesgoPct = 1.0;
                SwingApalancamientoMax = 1.0;

                AddPlot(Brushes.DodgerBlue, "BandaSuperior");
                AddPlot(Brushes.OrangeRed, "BandaInferior");
                AddPlot(Brushes.Gold, "VWAP");
            }
            else if (State == State.Configure)
            {
            }
            else if (State == State.DataLoaded)
            {
                historial = new List<DiaRth>();
                hoy = null;
                hoyFinalizado = false;
                fechaActual = DateTime.MinValue;
                diasCompletados = 0;

                qty = new Dictionary<string, int>();
                foreach (string s in Senales)
                    qty[s] = 0;
                pendEntQty = new Dictionary<string, int>();
                pendEntBarra = new Dictionary<string, int>();
                pendSalBarra = new Dictionary<string, int>();
                fechaEntrada = new Dictionary<string, DateTime>();
                ordenSenal = new Dictionary<Order, string>();
                ultimaEntrada = null;

                iniRth = Calculos.HhmmAMinutos(HoraInicioRth);
                finRth = Calculos.HhmmAMinutos(HoraFinRth);
                cierreIntradia = Math.Min(Calculos.HhmmAMinutos(HoraCierreIntradia), finRth);
                momPrimera = Calculos.HhmmAMinutos(MomPrimeraHora);
                momUltima = Math.Min(Calculos.HhmmAMinutos(MomUltimaEntrada), cierreIntradia);
                swingDecision = Math.Min(Calculos.HhmmAMinutos(SwingHoraDecision), finRth);

                tzPlataforma = Core.Globals.GeneralOptions.TimeZoneInfo;
                if (tzPlataforma == null)
                    tzPlataforma = TimeZoneInfo.Local;
                tzNuevaYork = BuscarZonaNuevaYork();
                sesiones = new SessionIterator(Bars);
                finSesionPlataforma = DateTime.MinValue;

                fechasExcluidas = LeerFechas(FechasExcluidas);

                if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute)
                    Print(Name + " AVISO: usa un gráfico de minutos (recomendado 5 min). Tipo actual: " + BarsPeriod.BarsPeriodType);
                else
                {
                    if (MomFrecuenciaMin % BarsPeriod.Value != 0 || 30 % BarsPeriod.Value != 0)
                        Print(Name + " AVISO: el periodo de barra (" + BarsPeriod.Value + " min) debería dividir 30 y la frecuencia del momentum.");
                    if (OrbActivo && OrbMinutos % BarsPeriod.Value != 0)
                        Print(Name + " AVISO: OrbMinutos (" + OrbMinutos + ") debe ser múltiplo del periodo de barra (" + BarsPeriod.Value + ").");
                }
                if (Calculate != Calculate.OnBarClose)
                    Print(Name + " AVISO: la estrategia está diseñada para Calculate = On bar close.");
            }
        }

        // =============================================================================
        //  BUCLE PRINCIPAL
        // =============================================================================
        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;
            ActualizarSesion();
            if (CurrentBar < 1)
                return;

            DateTime ny = ANuevaYork(Time[0]);
            int t = ny.Hour * 60 + ny.Minute;
            DateTime fecha = ny.Date;

            CaducarOrdenesPendientes();
            Reconciliar();

            if (fecha != fechaActual)
            {
                if (hoy != null && hoy.TieneApertura && !hoyFinalizado)
                    FinalizarDia();
                NuevoDia(fecha);
            }

            bool enRth = t > iniRth && t <= finRth;
            if (enRth && !hoyFinalizado)
                ActualizarDia(t);

            ControlPerdidaDiaria();
            CierreIntradia(t, enRth);

            if (enRth && !hoyFinalizado)
            {
                ModuloOrb(t);
                ModuloMomentum(t);
                Values[2][0] = Vwap();
            }

            ModuloSwing(t);

            if (hoy != null && hoy.TieneApertura && !hoyFinalizado && t >= finRth)
                FinalizarDia();
        }

        // =============================================================================
        //  DATOS DIARIOS
        // =============================================================================
        private void NuevoDia(DateTime fecha)
        {
            fechaActual = fecha;
            hoy = new DiaRth();
            hoy.Fecha = fecha;
            hoyFinalizado = false;
            vwapPV = 0;
            vwapV = 0;
            orTieneDatos = false;
            orbDecididoHoy = false;
            swingDecididoHoy = false;
            momGiroPendiente = 0;
            bloqueadoHoy = false;
            equityInicioFijado = false;
        }

        private void ActualizarDia(int t)
        {
            if (!hoy.TieneApertura)
            {
                hoy.TieneApertura = true;
                hoy.Apertura = Open[0];
                hoy.Maximo = High[0];
                hoy.Minimo = Low[0];
                equityInicioDia = EquityActual();
                equityInicioFijado = true;
            }
            else
            {
                hoy.Maximo = Math.Max(hoy.Maximo, High[0]);
                hoy.Minimo = Math.Min(hoy.Minimo, Low[0]);
            }
            hoy.Cierre = Close[0];
            if (hoy.Apertura > 0)
                hoy.Movimientos[t] = Math.Abs(Close[0] / hoy.Apertura - 1);

            double volumen = Volume[0];
            if (volumen <= 0)
                volumen = 1;
            vwapPV += (High[0] + Low[0] + Close[0]) / 3.0 * volumen;
            vwapV += volumen;
        }

        private void FinalizarDia()
        {
            hoyFinalizado = true;
            if (hoy == null || !hoy.TieneApertura)
                return;
            historial.Add(hoy);
            diasCompletados++;
            if (historial.Count > MaxDiasHistorial)
                historial.RemoveAt(0);
        }

        /// <summary>
        /// Lee el fin real de la sesión de la plantilla de horario (incluye los días de cierre
        /// anticipado por festivo, p. ej. Black Friday o la víspera del 4 de julio).
        /// </summary>
        private void ActualizarSesion()
        {
            if (Bars.IsFirstBarOfSession || finSesionPlataforma == DateTime.MinValue || Time[0] > finSesionPlataforma)
            {
                sesiones.GetNextSession(Time[0], true);
                finSesionPlataforma = sesiones.ActualSessionEnd;
                DateTime finNy = ANuevaYork(finSesionPlataforma);
                fechaFinSesionNy = finNy.Date;
                minutoFinSesionNy = finNy.Hour * 60 + finNy.Minute;
            }
        }

        /// <summary>Minuto NY a partir del cual se cierran y no se abren posiciones intradía hoy.</summary>
        private int LimiteIntradia()
        {
            int limite = cierreIntradia;
            if (fechaFinSesionNy == fechaActual)
                limite = Math.Min(limite, minutoFinSesionNy - MargenFinSesionMin);
            return limite;
        }

        private double Vwap()
        {
            return vwapV > 0 ? vwapPV / vwapV : Close[0];
        }

        private double CierrePrevio()
        {
            return historial.Count > 0 ? historial[historial.Count - 1].Cierre : double.NaN;
        }

        private List<double> CierresHistorial()
        {
            List<double> c = new List<double>(historial.Count + 1);
            for (int i = 0; i < historial.Count; i++)
                c.Add(historial[i].Cierre);
            return c;
        }

        // =============================================================================
        //  MÓDULO 1: MOMENTUM INTRADÍA (NOISE AREA + VWAP)
        // =============================================================================
        private void ModuloMomentum(int t)
        {
            if (!MomActivo || historial.Count < MomDias)
                return;

            double sigma = Calculos.SigmaRuido(historial, t, MomDias, Math.Max(3, MomDias / 2));
            double cierrePrevio = CierrePrevio();
            if (double.IsNaN(sigma) || double.IsNaN(cierrePrevio))
                return;

            double bandaSup = Math.Max(hoy.Apertura, cierrePrevio) * (1 + MomMultiplicador * sigma);
            double bandaInf = Math.Min(hoy.Apertura, cierrePrevio) * (1 - MomMultiplicador * sigma);
            Values[0][0] = bandaSup;
            Values[1][0] = bandaInf;

            int pos = PosicionModulo(MomL, MomS);
            bool esRevision = t >= momPrimera && (t - iniRth) % MomFrecuenciaMin == 0;
            int horaMaxEntrada = Math.Min(momUltima, LimiteIntradia() - 1);

            // Giro pendiente: la revisión anterior cerró la posición y pidió la contraria.
            if (momGiroPendiente != 0 && !esRevision)
            {
                if (pos == 0 && t <= horaMaxEntrada)
                    EntrarMomentum(momGiroPendiente, bandaSup, bandaInf, "giro");
                momGiroPendiente = 0;
            }
            if (!esRevision)
                return;
            momGiroPendiente = 0;

            double c = Close[0];
            double vwap = Vwap();
            if (pos > 0)
            {
                double stop = MomUsarVwap ? Math.Max(bandaSup, vwap) : bandaSup;
                if (c < stop)
                {
                    Salir(MomL, "stop momentum (" + Fmt(stop) + ")");
                    if (c < bandaInf && t <= horaMaxEntrada)
                        momGiroPendiente = -1;
                }
            }
            else if (pos < 0)
            {
                double stop = MomUsarVwap ? Math.Min(bandaInf, vwap) : bandaInf;
                if (c > stop)
                {
                    Salir(MomS, "stop momentum (" + Fmt(stop) + ")");
                    if (c > bandaSup && t <= horaMaxEntrada)
                        momGiroPendiente = 1;
                }
            }
            else if (t <= horaMaxEntrada && !HayPendiente(MomL) && !HayPendiente(MomS))
            {
                if (c > bandaSup)
                    EntrarMomentum(1, bandaSup, bandaInf, "rotura banda superior " + Fmt(bandaSup));
                else if (c < bandaInf)
                    EntrarMomentum(-1, bandaSup, bandaInf, "rotura banda inferior " + Fmt(bandaInf));
            }
        }

        private void EntrarMomentum(int dir, double bandaSup, double bandaInf, string motivo)
        {
            if (FiltroTendenciaIntradia && !TendenciaPermite(dir))
                return;
            if (!PuedeAbrir(dir))
                return;

            int cantidad;
            if (ModoTamano == ModoTamanoPosicion.Dinamico)
            {
                double sigmaDiaria = Calculos.DesvRetornos(CierresHistorial(), 14);
                if (double.IsNaN(sigmaDiaria) || sigmaDiaria <= 0)
                    return;
                double apalancamiento = Math.Min(MomApalancamientoMax, (MomVolObjetivoPct / 100.0) / sigmaDiaria);
                cantidad = (int)Math.Floor(Capital() * apalancamiento / Nocional());
            }
            else
                cantidad = MomContratos;

            double stop = double.NaN;
            if (MomStopEmergenciaAtr > 0)
            {
                double atr = Calculos.AtrDiario(historial, AtrDias);
                if (double.IsNaN(atr))
                    return;   // sin ATR no hay stop de emergencia: no se opera
                stop = Close[0] - dir * MomStopEmergenciaAtr * atr;
            }
            Entrar(dir, cantidad, dir > 0 ? MomL : MomS, stop, double.NaN, motivo);
        }

        // =============================================================================
        //  MÓDULO 2: OPENING RANGE BREAKOUT
        // =============================================================================
        private void ModuloOrb(int t)
        {
            if (!OrbActivo)
                return;
            int finOr = iniRth + OrbMinutos;

            if (t <= finOr)
            {
                if (!orTieneDatos)
                {
                    orTieneDatos = true;
                    orApertura = Open[0];
                    orMaximo = High[0];
                    orMinimo = Low[0];
                }
                else
                {
                    orMaximo = Math.Max(orMaximo, High[0]);
                    orMinimo = Math.Min(orMinimo, Low[0]);
                }
                orCierre = Close[0];
                if (t < finOr)
                    return;
            }

            if (orbDecididoHoy)
                return;
            orbDecididoHoy = true;
            if (t != finOr || !orTieneDatos || t >= LimiteIntradia())
                return;   // falta la barra que completa el rango: no se opera hoy

            int dir = orCierre > orApertura ? 1 : (orCierre < orApertura ? -1 : 0);
            if (dir == 0)
                return;   // vela doji: sin operación
            if (FiltroTendenciaIntradia && !TendenciaPermite(dir))
                return;
            if (!PuedeAbrir(dir))
                return;

            double stop = dir > 0 ? orMinimo : orMaximo;
            double riesgo = Math.Max(Math.Abs(Close[0] - stop), TickSize);

            int cantidad;
            if (ModoTamano == ModoTamanoPosicion.Dinamico)
            {
                int porRiesgo = (int)Math.Floor(Capital() * OrbRiesgoPct / 100.0 / (riesgo * ValorPunto()));
                int porApalancamiento = (int)Math.Floor(Capital() * OrbApalancamientoMax / Nocional());
                cantidad = Math.Min(porRiesgo, porApalancamiento);
            }
            else
                cantidad = OrbContratos;

            double objetivoTicks = OrbObjetivoR > 0 ? Math.Max(1, Math.Round(OrbObjetivoR * riesgo / TickSize)) : double.NaN;
            Entrar(dir, cantidad, dir > 0 ? OrbL : OrbS, stop, objetivoTicks,
                   "ORB " + OrbMinutos + " min, rango " + Fmt(orMinimo) + "-" + Fmt(orMaximo));
        }

        // =============================================================================
        //  MÓDULO 3: SWING RSI(2) DE CONNORS
        // =============================================================================
        private void ModuloSwing(int t)
        {
            int horaDecision = swingDecision;
            if (fechaFinSesionNy == fechaActual)
                horaDecision = Math.Min(horaDecision, minutoFinSesionNy - MargenFinSesionMin);
            if (!SwingActivo || swingDecididoHoy || hoy == null || !hoy.TieneApertura || hoyFinalizado || t < horaDecision)
                return;
            swingDecididoHoy = true;

            List<double> cierres = CierresHistorial();
            cierres.Add(hoy.Cierre);   // el cierre de hoy (precio en la hora de decisión)
            if (cierres.Count < Math.Max(SwingSmaFiltro, SwingSmaSalida) + 1)
                return;

            double c = hoy.Cierre;
            double smaFiltro = Calculos.MediaUltimos(cierres, SwingSmaFiltro);
            double smaSalida = Calculos.MediaUltimos(cierres, SwingSmaSalida);
            double rsi = Calculos.RsiWilder(cierres, SwingRsiPeriodo, 250);
            if (double.IsNaN(rsi) || double.IsNaN(smaFiltro) || double.IsNaN(smaSalida))
                return;

            int pos = PosicionModulo(SwL, SwS);
            int diasEnPosicion = diasCompletados - swingDiaEntrada;
            bool tiempoAgotado = SwingMaxDias > 0 && diasEnPosicion >= SwingMaxDias;

            if (pos > 0)
            {
                if (c > smaSalida || tiempoAgotado)
                    Salir(SwL, c > smaSalida ? "cierre > SMA" + SwingSmaSalida : "máximo de días");
                return;
            }
            if (pos < 0)
            {
                if (c < smaSalida || tiempoAgotado)
                    Salir(SwS, c < smaSalida ? "cierre < SMA" + SwingSmaSalida : "máximo de días");
                return;
            }
            if (HayPendiente(SwL) || HayPendiente(SwS))
                return;

            int dir = 0;
            if (c > smaFiltro && rsi < SwingRsiEntrada)
                dir = 1;
            else if (SwingCortos && c < smaFiltro && rsi > 100 - SwingRsiEntrada)
                dir = -1;
            if (dir == 0 || !PuedeAbrir(dir))
                return;

            double atr = Calculos.AtrDiario(historial, AtrDias);
            if ((SwingStopAtr > 0 || ModoTamano == ModoTamanoPosicion.Dinamico) && (double.IsNaN(atr) || atr <= 0))
                return;
            int cantidad;
            if (ModoTamano == ModoTamanoPosicion.Dinamico)
            {
                double distanciaRiesgo = (SwingStopAtr > 0 ? SwingStopAtr : 2.0) * atr;
                int porRiesgo = (int)Math.Floor(Capital() * SwingRiesgoPct / 100.0 / (distanciaRiesgo * ValorPunto()));
                int porApalancamiento = (int)Math.Floor(Capital() * SwingApalancamientoMax / Nocional());
                cantidad = Math.Min(porRiesgo, porApalancamiento);
            }
            else
                cantidad = SwingContratos;

            double stop = SwingStopAtr > 0 ? c - dir * SwingStopAtr * atr : double.NaN;
            Entrar(dir, cantidad, dir > 0 ? SwL : SwS, stop, double.NaN, "RSI(" + SwingRsiPeriodo + ")=" + rsi.ToString("0.0", CultureInfo.InvariantCulture) +
                                         ", SMA" + SwingSmaFiltro + "=" + Fmt(smaFiltro));
        }

        // =============================================================================
        //  RIESGO Y EJECUCIÓN
        // =============================================================================
        private void CierreIntradia(int t, bool enRth)
        {
            foreach (string s in SenalesIntradia)
            {
                if (qty[s] <= 0)
                    continue;
                DateTime f;
                bool otroDia = fechaEntrada.TryGetValue(s, out f) && f != fechaActual;
                if (t >= LimiteIntradia() || !enRth || otroDia)
                    Salir(s, "cierre intradía");
            }
        }

        private void ControlPerdidaDiaria()
        {
            if (MaxPerdidaDiaria <= 0 || !equityInicioFijado || bloqueadoHoy)
                return;
            double resultadoDia = EquityActual() - equityInicioDia;
            if (resultadoDia <= -MaxPerdidaDiaria)
            {
                bloqueadoHoy = true;
                Print(Name + " " + Time[0] + " Límite de pérdida diaria alcanzado (" + Fmt(resultadoDia) + " USD): se cierra todo y no se opera más hoy.");
                foreach (string s in Senales)
                    if (qty[s] > 0)
                        Salir(s, "límite de pérdida diaria");
            }
        }

        private bool PuedeAbrir(int dir)
        {
            if (bloqueadoHoy)
                return false;
            if (fechasExcluidas.Contains(fechaActual))
            {
                Traza("Fecha excluida: no se abren posiciones.");
                return false;
            }
            // Nunca se abre en sentido contrario a otra posición (evita invertir la de otro módulo).
            if (ContratosLado(-dir) > 0)
            {
                Traza("Señal " + (dir > 0 ? "larga" : "corta") + " bloqueada: hay una posición contraria abierta.");
                return false;
            }
            MarketPosition contraria = dir > 0 ? MarketPosition.Short : MarketPosition.Long;
            if (Position.MarketPosition == contraria)
                return false;
            return true;
        }

        /// <summary>
        /// Envía la entrada a mercado. stopPrecio (NaN = sin stop) y objetivoTicks (NaN = sin objetivo)
        /// se registran con SetStopLoss/SetProfitTarget sólo si la orden se llega a enviar.
        /// </summary>
        private void Entrar(int dir, int cantidad, string senal, double stopPrecio, double objetivoTicks, string motivo)
        {
            int libres = MaxContratos - ContratosLado(1) - ContratosLado(-1);
            cantidad = Math.Min(cantidad, libres);
            if (cantidad < 1)
            {
                Traza(senal + " descartada: tamaño 0 (capital insuficiente o máximo de contratos alcanzado).");
                return;
            }
            if (!double.IsNaN(stopPrecio))
            {
                stopPrecio = Redondear(stopPrecio);
                bool ladoCorrecto = dir > 0 ? stopPrecio < Close[0] : stopPrecio > Close[0];
                if (!ladoCorrecto)
                {
                    Traza(senal + " descartada: el stop (" + Fmt(stopPrecio) + ") queda al otro lado del precio.");
                    return;
                }
                SetStopLoss(senal, CalculationMode.Price, stopPrecio, false);
            }
            if (!double.IsNaN(objetivoTicks))
                SetProfitTarget(senal, CalculationMode.Ticks, objetivoTicks);
            Traza("ENTRADA " + senal + " x" + cantidad + " @" + Fmt(Close[0]) + " - " + motivo);
            ultimaEntrada = senal;
            pendEntQty[senal] = cantidad;
            pendEntBarra[senal] = CurrentBar;
            fechaEntrada[senal] = fechaActual;
            if (senal == SwL || senal == SwS)
                swingDiaEntrada = diasCompletados;
            if (dir > 0)
                EnterLong(cantidad, senal);
            else
                EnterShort(cantidad, senal);
        }

        private void Salir(string senal, string motivo)
        {
            if (qty[senal] <= 0 || pendSalBarra.ContainsKey(senal))
                return;
            Traza("SALIDA " + senal + " @" + Fmt(Close[0]) + " - " + motivo);
            pendSalBarra[senal] = CurrentBar;
            if (EsLarga(senal))
                ExitLong(senal + "_X", senal);
            else
                ExitShort(senal + "_X", senal);
        }

        private bool TendenciaPermite(int dir)
        {
            double sma = Calculos.MediaUltimos(CierresHistorial(), SmaTendencia);
            double cierrePrevio = CierrePrevio();
            if (double.IsNaN(sma) || double.IsNaN(cierrePrevio))
                return false;
            return dir > 0 ? cierrePrevio > sma : cierrePrevio < sma;
        }

        // =============================================================================
        //  SEGUIMIENTO DE ÓRDENES Y EJECUCIONES
        // =============================================================================
        protected override void OnOrderUpdate(Order order, double limitPrice, double stopPrice, int quantity, int filled,
                                              double averageFillPrice, OrderState orderState, DateTime time, ErrorCode error, string comment)
        {
            if (order == null || qty == null)
                return;

            // Los stops y objetivos que crea NinjaTrader con SetStopLoss/SetProfitTarget se asocian a su señal.
            if ((order.Name == "Stop loss" || order.Name == "Profit target") && !ordenSenal.ContainsKey(order))
            {
                string s = EsSenal(order.FromEntrySignal) ? order.FromEntrySignal : ultimaEntrada;
                if (s != null)
                    ordenSenal[order] = s;
            }

            if (orderState == OrderState.Cancelled || orderState == OrderState.Rejected)
            {
                if (EsSenal(order.Name) && EsEntrada(order.OrderAction))
                {
                    pendEntQty.Remove(order.Name);
                    pendEntBarra.Remove(order.Name);
                }
                else if (order.Name != null && order.Name.EndsWith("_X"))
                    pendSalBarra.Remove(order.Name.Substring(0, order.Name.Length - 2));
                ordenSenal.Remove(order);
                if (orderState == OrderState.Rejected)
                    Print(Name + " ORDEN RECHAZADA: " + order.Name + " " + comment);
            }
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity,
                                                  MarketPosition marketPosition, string orderId, DateTime time)
        {
            if (execution == null || execution.Order == null || qty == null)
                return;
            Order o = execution.Order;

            if (EsEntrada(o.OrderAction))
            {
                if (!EsSenal(o.Name))
                    return;
                qty[o.Name] += quantity;
                if (o.OrderState == OrderState.Filled || !pendEntQty.ContainsKey(o.Name) || qty[o.Name] >= pendEntQty[o.Name])
                {
                    pendEntQty.Remove(o.Name);
                    pendEntBarra.Remove(o.Name);
                }
                return;
            }

            // Salida: identificar a qué señal pertenece.
            bool cierraLargos = o.OrderAction == OrderAction.Sell;
            string senal = null;
            if (EsSenal(o.FromEntrySignal))
                senal = o.FromEntrySignal;
            else
            {
                string s;
                if (ordenSenal.TryGetValue(o, out s))
                    senal = s;
            }
            if (senal == null || EsLarga(senal) != cierraLargos || qty[senal] <= 0)
                senal = SenalAbiertaDelLado(cierraLargos ? 1 : -1);
            if (senal == null)
                return;

            qty[senal] = Math.Max(0, qty[senal] - quantity);
            if (qty[senal] == 0)
                pendSalBarra.Remove(senal);
            if (o.OrderState == OrderState.Filled)
                ordenSenal.Remove(o);
        }

        private void CaducarOrdenesPendientes()
        {
            foreach (string s in Senales)
            {
                int barra;
                if (pendEntBarra.TryGetValue(s, out barra) && CurrentBar - barra > BarrasCaducidadOrden)
                {
                    pendEntBarra.Remove(s);
                    pendEntQty.Remove(s);
                }
                if (pendSalBarra.TryGetValue(s, out barra) && CurrentBar - barra > BarrasCaducidadOrden)
                    pendSalBarra.Remove(s);
            }
        }

        /// <summary>Si la posición real es plana y el seguimiento interno no, se corrige.</summary>
        private void Reconciliar()
        {
            if (pendEntQty.Count > 0 || pendSalBarra.Count > 0)
                return;
            int neto = ContratosAbiertos(1) - ContratosAbiertos(-1);
            int real = Position.MarketPosition == MarketPosition.Long ? Position.Quantity
                     : (Position.MarketPosition == MarketPosition.Short ? -Position.Quantity : 0);
            if (neto == real)
            {
                avisoDesfase = false;
                return;
            }
            if (!avisoDesfase)
            {
                avisoDesfase = true;
                Print(Name + " AVISO " + Time[0] + ": seguimiento interno (" + neto + ") distinto de la posición (" + real + ").");
            }
            if (real == 0)
            {
                foreach (string s in Senales)
                    qty[s] = 0;
                avisoDesfase = false;
            }
        }

        // =============================================================================
        //  UTILIDADES
        // =============================================================================
        private static bool EsSenal(string s)
        {
            return s != null && Array.IndexOf(Senales, s) >= 0;
        }

        private static bool EsLarga(string s)
        {
            return s.EndsWith("_L");
        }

        private static bool EsEntrada(OrderAction a)
        {
            return a == OrderAction.Buy || a == OrderAction.SellShort;
        }

        private int PosicionModulo(string larga, string corta)
        {
            return qty[larga] - qty[corta];
        }

        private bool HayPendiente(string senal)
        {
            return pendEntQty.ContainsKey(senal);
        }

        /// <summary>Contratos abiertos en un lado (+1 largos, -1 cortos).</summary>
        private int ContratosAbiertos(int lado)
        {
            int n = 0;
            foreach (string s in Senales)
                if (EsLarga(s) == (lado > 0))
                    n += qty[s];
            return n;
        }

        /// <summary>Contratos abiertos más los pendientes de ejecutar en un lado.</summary>
        private int ContratosLado(int lado)
        {
            int n = ContratosAbiertos(lado);
            foreach (KeyValuePair<string, int> p in pendEntQty)
                if (EsLarga(p.Key) == (lado > 0))
                    n += p.Value;
            return n;
        }

        private string SenalAbiertaDelLado(int lado)
        {
            foreach (string s in Senales)
                if (EsLarga(s) == (lado > 0) && qty[s] > 0)
                    return s;
            return null;
        }

        private double EquityActual()
        {
            return SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit
                 + Position.GetUnrealizedProfitLoss(PerformanceUnit.Currency, Close[0]);
        }

        private double Capital()
        {
            double c = CapitalCuenta;
            if (Reinvertir)
                c += SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit;
            return Math.Max(0, c);
        }

        private double ValorPunto()
        {
            return Instrument.MasterInstrument.PointValue;
        }

        private double Nocional()
        {
            return Math.Max(1e-9, Close[0] * ValorPunto());
        }

        private double Redondear(double precio)
        {
            return Instrument.MasterInstrument.RoundToTickSize(precio);
        }

        /// <summary>Hora de la barra (zona de NinjaTrader) convertida a hora de Nueva York.</summary>
        private DateTime ANuevaYork(DateTime t)
        {
            DateTime local = DateTime.SpecifyKind(t, DateTimeKind.Unspecified);
            DateTime utc = DateTime.SpecifyKind(local - tzPlataforma.GetUtcOffset(local), DateTimeKind.Utc);
            return TimeZoneInfo.ConvertTimeFromUtc(utc, tzNuevaYork);
        }

        private static TimeZoneInfo BuscarZonaNuevaYork()
        {
            string[] ids = { "Eastern Standard Time", "America/New_York" };
            foreach (string id in ids)
            {
                try { return TimeZoneInfo.FindSystemTimeZoneById(id); }
                catch (TimeZoneNotFoundException) { }
                catch (InvalidTimeZoneException) { }
            }
            throw new InvalidOperationException("No se encuentra la zona horaria de Nueva York en este equipo.");
        }

        private static HashSet<DateTime> LeerFechas(string texto)
        {
            HashSet<DateTime> r = new HashSet<DateTime>();
            if (string.IsNullOrEmpty(texto))
                return r;
            foreach (string parte in texto.Split(new[] { ';', ',', ' ', '\n', '\r', '\t' }, StringSplitOptions.RemoveEmptyEntries))
            {
                DateTime f;
                if (DateTime.TryParseExact(parte.Trim(), "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out f))
                    r.Add(f.Date);
            }
            return r;
        }

        private static string Fmt(double v)
        {
            return v.ToString("0.00", CultureInfo.InvariantCulture);
        }

        private void Traza(string texto)
        {
            if (Depurar)
                Print(Name + " " + Time[0].ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture) + " " + texto);
        }

        // =============================================================================
        //  PARÁMETROS
        // =============================================================================
        #region Parámetros

        // ---------- 0. General ----------
        [NinjaScriptProperty]
        [Display(Name = "Modo de tamaño", Description = "ContratosFijos: usa los contratos de cada módulo. Dinamico: objetivo de volatilidad (momentum) y % de riesgo (ORB, RSI2).", Order = 1, GroupName = "0. General")]
        public ModoTamanoPosicion ModoTamano { get; set; }

        [NinjaScriptProperty]
        [Range(1000, double.MaxValue)]
        [Display(Name = "Capital de la cuenta (USD)", Description = "Capital usado para el tamaño dinámico.", Order = 2, GroupName = "0. General")]
        public double CapitalCuenta { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Reinvertir beneficios", Description = "Suma al capital el resultado cerrado de la estrategia.", Order = 3, GroupName = "0. General")]
        public bool Reinvertir { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Máximo de contratos", Description = "Límite total de contratos abiertos entre todos los módulos.", Order = 4, GroupName = "0. General")]
        public int MaxContratos { get; set; }

        [NinjaScriptProperty]
        [Range(0, double.MaxValue)]
        [Display(Name = "Pérdida diaria máxima (USD)", Description = "Al alcanzarla se cierra todo y no se opera hasta el día siguiente. 0 = desactivado.", Order = 5, GroupName = "0. General")]
        public double MaxPerdidaDiaria { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "Inicio sesión regular (HHMM NY)", Order = 6, GroupName = "0. General")]
        public int HoraInicioRth { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "Fin sesión regular (HHMM NY)", Order = 7, GroupName = "0. General")]
        public int HoraFinRth { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "Cierre posiciones intradía (HHMM NY)", Description = "Hora a la que se cierran momentum y ORB.", Order = 8, GroupName = "0. General")]
        public int HoraCierreIntradia { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Fechas excluidas (yyyy-MM-dd;...)", Description = "Días sin nuevas entradas, p. ej. FOMC o IPC: 2026-12-09;2027-01-27", Order = 9, GroupName = "0. General")]
        public string FechasExcluidas { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Filtro de tendencia intradía", Description = "Momentum y ORB sólo largos sobre la SMA diaria y sólo cortos por debajo.", Order = 10, GroupName = "0. General")]
        public bool FiltroTendenciaIntradia { get; set; }

        [NinjaScriptProperty]
        [Range(2, 400)]
        [Display(Name = "SMA de tendencia (días)", Order = 11, GroupName = "0. General")]
        public int SmaTendencia { get; set; }

        [NinjaScriptProperty]
        [Range(2, 100)]
        [Display(Name = "ATR diario (días)", Description = "Periodo del ATR diario usado en los stops de emergencia y el tamaño.", Order = 12, GroupName = "0. General")]
        public int AtrDias { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Depurar (Output window)", Description = "Escribe cada decisión en la ventana Output.", Order = 13, GroupName = "0. General")]
        public bool Depurar { get; set; }

        // ---------- 1. Momentum intradía ----------
        [NinjaScriptProperty]
        [Display(Name = "Activar momentum intradía", Order = 1, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public bool MomActivo { get; set; }

        [NinjaScriptProperty]
        [Range(3, 100)]
        [Display(Name = "Días para la banda de ruido", Description = "Paper: 14.", Order = 2, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public int MomDias { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10)]
        [Display(Name = "Multiplicador de la banda", Description = "Paper: 1.", Order = 3, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public double MomMultiplicador { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "Primera revisión (HHMM NY)", Order = 4, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public int MomPrimeraHora { get; set; }

        [NinjaScriptProperty]
        [Range(1, 390)]
        [Display(Name = "Frecuencia de revisión (min)", Description = "Paper: 30 (HH:00 y HH:30).", Order = 5, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public int MomFrecuenciaMin { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "Última entrada (HHMM NY)", Order = 6, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public int MomUltimaEntrada { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Stop con VWAP", Description = "Stop = max(banda, VWAP) en largos y min(banda, VWAP) en cortos. Si no, sólo la banda.", Order = 7, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public bool MomUsarVwap { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Contratos (modo fijo)", Order = 8, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public int MomContratos { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20)]
        [Display(Name = "Volatilidad diaria objetivo (%)", Description = "Modo dinámico. Paper: 2%.", Order = 9, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public double MomVolObjetivoPct { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20)]
        [Display(Name = "Apalancamiento máximo", Description = "Modo dinámico. Paper: 4.", Order = 10, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public double MomApalancamientoMax { get; set; }

        [NinjaScriptProperty]
        [Range(0, 10)]
        [Display(Name = "Stop de emergencia (x ATR diario)", Description = "Stop real en el mercado por si se cae la conexión. 0 = sin stop de emergencia.", Order = 11, GroupName = "1. Momentum (Noise Area + VWAP)")]
        public double MomStopEmergenciaAtr { get; set; }

        // ---------- 2. Opening Range Breakout ----------
        [NinjaScriptProperty]
        [Display(Name = "Activar ORB", Description = "Desactivado por defecto: su ventaja neta de costes es dudosa.", Order = 1, GroupName = "2. Opening Range Breakout")]
        public bool OrbActivo { get; set; }

        [NinjaScriptProperty]
        [Range(1, 120)]
        [Display(Name = "Minutos del rango de apertura", Description = "Paper: 5.", Order = 2, GroupName = "2. Opening Range Breakout")]
        public int OrbMinutos { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Objetivo (múltiplos de R)", Description = "Paper: 10. 0 = sin objetivo (sale al cierre).", Order = 3, GroupName = "2. Opening Range Breakout")]
        public double OrbObjetivoR { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Contratos (modo fijo)", Order = 4, GroupName = "2. Opening Range Breakout")]
        public int OrbContratos { get; set; }

        [NinjaScriptProperty]
        [Range(0.05, 10)]
        [Display(Name = "Riesgo por operación (%)", Description = "Modo dinámico. Paper: 1%.", Order = 5, GroupName = "2. Opening Range Breakout")]
        public double OrbRiesgoPct { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20)]
        [Display(Name = "Apalancamiento máximo", Description = "Modo dinámico. Paper: 4.", Order = 6, GroupName = "2. Opening Range Breakout")]
        public double OrbApalancamientoMax { get; set; }

        // ---------- 3. Swing RSI(2) ----------
        [NinjaScriptProperty]
        [Display(Name = "Activar swing RSI(2)", Order = 1, GroupName = "3. Swing RSI(2) Connors")]
        public bool SwingActivo { get; set; }

        [NinjaScriptProperty]
        [Range(2, 50)]
        [Display(Name = "Periodo RSI", Order = 2, GroupName = "3. Swing RSI(2) Connors")]
        public int SwingRsiPeriodo { get; set; }

        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name = "Umbral de entrada RSI", Description = "Compra si RSI < umbral (Connors: 5 o 10). Cortos si RSI > 100 - umbral.", Order = 3, GroupName = "3. Swing RSI(2) Connors")]
        public double SwingRsiEntrada { get; set; }

        [NinjaScriptProperty]
        [Range(10, 400)]
        [Display(Name = "SMA filtro de tendencia (días)", Description = "Connors: 200.", Order = 4, GroupName = "3. Swing RSI(2) Connors")]
        public int SwingSmaFiltro { get; set; }

        [NinjaScriptProperty]
        [Range(2, 50)]
        [Display(Name = "SMA de salida (días)", Description = "Connors: 5.", Order = 5, GroupName = "3. Swing RSI(2) Connors")]
        public int SwingSmaSalida { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Máximo de días en posición", Description = "0 = sin límite.", Order = 6, GroupName = "3. Swing RSI(2) Connors")]
        public int SwingMaxDias { get; set; }

        [NinjaScriptProperty]
        [Range(0, 20)]
        [Display(Name = "Stop de emergencia (x ATR diario)", Description = "Stop de catástrofe. 0 = sin stop (como el sistema original).", Order = 7, GroupName = "3. Swing RSI(2) Connors")]
        public double SwingStopAtr { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Permitir cortos", Description = "Variante corta (bajo la SMA y RSI alto). Históricamente débil en el S&P 500.", Order = 8, GroupName = "3. Swing RSI(2) Connors")]
        public bool SwingCortos { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "Hora de decisión (HHMM NY)", Description = "16:00 = al cierre (requiere plantilla ETH). Con plantilla RTH usa 15:55.", Order = 9, GroupName = "3. Swing RSI(2) Connors")]
        public int SwingHoraDecision { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Contratos (modo fijo)", Order = 10, GroupName = "3. Swing RSI(2) Connors")]
        public int SwingContratos { get; set; }

        [NinjaScriptProperty]
        [Range(0.05, 10)]
        [Display(Name = "Riesgo por operación (%)", Description = "Modo dinámico: riesgo medido hasta el stop de emergencia.", Order = 11, GroupName = "3. Swing RSI(2) Connors")]
        public double SwingRiesgoPct { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20)]
        [Display(Name = "Apalancamiento máximo", Description = "Modo dinámico.", Order = 12, GroupName = "3. Swing RSI(2) Connors")]
        public double SwingApalancamientoMax { get; set; }

        #endregion
    }
}
```

---

*Fin del documento. El código de la sección 8 es idéntico al del repositorio en la fecha de este traspaso (SHA-256 del archivo original con BOM: `EFD1AB14B106134A467D272461E0257C95F56FB3EA764FB21EE12B2813571AAC`).*
