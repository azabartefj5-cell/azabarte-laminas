// Imitación mínima de la API de NinjaTrader 8 para compilar y ejecutar SistemaCombinadoES fuera
// de NinjaTrader. NO es NinjaTrader: sólo reproduce lo que usa la estrategia, con un motor de
// ejecución sencillo (órdenes a mercado a la apertura de la barra siguiente, stops y objetivos
// contra el máximo/mínimo de la barra). Sirve para detectar errores de compilación y de lógica.
using System;
using System.Collections.Generic;
using System.Linq;

namespace System.Windows { public class MarcadorStubWindows { } }
namespace System.Windows.Input { public class MarcadorStubInput { } }
namespace System.Windows.Media
{
    public class Brush { public string Nombre = ""; }
    public static class Brushes
    {
        public static readonly Brush DodgerBlue = new Brush { Nombre = "DodgerBlue" };
        public static readonly Brush OrangeRed = new Brush { Nombre = "OrangeRed" };
        public static readonly Brush Gold = new Brush { Nombre = "Gold" };
    }
}
namespace NinjaTrader.Gui { public class MarcadorStubGui { } }
namespace NinjaTrader.Gui.Chart { public class MarcadorStubChart { } }
namespace NinjaTrader.Gui.SuperDom { public class MarcadorStubSuperDom { } }
namespace NinjaTrader.Gui.Tools { public class MarcadorStubTools { } }
namespace NinjaTrader.Core.FloatingPoint { public class MarcadorStubFloatingPoint { } }
namespace NinjaTrader.NinjaScript.Indicators { public class MarcadorStubIndicators { } }
namespace NinjaTrader.NinjaScript.DrawingTools { public class MarcadorStubDrawingTools { } }

namespace NinjaTrader.Core
{
    public class OpcionesGenerales { public TimeZoneInfo TimeZoneInfo { get; set; } = TimeZoneInfo.Utc; }
    public static class Globals { public static OpcionesGenerales GeneralOptions { get; } = new OpcionesGenerales(); }
}

namespace NinjaTrader.Data
{
    public enum BarsPeriodType { Tick, Volume, Range, Second, Minute, Day, Week, Month, Year }
    public class BarsPeriod { public BarsPeriodType BarsPeriodType { get; set; } = BarsPeriodType.Minute; public int Value { get; set; } = 5; }

    /// <summary>Sesiones de negociación (inicio exclusivo, fin inclusivo) en la zona de la plataforma.</summary>
    public class Bars
    {
        public List<(DateTime Inicio, DateTime Fin)> SimSesiones { get; set; } = new();
        internal Func<int> BarraActual = () => 0;
        internal Func<int, DateTime> TiempoBarra = _ => DateTime.MinValue;

        internal int IndiceSesion(DateTime t)
        {
            int lo = 0, hi = SimSesiones.Count - 1;
            while (lo <= hi)
            {
                int m = (lo + hi) / 2;
                if (t <= SimSesiones[m].Inicio) hi = m - 1;
                else if (t > SimSesiones[m].Fin) lo = m + 1;
                else return m;
            }
            return -1 - lo;   // no está dentro: -(índice de la siguiente sesión) - 1
        }

        public bool IsFirstBarOfSession
        {
            get
            {
                int i = BarraActual();
                return i == 0 || IndiceSesion(TiempoBarra(i)) != IndiceSesion(TiempoBarra(i - 1));
            }
        }
    }

    public class SessionIterator
    {
        private readonly Bars bars;
        public SessionIterator(Bars bars) { this.bars = bars; }
        public DateTime ActualSessionBegin { get; private set; }
        public DateTime ActualSessionEnd { get; private set; }
        public bool GetNextSession(DateTime tiempo, bool incluyeFin)
        {
            int k = bars.IndiceSesion(tiempo);
            if (k < 0) k = -k - 1;
            if (k >= bars.SimSesiones.Count) return false;
            ActualSessionBegin = bars.SimSesiones[k].Inicio;
            ActualSessionEnd = bars.SimSesiones[k].Fin;
            return true;
        }
    }
}

