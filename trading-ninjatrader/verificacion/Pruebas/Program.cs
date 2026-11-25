// Banco de pruebas de SistemaCombinadoES sobre datos SINTÉTICOS (paseo aleatorio con días de
// tendencia y reversión entre días). Los resultados en dólares no significan nada: sólo se
// comprueba que la lógica hace lo que dicen las reglas.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript.Strategies;
using SistemaCombinadoESComun;

static class Program
{
    static readonly TimeZoneInfo Ny = Zona("Eastern Standard Time", "America/New_York");
    static readonly TimeZoneInfo Madrid = Zona("Romance Standard Time", "Europe/Madrid");
    static int fallos;
    static List<(DateTime Inicio, DateTime Fin)> sesiones5, sesiones1;

    static TimeZoneInfo Zona(params string[] ids)
    {
        foreach (var id in ids) { try { return TimeZoneInfo.FindSystemTimeZoneById(id); } catch { } }
        throw new Exception("zona no encontrada");
    }

    record BarraNy(DateTime Ny, double O, double H, double L, double C, double V);

    static int Main()
    {
        var datos5 = Generar(semilla: 7, minutos: 5, desde: new DateTime(2022, 1, 3), hasta: new DateTime(2024, 3, 29), out sesiones5);
        var datos1 = Generar(semilla: 11, minutos: 1, desde: new DateTime(2023, 1, 3), hasta: new DateTime(2023, 12, 29), out sesiones1);
        Console.WriteLine($"Datos 5 min: {datos5.Count} barras; datos 1 min: {datos1.Count} barras");

        // A) Configuración por defecto (momentum + RSI2), plataforma en hora de Madrid
        var a = Ejecutar("A: por defecto, NinjaTrader en hora de Madrid", datos5, Madrid, 5, null);
        // B) Igual con la plataforma en hora de Nueva York: mismas operaciones
        var b = Ejecutar("B: por defecto, NinjaTrader en hora de Nueva York", datos5, Ny, 5, null);
        Comparar("A vs B (zona horaria de la plataforma)", a, b);
        // C) Stops con FromEntrySignal vacío (comportamiento visto en algunas versiones de NT8)
        var c = Ejecutar("C: por defecto, stops sin FromEntrySignal", datos5, Madrid, 5, null, stopsSinSenal: true);
        Comparar("A vs C (stops sin señal)", a, c);

        // D) Todo activado, tamaño dinámico, límite diario y fechas excluidas
        var excluidas = new[] { "2023-03-22", "2023-05-03", "2023-06-14" };
        var d = Ejecutar("D: tres módulos, tamaño dinámico, límites", datos5, Madrid, 5, s =>
        {
            s.OrbActivo = true; s.ModoTamano = ModoTamanoPosicion.Dinamico; s.CapitalCuenta = 2_000_000;
            s.MaxContratos = 6; s.MaxPerdidaDiaria = 15000; s.FechasExcluidas = string.Join(";", excluidas);
            s.SwingCortos = true; s.FiltroTendenciaIntradia = true;
        });
        Verificar(d.Est.SimMaxContratosAbiertos <= 6, $"máximo de contratos respetado ({d.Est.SimMaxContratosAbiertos} <= 6)");
        var entradasExcluidas = d.Est.SimOrdenes.Count(o => EsEntrada(o) && excluidas.Contains(FechaNy(d, o.BarraEnvio)));
        Verificar(entradasExcluidas == 0, $"sin entradas en fechas excluidas ({entradasExcluidas})");

        // E) Sólo el swing RSI2: comparar con una simulación independiente de las reglas de Connors
        var e = Ejecutar("E: sólo swing RSI(2)", datos5, Madrid, 5, s => { s.MomActivo = false; });
        ComprobarSwingCompleto(e);

        // F) Barras de 1 minuto con todos los módulos
        var f = Ejecutar("F: barras de 1 minuto, tres módulos", datos1, Madrid, 1, s => { s.OrbActivo = true; s.MaxContratos = 3; });

        // G) ORB solo, para validar sus reglas una a una
        var g = Ejecutar("G: sólo ORB", datos5, Madrid, 5, s => { s.MomActivo = false; s.SwingActivo = false; s.OrbActivo = true; });
        ComprobarOrb(g);

        Console.WriteLine();
        Console.WriteLine(fallos == 0 ? "RESULTADO: todas las comprobaciones correctas" : $"RESULTADO: {fallos} comprobaciones FALLIDAS");
        return fallos == 0 ? 0 : 1;
    }

