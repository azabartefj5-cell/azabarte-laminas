// =====================================================================================
//  MaxBeneficioConAcierto80  -  Función de ajuste (Optimization Fitness) para NinjaTrader 8
// -------------------------------------------------------------------------------------
//  Úsala en Strategy Analyzer -> Optimization -> "Optimize on": MaxBeneficioConAcierto80.
//  Ordena las combinaciones de parámetros así:
//    1) las que tienen al menos un 80 % de operaciones ganadoras y suficientes operaciones,
//       por BENEFICIO NETO (mayor es mejor);
//    2) detrás, las que no llegan al 80 %, por cercanía a ese 80 %.
//  Así el optimizador busca "la máxima rentabilidad con al menos un 80 % de aciertos".
//
//  Instalación: copia este archivo en
//    Documentos\NinjaTrader 8\bin\Custom\OptimizationFitnesses\
//  y compila (F5) en el NinjaScript Editor.
//
//  AVISO: optimizar sobre el pasado encuentra siempre algo que parece bueno. Valida el
//  resultado con Walk Forward Optimization o en un periodo que no hayas usado para optimizar.
// =====================================================================================

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
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
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
#endregion

namespace NinjaTrader.NinjaScript.OptimizationFitnesses
{
    public class MaxBeneficioConAcierto80 : OptimizationFitness
    {
        // Cambia estos valores si quieres otro objetivo.
        private const double AciertoMinimo = 0.80;   // 80 % de operaciones ganadoras
        private const int OperacionesMinimas = 50;    // menos operaciones no son estadística

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
                Name = "MaxBeneficioConAcierto80";
        }

        protected override void OnCalculatePerformanceValue(StrategyBase strategy)
        {
            Value = Puntuacion(
                strategy.SystemPerformance.AllTrades.TradesCount,
                strategy.SystemPerformance.AllTrades.TradesPerformance.PercentProfitable,
                strategy.SystemPerformance.AllTrades.TradesPerformance.NetProfit);
        }

        /// <summary>Puntuación: beneficio neto si cumple los mínimos; si no, una penalización.</summary>
        public static double Puntuacion(int operaciones, double porcentajeGanadoras, double beneficioNeto)
        {
            // NinjaTrader da el porcentaje como fracción (0,80); se acepta también 80.
            double acierto = porcentajeGanadoras > 1.0 ? porcentajeGanadoras / 100.0 : porcentajeGanadoras;
            if (operaciones < OperacionesMinimas)
                return -2e9 + operaciones;
            if (acierto < AciertoMinimo)
                return -1e9 * (AciertoMinimo - acierto);
            return beneficioNeto;
        }
    }
}