namespace NinjaTrader.Cbi
{
    public enum OrderAction { Buy, BuyToCover, Sell, SellShort }
    public enum OrderType { Market, StopMarket, Limit }
    public enum MarketPosition { Flat, Long, Short }
    public enum OrderState { Initialized, Submitted, Accepted, Working, PartFilled, Filled, Cancelled, Rejected }
    public enum ErrorCode { NoError }
    public enum TimeInForce { Day, Gtc }
    public enum PerformanceUnit { Currency, Percent, Pips, Points, Ticks }

    public class Order
    {
        public string Name { get; set; } = "";
        public string FromEntrySignal { get; set; } = "";
        public OrderAction OrderAction { get; set; }
        public OrderType OrderType { get; set; }
        public int Quantity { get; set; }
        public double StopPrice { get; set; }
        public double LimitPrice { get; set; }
        public OrderState OrderState { get; set; } = OrderState.Initialized;
        public int Filled { get; set; }
        public double AverageFillPrice { get; set; }
        // Datos del simulador
        public int BarraEnvio;
        public string SenalReal = "";   // señal de entrada a la que pertenece (aunque FromEntrySignal esté vacío)
    }

    public class Execution { public Order Order { get; set; } = null!; public double Price { get; set; } public int Quantity { get; set; } public DateTime Time { get; set; } }

    public class MasterInstrument
    {
        public double PointValue { get; set; } = 50;
        public double TickSize { get; set; } = 0.25;
        public double RoundToTickSize(double p) => Math.Round(p / TickSize, MidpointRounding.AwayFromZero) * TickSize;
    }
    public class Instrument { public MasterInstrument MasterInstrument { get; } = new MasterInstrument(); }

    public class Position
    {
        internal Func<int> NetoProveedor = () => 0;
        internal Func<double, double> NoRealizado = _ => 0;
        public MarketPosition MarketPosition => NetoProveedor() > 0 ? MarketPosition.Long : NetoProveedor() < 0 ? MarketPosition.Short : MarketPosition.Flat;
        public int Quantity => Math.Abs(NetoProveedor());
        public double GetUnrealizedProfitLoss(PerformanceUnit unidad, double precio) => NoRealizado(precio);
    }
}

namespace NinjaTrader.NinjaScript
{
    using NinjaTrader.Cbi;

    public enum State { SetDefaults, Configure, Active, DataLoaded, Historical, Transition, Realtime, Terminated }
    public enum Calculate { OnBarClose, OnEachTick, OnPriceChange }
    public enum EntryHandling { AllEntries, UniqueEntries }
    public enum MaximumBarsLookBack { TwoHundredFiftySix, Infinite }
    public enum OrderFillResolution { Standard, High }
    public enum StartBehavior { AdoptAccountPosition, ImmediatelySubmit, ImmediatelySubmitSynchronizeAccount, WaitUntilFlat, WaitUntilFlatSynchronizeAccount }
    public enum RealtimeErrorHandling { IgnoreAllErrors, StopCancelClose, StopCancelCloseIgnoreRejects }
    public enum StopTargetHandling { ByStrategyPosition, PerEntryExecution }
    public enum CalculationMode { Currency, Percent, Pips, Price, Ticks }

    [AttributeUsage(AttributeTargets.Property)]
    public class NinjaScriptPropertyAttribute : Attribute { }

    public interface ISeries<T> { T this[int barsAgo] { get; } }

    public class SerieLectura<T> : ISeries<T>
    {
        private readonly Func<int, T> f;
        public SerieLectura(Func<int, T> f) { this.f = f; }
        public T this[int barsAgo] => f(barsAgo);
    }