    // =========================================================================================
    class Ejecucion
    {
        public string Titulo = "";
        public SistemaCombinadoES Est = null!;
        public List<BarraNy> Datos = null!;
        public int Minutos;
    }

    static Ejecucion Ejecutar(string titulo, List<BarraNy> datosNy, TimeZoneInfo zonaPlataforma, int minutos,
                              Action<SistemaCombinadoES> parametros, bool stopsSinSenal = false)
    {
        NinjaTrader.Core.Globals.GeneralOptions.TimeZoneInfo = zonaPlataforma;
        var barras = datosNy.Select(x => new BarraSim
        {
            Tiempo = TimeZoneInfo.ConvertTime(x.Ny, Ny, zonaPlataforma),
            Open = x.O, High = x.H, Low = x.L, Close = x.C, Volume = x.V
        }).ToList();

        var s = new SistemaCombinadoES();
        s.BarsPeriod.Value = minutos;
        s.Bars.SimSesiones = (minutos == 5 ? sesiones5 : sesiones1)
            .Select(x => (TimeZoneInfo.ConvertTime(x.Inicio, Ny, zonaPlataforma), TimeZoneInfo.ConvertTime(x.Fin, Ny, zonaPlataforma))).ToList();
        s.SimStopsSinSenal = stopsSinSenal;
        s.SimConfigurar(x => parametros?.Invoke((SistemaCombinadoES)x));
        s.SimEjecutar(barras);
        var ej = new Ejecucion { Titulo = titulo, Est = s, Datos = datosNy, Minutos = minutos };

        Console.WriteLine();
        Console.WriteLine("== " + titulo);
        foreach (var grupo in s.SimOperaciones.GroupBy(o => o.Senal.Substring(0, o.Senal.IndexOf('_'))).OrderBy(x => x.Key))
        {
            var ops = grupo.ToList();
            Console.WriteLine($"   {grupo.Key,-5} operaciones={ops.Count,4}  largas={ops.Count(o => o.Lado > 0),4}  cortas={ops.Count(o => o.Lado < 0),4}  " +
                              $"acierto={100.0 * ops.Count(o => o.Resultado > 0) / ops.Count,5:0.0}%  salidas: " +
                              string.Join(", ", ops.GroupBy(o => o.NombreSalida.EndsWith("_X") ? "estrategia" : o.NombreSalida).Select(x => $"{x.Key}={x.Count()}")));
        }
        foreach (var l in s.SimSalida.Where(x => x.Contains("AVISO") || x.Contains("RECHAZADA")).Take(5))
            Console.WriteLine("   salida: " + l);

        Verificar(s.SimViolaciones.Count == 0, $"[{titulo}] sin órdenes ignoradas/invertidas/duplicadas ({s.SimViolaciones.Count})");
        foreach (var v in s.SimViolaciones.Take(5)) Console.WriteLine("      " + v);
        Verificar(!s.SimSalida.Any(x => x.Contains("seguimiento interno")), $"[{titulo}] seguimiento interno de posiciones coherente");
        Verificar(s.SimOperaciones.Count > 0, $"[{titulo}] hay operaciones");
        ComprobarIntradia(ej);
        if (s.MomActivo) ComprobarMomentum(ej);
        return ej;
    }

    // ---- Comprobaciones ---------------------------------------------------------------------
    static void ComprobarIntradia(Ejecucion ej)
    {
        int malas = 0;
        foreach (var op in ej.Est.SimOperaciones.Where(o => o.Senal.StartsWith("MOM") || o.Senal.StartsWith("ORB")))
        {
            var ent = ej.Datos[op.BarraEntrada].Ny; var sal = ej.Datos[op.BarraSalida].Ny;
            bool mismoDia = ent.Date == sal.Date;
            bool antesDeCierre = sal.TimeOfDay <= (DiaCortoNy(ent.Date) ? new TimeSpan(13, 5, 0) : new TimeSpan(16, 0, 0));
            if (!mismoDia || !antesDeCierre) { malas++; if (malas <= 3) Console.WriteLine($"      intradía fuera de hora: {op.Senal} {ent} -> {sal}"); }
            if (ent.TimeOfDay <= new TimeSpan(9, 30, 0)) malas++;
        }
        Verificar(malas == 0, $"[{ej.Titulo}] momentum/ORB entran en sesión regular y cierran el mismo día antes de las 16:00 NY ({malas})");
    }

