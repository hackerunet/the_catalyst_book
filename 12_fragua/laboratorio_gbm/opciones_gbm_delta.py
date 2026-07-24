import numpy as np
import pandas as pd
import scipy.stats as si
import os

# ==============================================================================
# LABORATORIO MATEMÁTICO: MOVIMIENTO BROWNIANO Y OPCIONES
# ==============================================================================
# Este script modela la incertidumbre del mercado mediante GBM, 
# valúa opciones con Black-Scholes, calcula las 5 Griegas principales,
# y ejecuta un experimento conceptual de Delta-Hedging.
# ==============================================================================

class BlackScholesCalculator:
    """Calculadora de Opciones Black-Scholes y sus Griegas."""
    
    def __init__(self, S, K, T, r, sigma):
        self.S = float(S)          # Precio Spot actual del subyacente
        self.K = float(K)          # Precio Strike (Ejercicio)
        self.T = float(T)          # Tiempo hasta el vencimiento (en años)
        self.r = float(r)          # Tasa libre de riesgo (anualizada)
        self.sigma = float(sigma)  # Volatilidad implícita (anualizada)
        
        # d1 y d2 son los componentes centrales de la ecuación BS
        # d1 mide la probabilidad ajustada al riesgo de que la opción expire In-The-Money
        self.d1 = (np.log(self.S / self.K) + (self.r + 0.5 * self.sigma ** 2) * self.T) / (self.sigma * np.sqrt(self.T))
        self.d2 = self.d1 - self.sigma * np.sqrt(self.T)
        
    def call_price(self):
        """Precio de una Call Europea"""
        return (self.S * si.norm.cdf(self.d1, 0.0, 1.0) - 
                self.K * np.exp(-self.r * self.T) * si.norm.cdf(self.d2, 0.0, 1.0))
                
    def put_price(self):
        """Precio de una Put Europea"""
        return (self.K * np.exp(-self.r * self.T) * si.norm.cdf(-self.d2, 0.0, 1.0) - 
                self.S * si.norm.cdf(-self.d1, 0.0, 1.0))

    # --- LAS 5 GRIEGAS ---
    
    def delta(self, type='call'):
        """Delta: Sensibilidad del precio de la opción respecto al precio Spot."""
        if type == 'call':
            return si.norm.cdf(self.d1, 0.0, 1.0)
        else:
            return si.norm.cdf(self.d1, 0.0, 1.0) - 1

    def gamma(self):
        """Gamma: Sensibilidad del Delta respecto al precio Spot (Curvatura)."""
        # Igual para Call y Put
        return si.norm.pdf(self.d1, 0.0, 1.0) / (self.S * self.sigma * np.sqrt(self.T))

    def vega(self):
        """Vega: Sensibilidad del precio respecto a la volatilidad implícita."""
        # Se reporta usualmente como cambio por 1% de volatilidad (/100)
        return self.S * si.norm.pdf(self.d1, 0.0, 1.0) * np.sqrt(self.T) / 100.0

    def theta(self, type='call'):
        """Theta: Sensibilidad del precio respecto al paso del tiempo (Decaimiento)."""
        # Se reporta usualmente como pérdida diaria de valor (/365)
        p1 = -(self.S * si.norm.pdf(self.d1, 0.0, 1.0) * self.sigma) / (2 * np.sqrt(self.T))
        if type == 'call':
            p2 = self.r * self.K * np.exp(-self.r * self.T) * si.norm.cdf(self.d2, 0.0, 1.0)
            return (p1 - p2) / 365.0
        else:
            p2 = self.r * self.K * np.exp(-self.r * self.T) * si.norm.cdf(-self.d2, 0.0, 1.0)
            return (p1 + p2) / 365.0

    def rho(self, type='call'):
        """Rho: Sensibilidad del precio respecto a la tasa de interés."""
        # Se reporta usualmente como cambio por 1% de tasa de interés (/100)
        if type == 'call':
            return self.K * self.T * np.exp(-self.r * self.T) * si.norm.cdf(self.d2, 0.0, 1.0) / 100.0
        else:
            return -self.K * self.T * np.exp(-self.r * self.T) * si.norm.cdf(-self.d2, 0.0, 1.0) / 100.0