    public class Series<T> : ISeries<T>
    {
        internal readonly Dictionary<int, T> Datos = new Dictionary<int, T>();
        internal Func<int> BarraActual = () => 0;
        public T this[int barsAgo]
        {
            get => Datos.TryGetValue(BarraActual() - barsAgo, out var v) ? v : default!;
            set => Datos[BarraActual() - barsAgo] = value;
        }
        public bool TieneValor(int barra) => Datos.ContainsKey(barra);
        public T ValorEn(int barra) => Datos[barra];
    }

    public class CurrencyPerf { public double CumProfit { get; internal set; } }
    public class TradesPerformance { public CurrencyPerf Currency { get; } = new CurrencyPerf(); }
    public class TradeCollection { public TradesPerformance TradesPerformance { get; } = new TradesPerformance(); }
    public class SystemPerformance { public TradeCollection AllTrades { get; } = new TradeCollection(); }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    using NinjaTrader.Cbi;
    using NinjaTrader.Data;

    public class BarraSim
    {
        public DateTime Tiempo;   // en la zona horaria de la "plataforma"
        public double Open, High, Low, Close, Volume;
    }

    public class OperacionSim
    {
        public string Senal = "";
        public int Lado;
        public int Cantidad;
        public double PrecioEntrada, PrecioSalida;
        public int BarraEntrada, BarraSalida, BarraEnvioEntrada;
        public string NombreSalida = "";
        public double Resultado;   // USD, neto de comisión
    }

    /// <summary>Lote abierto por una orden de entrada (equivale a "por señal de entrada" en NinjaTrader).</summary>
    internal class Lote
    {
        public string Senal = "";
        public int Lado;
        public int Cantidad;
        public double Precio;
        public int Barra, BarraEnvio;
        public Order? Stop, Objetivo;
        public bool SalidaPendiente;
    }

    public abstract class Strategy
    {
        // ---- Propiedades de configuración ----
        public string Description { get; set; } = "";
        public string Name { get; set; } = "";
        public Calculate Calculate { get; set; }
        public int EntriesPerDirection { get; set; }
        public EntryHandling EntryHandling { get; set; }
        public bool IsExitOnSessionCloseStrategy { get; set; }
        public int ExitOnSessionCloseSeconds { get; set; }
        public bool IsFillLimitOnTouch { get; set; }
        public MaximumBarsLookBack MaximumBarsLookBack { get; set; }
        public OrderFillResolution OrderFillResolution { get; set; }
        public double Slippage { get; set; }
        public StartBehavior StartBehavior { get; set; }
        public TimeInForce TimeInForce { get; set; }
        public bool TraceOrders { get; set; }
        public RealtimeErrorHandling RealtimeErrorHandling { get; set; }
        public StopTargetHandling StopTargetHandling { get; set; }
        public int BarsRequiredToTrade { get; set; }
        public bool IsInstantiatedOnEachOptimizationIteration { get; set; }
        public bool IsOverlay { get; set; }

        // ---- Estado y datos ----
        public State State { get; private set; }
        public int BarsInProgress => 0;
        public int CurrentBar { get; private set; }
        public BarsPeriod BarsPeriod { get; } = new BarsPeriod();
        public Bars Bars { get; } = new Bars();
        public Instrument Instrument { get; } = new Instrument();
        public double TickSize => Instrument.MasterInstrument.TickSize;
        public Position Position { get; } = new Position();
        public SystemPerformance SystemPerformance { get; } = new SystemPerformance();
        public ISeries<DateTime> Time { get; }
        public ISeries<double> Open { get; }
        public ISeries<double> High { get; }
        public ISeries<double> Low { get; }
        public ISeries<double> Close { get; }
        public ISeries<double> Volume { get; }
        public Series<double>[] Values => valores.ToArray();

        // ---- Simulador ----
        public bool SimStopsSinSenal { get; set; }          // simula stops con FromEntrySignal vacío
        public double SimComisionPorLado { get; set; } = 2.25; // USD por contrato y lado
        public List<string> SimSalida { get; } = new List<string>();
        public List<string> SimViolaciones { get; } = new List<string>();
        public List<OperacionSim> SimOperaciones { get; } = new List<OperacionSim>();
        public List<Order> SimOrdenes { get; } = new List<Order>();
        public int SimMaxContratosAbiertos { get; private set; }
        public List<string> SimNombresPlots { get; } = new List<string>();