    static void ComprobarMomentum(Ejecucion ej)
    {
        var dias = DiasRth(ej.Datos);
        var indiceDia = dias.Select((d, i) => (d.Fecha, i)).ToDictionary(x => x.Fecha, x => x.i);
        var s = ej.Est;
        int revisadas = 0, malas = 0, giros = 0;
        foreach (var o in s.SimOrdenes.Where(o => EsEntrada(o) && o.Name.StartsWith("MOM")))
        {
            var ny = ej.Datos[o.BarraEnvio].Ny;
            int t = ny.Hour * 60 + ny.Minute;
            bool esRevision = t >= 600 && t <= 930 && (t - 570) % 30 == 0;
            int barraSenal = o.BarraEnvio;
            if (!esRevision)
            {
                // entrada por giro: la barra anterior debe ser una revisión
                var nyAnt = ej.Datos[o.BarraEnvio - 1].Ny; int tAnt = nyAnt.Hour * 60 + nyAnt.Minute;
                if (!(tAnt >= 600 && (tAnt - 570) % 30 == 0)) { malas++; continue; }
                barraSenal = o.BarraEnvio - 1; giros++;
                ny = nyAnt; t = tAnt;
            }
            int k = indiceDia[ny.Date];
            if (k < 14) { malas++; continue; }
            var previos = dias.Skip(k - 14).Take(14).ToList();
            var movs = previos.Where(d => d.Movs.ContainsKey(t)).Select(d => d.Movs[t]).ToList();
            double sigma = movs.Average();
            double ap = dias[k].Apertura, cp = dias[k - 1].Cierre;
            double ub = Math.Max(ap, cp) * (1 + sigma), lb = Math.Min(ap, cp) * (1 - sigma);
            double c = ej.Datos[barraSenal].C;
            bool ok = o.OrderAction == OrderAction.Buy ? c > ub : c < lb;
            // la banda dibujada por la estrategia debe coincidir con la calculada aquí
            var plots = s.Values;
            if (plots[0].TieneValor(barraSenal) && Math.Abs(plots[0].ValorEn(barraSenal) - ub) > 1e-6) ok = false;
            if (plots[1].TieneValor(barraSenal) && Math.Abs(plots[1].ValorEn(barraSenal) - lb) > 1e-6) ok = false;
            revisadas++;
            if (!ok) { malas++; if (malas <= 3) Console.WriteLine($"      momentum dudoso {o.Name} {ny} c={c} ub={ub:0.00} lb={lb:0.00}"); }
        }
        Verificar(revisadas > 0 && malas == 0, $"[{ej.Titulo}] {revisadas} entradas de momentum ({giros} por giro) en hora de revisión y fuera de la banda recalculada ({malas} incorrectas)");
    }

    static void ComprobarOrb(Ejecucion ej)
    {
        int malas = 0, n = 0;
        foreach (var op in ej.Est.SimOperaciones.Where(o => o.Senal.StartsWith("ORB")))
        {
            n++;
            var barraOr = ej.Datos[op.BarraEnvioEntrada];
            if (barraOr.Ny.TimeOfDay != new TimeSpan(9, 35, 0)) malas++;
            int dir = barraOr.C > barraOr.O ? 1 : -1;
            if (dir != op.Lado) malas++;
            double stop = dir > 0 ? barraOr.L : barraOr.H;
            if (op.NombreSalida == "Stop loss" && Math.Abs(op.PrecioSalida - stop) > 1.0 &&
                (dir > 0 ? op.PrecioSalida > stop : op.PrecioSalida < stop)) malas++;
        }
        Verificar(n > 0 && malas == 0, $"[{ej.Titulo}] {n} operaciones ORB con la dirección y el stop de la primera vela ({malas} incorrectas)");
    }