def simulate_gbm(S0, mu, sigma, T, N):
    """
    Simula una trayectoria de precios usando Movimiento Browniano Geométrico.
    dS = S * (mu * dt + sigma * dW)
    """
    dt = T / N
    t = np.linspace(0, T, N+1)
    W = np.random.standard_normal(size=N)
    W = np.insert(W, 0, 0.0)
    W = np.cumsum(W) * np.sqrt(dt) # Proceso de Wiener
    
    # Solución analítica del GBM
    S = S0 * np.exp((mu - 0.5 * sigma**2) * t + sigma * W)
    return t, S

def run_delta_hedging_experiment():
    print("--- INICIANDO EXPERIMENTO DE DELTA-HEDGING ---")
    
    # Parámetros asimilados a Cripto
    S0 = 3500.0       # Precio inicial ETH
    K = 3500.0        # Strike At-The-Money
    T = 30 / 365.0    # 30 días de vencimiento
    r = 0.05          # Tasa libre de riesgo 5% (indicado por el usuario)
    sigma = 0.60      # 60% volatilidad anualizada
    N = 30            # Rebalanceo diario (30 pasos)
    
    print(f"Subyacente Inicial: ${S0} | Strike: ${K} | Volatilidad: {sigma*100}% | Tasa: {r*100}%")
    
    # Valuación inicial
    bs = BlackScholesCalculator(S0, K, T, r, sigma)
    call_px = bs.call_price()
    delta_init = bs.delta('call')
    print(f"\nValor de la Call (Venta a Cliente): ${call_px:.2f}")
    print(f"Griegas Iniciales -> Delta: {delta_init:.4f}, Gamma: {bs.gamma():.4f}, Vega: {bs.vega():.4f}")
    
    # El Market Maker Vende 1 Call. Está SHORT Call, por tanto tiene Delta Negativo (-0.54 aprox).
    # Para estar neutral, debe comprar +Delta acciones en Spot.
    
    # Simulamos el camino del precio Spot (GBM)
    t, S_path = simulate_gbm(S0, mu=0.0, sigma=sigma, T=T, N=N)
    
    portfolio_cash = call_px  # Recibimos la prima inicial
    shares_held = 0.0
    
    print("\nSimulación Paso a Paso (Rebalanceo Diario):")
    for i in range(N):
        current_S = S_path[i]
        time_to_expiry = T - t[i]
        
        # En el vencimiento (t[N] o cercano), Delta colapsa a 0 o 1
        if time_to_expiry < 1e-5:
            target_delta = 1.0 if current_S > K else 0.0
        else:
            calc = BlackScholesCalculator(current_S, K, time_to_expiry, r, sigma)
            target_delta = calc.delta('call')
            
        # Como vendimos 1 call, nuestra exposición al subyacente de la opción es -1 * target_delta.
        # Necesitamos poseer exactamente +target_delta en Spot para que la suma sea 0.
        shares_needed = target_delta - shares_held
        
        # Comprar/Vender acciones para el hedge
        cost = shares_needed * current_S
        
        # El cash rinde la tasa libre de riesgo r=5%
        if i > 0:
            dt = t[i] - t[i-1]
            portfolio_cash = portfolio_cash * np.exp(r * dt)
            
        portfolio_cash -= cost
        shares_held += shares_needed
        
        if i % 5 == 0 or i == N-1: # Imprimir cada 5 días
            print(f"Día {i:2d} | Precio Spot: ${current_S:.2f} | Delta Objetivo: {target_delta:.4f} | Cash: ${portfolio_cash:.2f}")
            
    # Día Final de Expiración
    final_S = S_path[-1]
    dt = T - t[-2]
    portfolio_cash = portfolio_cash * np.exp(r * dt)
    
    print("\n--- LIQUIDACIÓN FINAL EN VENCIMIENTO ---")
    print(f"Precio Final Spot: ${final_S:.2f}")
    option_payoff = max(final_S - K, 0.0)
    print(f"El cliente ejerce la Call y le debemos pagar: ${option_payoff:.2f}")
    
    # Liquidamos nuestras acciones hedgeadas a precio de mercado
    portfolio_cash += shares_held * final_S
    
    # Pagamos el payoff de la opción
    portfolio_cash -= option_payoff
    
    print(f"Caja Final del Market Maker tras pagar opción y liquidar Spot: ${portfolio_cash:.2f}")
    # En un mundo ideal continuo y sin comisiones, la caja final debería ser $0 (perfectamente cubierta)
    # Las discrepancias provienen del rebalanceo discreto (diario) y el costo de gamma.
    
if __name__ == '__main__':
    run_delta_hedging_experiment()