        private readonly List<Series<double>> valores = new List<Series<double>>();
        private List<BarraSim> barras = new List<BarraSim>();
        private readonly List<Lote> lotes = new List<Lote>();
        private readonly List<Order> mercadoPendientes = new List<Order>();
        private readonly Dictionary<string, (CalculationMode modo, double valor)> stopsCfg = new();
        private readonly Dictionary<string, (CalculationMode modo, double valor)> objetivosCfg = new();

        protected Strategy()
        {
            Time = new SerieLectura<DateTime>(a => barras[CurrentBar - a].Tiempo);
            Open = new SerieLectura<double>(a => barras[CurrentBar - a].Open);
            High = new SerieLectura<double>(a => barras[CurrentBar - a].High);
            Low = new SerieLectura<double>(a => barras[CurrentBar - a].Low);
            Close = new SerieLectura<double>(a => barras[CurrentBar - a].Close);
            Volume = new SerieLectura<double>(a => barras[CurrentBar - a].Volume);
            Bars.BarraActual = () => CurrentBar;
            Bars.TiempoBarra = i => barras[i].Tiempo;
            Position.NetoProveedor = () => lotes.Sum(l => l.Lado * l.Cantidad);
            Position.NoRealizado = p => lotes.Sum(l => l.Lado * (p - l.Precio) * l.Cantidad * Instrument.MasterInstrument.PointValue);
        }

        protected virtual void OnStateChange() { }
        protected virtual void OnBarUpdate() { }
        protected virtual void OnOrderUpdate(Order order, double limitPrice, double stopPrice, int quantity, int filled,
            double averageFillPrice, OrderState orderState, DateTime time, ErrorCode error, string comment) { }
        protected virtual void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity,
            MarketPosition marketPosition, string orderId, DateTime time) { }

        public void Print(object o) => SimSalida.Add(o?.ToString() ?? "");

        public void AddPlot(System.Windows.Media.Brush pincel, string nombre)
        {
            var s = new Series<double>();
            s.BarraActual = () => CurrentBar;
            valores.Add(s);
            SimNombresPlots.Add(nombre);
        }

        // ---- Órdenes (enfoque gestionado) ----
        public Order? EnterLong(int cantidad, string senal) => Entrada(1, cantidad, senal);
        public Order? EnterShort(int cantidad, string senal) => Entrada(-1, cantidad, senal);

        private Order? Entrada(int lado, int cantidad, string senal)
        {
            int neto = Position.NetoProveedor();
            if (neto * lado < 0) { SimViolaciones.Add($"{Time[0]:yyyy-MM-dd HH:mm} INVERSIÓN: entrada {senal} con posición contraria {neto}"); return null; }
            if (lotes.Any(l => l.Senal == senal) || mercadoPendientes.Any(o => o.Name == senal))
            { SimViolaciones.Add($"{Time[0]:yyyy-MM-dd HH:mm} ENTRADA IGNORADA: {senal} ya abierta"); return null; }
            if (cantidad < 1) { SimViolaciones.Add($"ENTRADA con cantidad {cantidad}"); return null; }
            var o = new Order { Name = senal, OrderAction = lado > 0 ? OrderAction.Buy : OrderAction.SellShort, OrderType = OrderType.Market, Quantity = cantidad, BarraEnvio = CurrentBar, SenalReal = senal };
            Enviar(o);
            mercadoPendientes.Add(o);
            return o;
        }

        public Order? ExitLong(string nombre, string desdeEntrada) => Salida(1, nombre, desdeEntrada);
        public Order? ExitShort(string nombre, string desdeEntrada) => Salida(-1, nombre, desdeEntrada);