    /// <summary>Simulación independiente de RSI(2): mismas fechas de entrada y salida.</summary>
    static void ComprobarSwingCompleto(Ejecucion ej)
    {
        var dias = DiasRth(ej.Datos);
        var cierres = dias.Select(d => d.Cierre).ToList();
        var esperadasEntradas = new List<DateTime>(); var esperadasSalidas = new List<DateTime>();
        bool dentro = false; int diaEntrada = 0;
        for (int i = 200; i < dias.Count; i++)
        {
            var hasta = cierres.Take(i + 1).ToList();
            double sma200 = hasta.Skip(hasta.Count - 200).Average(), sma5 = hasta.Skip(hasta.Count - 5).Average();
            double rsi = RsiReferencia(hasta, 2);
            if (dentro)
            {
                if (cierres[i] > sma5 || i - diaEntrada >= 10) { dentro = false; esperadasSalidas.Add(dias[i].Fecha); }
            }
            else if (cierres[i] > sma200 && rsi < 10) { dentro = true; diaEntrada = i; esperadasEntradas.Add(dias[i].Fecha); }
        }
        var s = ej.Est;
        var reales = s.SimOrdenes.Where(o => EsEntrada(o) && o.Name == "RSI2_L").Select(o => ej.Datos[o.BarraEnvio].Ny.Date).ToList();
        var salidas = s.SimOrdenes.Where(o => o.Name == "RSI2_L_X").Select(o => ej.Datos[o.BarraEnvio].Ny.Date).ToList();
        var stops = s.SimOperaciones.Count(o => o.Senal == "RSI2_L" && o.NombreSalida == "Stop loss");
        bool iguales = reales.SequenceEqual(esperadasEntradas) && salidas.SequenceEqual(esperadasSalidas.Take(salidas.Count));
        Verificar(stops > 0 || iguales, $"[{ej.Titulo}] entradas RSI(2) iguales a la simulación independiente ({reales.Count} reales, {esperadasEntradas.Count} esperadas, {stops} stops de emergencia)");
        if (!iguales && stops == 0)
        {
            Console.WriteLine("      reales:    " + string.Join(" ", reales.Take(8).Select(x => x.ToString("yyyy-MM-dd"))));
            Console.WriteLine("      esperadas: " + string.Join(" ", esperadasEntradas.Take(8).Select(x => x.ToString("yyyy-MM-dd"))));
        }
    }

    static double RsiReferencia(List<double> c, int p)
    {
        // Wilder clásico sobre toda la serie disponible (máx. 250 valores, como la estrategia)
        int inicio = Math.Max(1, c.Count - 250);
        double g = 0, l = 0;
        for (int i = inicio; i < inicio + p; i++) { double d = c[i] - c[i - 1]; g += Math.Max(d, 0); l += Math.Max(-d, 0); }
        g /= p; l /= p;
        for (int i = inicio + p; i < c.Count; i++) { double d = c[i] - c[i - 1]; g = (g * (p - 1) + Math.Max(d, 0)) / p; l = (l * (p - 1) + Math.Max(-d, 0)) / p; }
        return l == 0 ? 100 : 100 - 100 / (1 + g / l);
    }

    static void Comparar(string titulo, Ejecucion x, Ejecucion y)
    {
        string Firma(Ejecucion e) => string.Join("|", e.Est.SimOperaciones.Select(o =>
            $"{o.Senal}:{e.Datos[o.BarraEntrada].Ny:yyyyMMddHHmm}:{o.PrecioEntrada}:{e.Datos[o.BarraSalida].Ny:yyyyMMddHHmm}:{o.PrecioSalida}:{o.Cantidad}"));
        Verificar(Firma(x) == Firma(y), $"{titulo}: operaciones idénticas ({x.Est.SimOperaciones.Count} / {y.Est.SimOperaciones.Count})");
    }

    // ---- Utilidades ------------------------------------------------------------------------
    class DiaRef { public DateTime Fecha; public double Apertura, Cierre; public Dictionary<int, double> Movs = new(); }

    static List<DiaRef> DiasRth(List<BarraNy> datos)
    {
        var r = new List<DiaRef>();
        foreach (var g in datos.Where(b => { int t = b.Ny.Hour * 60 + b.Ny.Minute; return t > 570 && t <= 960; }).GroupBy(b => b.Ny.Date))
        {
            var l = g.ToList();
            var d = new DiaRef { Fecha = g.Key, Apertura = l[0].O, Cierre = l[^1].C };
            foreach (var b in l) d.Movs[b.Ny.Hour * 60 + b.Ny.Minute] = Math.Abs(b.C / d.Apertura - 1);
            r.Add(d);
        }
        return r;
    }

    static bool EsEntrada(Order o) => (o.OrderAction == OrderAction.Buy || o.OrderAction == OrderAction.SellShort) && !o.Name.Contains(' ') && !o.Name.EndsWith("_X");
    static string FechaNy(Ejecucion e, int barra) => e.Datos[barra].Ny.ToString("yyyy-MM-dd");