        private Order? Salida(int lado, string nombre, string desdeEntrada)
        {
            var lote = lotes.FirstOrDefault(l => l.Senal == desdeEntrada && l.Lado == lado);
            if (lote == null) { SimViolaciones.Add($"{Time[0]:yyyy-MM-dd HH:mm} SALIDA IGNORADA: {desdeEntrada} no está abierta"); return null; }
            if (lote.SalidaPendiente) { SimViolaciones.Add($"{Time[0]:yyyy-MM-dd HH:mm} SALIDA DUPLICADA: {desdeEntrada}"); return null; }
            lote.SalidaPendiente = true;
            var o = new Order { Name = nombre, FromEntrySignal = desdeEntrada, OrderAction = lado > 0 ? OrderAction.Sell : OrderAction.BuyToCover, OrderType = OrderType.Market, Quantity = lote.Cantidad, BarraEnvio = CurrentBar, SenalReal = desdeEntrada };
            Enviar(o);
            mercadoPendientes.Add(o);
            return o;
        }

        public void SetStopLoss(string desdeEntrada, CalculationMode modo, double valor, bool simulado) => stopsCfg[desdeEntrada] = (modo, valor);
        public void SetProfitTarget(string desdeEntrada, CalculationMode modo, double valor) => objetivosCfg[desdeEntrada] = (modo, valor);

        private void Enviar(Order o)
        {
            SimOrdenes.Add(o);
            Actualizar(o, OrderState.Submitted);
            Actualizar(o, OrderState.Working);
        }

        private void Actualizar(Order o, OrderState estado)
        {
            o.OrderState = estado;
            OnOrderUpdate(o, o.LimitPrice, o.StopPrice, o.Quantity, o.Filled, o.AverageFillPrice, estado, barras[CurrentBar].Tiempo, ErrorCode.NoError, "");
        }

        private void Ejecutar(Order o, double precio)
        {
            o.Filled = o.Quantity;
            o.AverageFillPrice = precio;
            Actualizar(o, OrderState.Filled);
            bool esEntrada = o.OrderAction == OrderAction.Buy || o.OrderAction == OrderAction.SellShort;
            double pv = Instrument.MasterInstrument.PointValue;
            if (esEntrada)
            {
                int lado = o.OrderAction == OrderAction.Buy ? 1 : -1;
                var lote = new Lote { Senal = o.Name, Lado = lado, Cantidad = o.Quantity, Precio = precio, Barra = CurrentBar, BarraEnvio = o.BarraEnvio };
                lotes.Add(lote);
                SimMaxContratosAbiertos = Math.Max(SimMaxContratosAbiertos, lotes.Sum(l => l.Cantidad));
                SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit -= SimComisionPorLado * o.Quantity;
                OnExecutionUpdate(new Execution { Order = o, Price = precio, Quantity = o.Quantity, Time = barras[CurrentBar].Tiempo }, Guid.NewGuid().ToString(), precio, o.Quantity, Position.MarketPosition, Guid.NewGuid().ToString(), barras[CurrentBar].Tiempo);
                // Stop y objetivo por ejecución de entrada (StopTargetHandling.PerEntryExecution)
                if (stopsCfg.TryGetValue(lote.Senal, out var sc))
                {
                    double p = sc.modo == CalculationMode.Price ? sc.valor : precio - lado * sc.valor * TickSize;
                    lote.Stop = new Order { Name = "Stop loss", FromEntrySignal = SimStopsSinSenal ? "" : lote.Senal, SenalReal = lote.Senal, OrderAction = lado > 0 ? OrderAction.Sell : OrderAction.BuyToCover, OrderType = OrderType.StopMarket, Quantity = lote.Cantidad, StopPrice = p, BarraEnvio = CurrentBar };
                    Enviar(lote.Stop);
                }
                if (objetivosCfg.TryGetValue(lote.Senal, out var oc))
                {
                    double p = oc.modo == CalculationMode.Price ? oc.valor : precio + lado * oc.valor * TickSize;
                    lote.Objetivo = new Order { Name = "Profit target", FromEntrySignal = SimStopsSinSenal ? "" : lote.Senal, SenalReal = lote.Senal, OrderAction = lado > 0 ? OrderAction.Sell : OrderAction.BuyToCover, OrderType = OrderType.Limit, Quantity = lote.Cantidad, LimitPrice = p, BarraEnvio = CurrentBar };
                    Enviar(lote.Objetivo);
                }
            }
            else
            {
                var lote = lotes.First(l => l.Senal == o.SenalReal);
                lotes.Remove(lote);
                double resultado = lote.Lado * (precio - lote.Precio) * lote.Cantidad * pv - 2 * SimComisionPorLado * lote.Cantidad;
                SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit += lote.Lado * (precio - lote.Precio) * lote.Cantidad * pv - SimComisionPorLado * lote.Cantidad;
                SimOperaciones.Add(new OperacionSim { Senal = lote.Senal, Lado = lote.Lado, Cantidad = lote.Cantidad, PrecioEntrada = lote.Precio, PrecioSalida = precio, BarraEntrada = lote.Barra, BarraSalida = CurrentBar, BarraEnvioEntrada = lote.BarraEnvio, NombreSalida = o.Name, Resultado = resultado });
                OnExecutionUpdate(new Execution { Order = o, Price = precio, Quantity = o.Quantity, Time = barras[CurrentBar].Tiempo }, Guid.NewGuid().ToString(), precio, o.Quantity, Position.MarketPosition, Guid.NewGuid().ToString(), barras[CurrentBar].Tiempo);
                foreach (var otra in new[] { lote.Stop, lote.Objetivo })
                    if (otra != null && otra != o && otra.OrderState == OrderState.Working)
                        Actualizar(otra, OrderState.Cancelled);
            }
        }

        // ---- Bucle de simulación ----
        public void SimConfigurar(Action<Strategy>? parametros)
        {
            State = State.SetDefaults; OnStateChange();
            parametros?.Invoke(this);
            State = State.Configure; OnStateChange();
        }

        public void SimEjecutar(List<BarraSim> datos)
        {
            barras = datos;
            CurrentBar = 0;
            State = State.DataLoaded; OnStateChange();
            State = State.Historical;
            double tick = TickSize;
            for (int i = 0; i < barras.Count; i++)
            {
                CurrentBar = i;
                var b = barras[i];
                // 1) órdenes a mercado enviadas en la barra anterior: se ejecutan a la apertura
                foreach (var o in mercadoPendientes.ToList())
                {
                    mercadoPendientes.Remove(o);
                    bool compra = o.OrderAction == OrderAction.Buy || o.OrderAction == OrderAction.BuyToCover;
                    Ejecutar(o, b.Open + (compra ? 1 : -1) * Slippage * tick);
                }
                // 2) stops y objetivos contra el rango de la barra (el stop primero, criterio prudente)
                foreach (var l in lotes.ToList())
                {
                    if (l.Stop != null && l.Stop.OrderState == OrderState.Working)
                    {
                        double s = l.Stop.StopPrice;
                        bool toca = l.Lado > 0 ? b.Low <= s : b.High >= s;
                        if (toca)
                        {
                            double p = l.Lado > 0 ? Math.Min(b.Open, s) : Math.Max(b.Open, s);
                            Ejecutar(l.Stop, p - l.Lado * Slippage * tick);
                            continue;
                        }
                    }
                    if (l.Objetivo != null && l.Objetivo.OrderState == OrderState.Working)
                    {
                        double s = l.Objetivo.LimitPrice;
                        bool toca = l.Lado > 0 ? b.High > s : b.Low < s;
                        if (toca)
                            Ejecutar(l.Objetivo, l.Lado > 0 ? Math.Max(b.Open, s) : Math.Min(b.Open, s));
                    }
                }
                // 3) lógica de la estrategia al cierre de la barra
                OnBarUpdate();
            }
            State = State.Terminated; OnStateChange();
        }
    }
}