    static void Verificar(bool condicion, string texto)
    {
        Console.WriteLine((condicion ? "   [OK]    " : "   [FALLO] ") + texto);
        if (!condicion) fallos++;
    }

    // ---- Generador de datos sintéticos (hora de Nueva York) ---------------------------------
    static readonly HashSet<DateTime> Festivos = new[] {
        "2022-01-17","2022-02-21","2022-04-15","2022-05-30","2022-06-20","2022-07-04","2022-09-05","2022-11-24","2022-12-26",
        "2023-01-02","2023-01-16","2023-02-20","2023-04-07","2023-05-29","2023-06-19","2023-07-04","2023-09-04","2023-11-23","2023-12-25",
        "2024-01-01","2024-01-15","2024-02-19","2024-03-29" }.Select(x => DateTime.Parse(x, CultureInfo.InvariantCulture)).ToHashSet();
    static readonly HashSet<DateTime> DiasCortos = new[] { "2022-11-25", "2023-07-03", "2023-11-24" }
        .Select(x => DateTime.Parse(x, CultureInfo.InvariantCulture)).ToHashSet();
    static bool DiaCortoNy(DateTime d) => DiasCortos.Contains(d.Date);

    static List<BarraNy> Generar(int semilla, int minutos, DateTime desde, DateTime hasta, out List<(DateTime Inicio, DateTime Fin)> sesiones)
    {
        sesiones = new List<(DateTime Inicio, DateTime Fin)>();
        var rnd = new Random(semilla);
        double Normal() { double u1 = 1 - rnd.NextDouble(), u2 = rnd.NextDouble(); return Math.Sqrt(-2 * Math.Log(u1)) * Math.Cos(2 * Math.PI * u2); }
        double Tick(double p) => Math.Round(p * 4) / 4;

        var r = new List<BarraNy>();
        double precio = 4000, retornoRthPrevio = 0;
        for (var dia = desde; dia <= hasta; dia = dia.AddDays(1))
        {
            if (dia.DayOfWeek == DayOfWeek.Saturday || dia.DayOfWeek == DayOfWeek.Sunday || Festivos.Contains(dia)) continue;
            bool corto = DiasCortos.Contains(dia);
            int finRth = corto ? 13 * 60 : 16 * 60, finSesion = corto ? 13 * 60 + 15 : 17 * 60;
            // tipo de día: tendencia (momentum intradía) o rango; la noche revierte parte del día anterior
            double tendencia = rnd.NextDouble() < 0.35 ? (rnd.NextDouble() < 0.55 ? 1 : -1) * (0.004 + 0.006 * rnd.NextDouble()) : 0;
            double derivaNoche = -0.35 * retornoRthPrevio;
            var inicio = dia.AddDays(-1).AddHours(18);
            var fin = dia.AddMinutes(finSesion);
            sesiones.Add((inicio, fin));
            int barrasNoche = (int)((dia.AddMinutes(570) - inicio).TotalMinutes / minutos);
            int barrasRth = (finRth - 570) / minutos;
            double aperturaRth = 0;
            for (var t = inicio.AddMinutes(minutos); t <= fin; t = t.AddMinutes(minutos))
            {
                int m = t.Hour * 60 + t.Minute;
                bool enRth = t.Date == dia && m > 570 && m <= finRth;
                double sigma = (enRth ? 0.0011 : 0.00035) * Math.Sqrt(minutos / 5.0);
                double deriva = enRth ? (tendencia + 0.0003) / barrasRth : (t < dia.AddMinutes(570) ? derivaNoche / barrasNoche : 0);
                double o = precio;
                if (enRth && aperturaRth == 0) aperturaRth = o;
                double c = o * Math.Exp(deriva + sigma * Normal());
                double h = Math.Max(o, c) * (1 + Math.Abs(Normal()) * sigma * 0.4);
                double l = Math.Min(o, c) * (1 - Math.Abs(Normal()) * sigma * 0.4);
                double v = enRth ? 2000 + rnd.Next(3000) : 150 + rnd.Next(300);
                r.Add(new BarraNy(t, Tick(o), Tick(h), Tick(l), Tick(c), v));
                precio = Tick(c);
                if (enRth && m == finRth) retornoRthPrevio = precio / aperturaRth - 1;
            }
        }
        return r;
    }
}
