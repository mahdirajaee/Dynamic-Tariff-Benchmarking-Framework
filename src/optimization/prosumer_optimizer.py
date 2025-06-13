import numpy as np
import cvxpy as cp
from typing import Dict, List, Tuple, Optional
import pandas as pd


class ProsumerCommunityOptimizer:
    """
    Single-level optimization for prosumer community energy management
    with dynamic tariffs and peer-to-peer trading.
    """
    
    def __init__(self, 
                 num_buildings: int = 10,
                 time_horizon: int = 96,
                 efficiency_charge: float = 0.95,
                 efficiency_discharge: float = 0.95):
        """
        Initialize the prosumer community optimizer.
        
        Args:
            num_buildings: Number of prosumer buildings
            time_horizon: Number of time steps (e.g., 96 for 15-min intervals over 24h)
            efficiency_charge: Battery charging efficiency
            efficiency_discharge: Battery discharging efficiency
        """
        self.num_buildings = num_buildings
        self.time_horizon = time_horizon
        self.eta_ch = efficiency_charge
        self.eta_dis = efficiency_discharge
        
        # Initialize variables
        self._setup_variables()
        
    def _setup_variables(self):
        """Setup CVXPY optimization variables."""
        # Grid imports/exports [kWh]
        self.G_down = cp.Variable((self.num_buildings, self.time_horizon), nonneg=True)  # Grid imports
        self.G_up = cp.Variable((self.num_buildings, self.time_horizon), nonneg=True)    # Total exports
        
        # Community trading [kWh]
        self.E_comm = cp.Variable((self.num_buildings, self.time_horizon), nonneg=True)  # Community exports
        
        # Battery operations [kW]
        self.B_up = cp.Variable((self.num_buildings, self.time_horizon), nonneg=True)    # Battery charge
        self.B_down = cp.Variable((self.num_buildings, self.time_horizon), nonneg=True)  # Battery discharge
        
        # Battery state of charge [kWh]
        self.SOC = cp.Variable((self.num_buildings, self.time_horizon), nonneg=True)
        
        # Flexible load served [kWh]
        self.L = cp.Variable((self.num_buildings, self.time_horizon), nonneg=True)
        
    def setup_problem(self,
                     demand: np.ndarray,
                     pv_generation: np.ndarray,
                     import_prices: np.ndarray,
                     export_prices: np.ndarray,
                     community_prices: np.ndarray,
                     battery_specs: Dict,
                     load_flexibility: Dict) -> cp.Problem:
        """
        Setup the optimization problem with constraints.
        
        Args:
            demand: Demand profiles [buildings x time_steps]
            pv_generation: PV generation profiles [buildings x time_steps]
            import_prices: Grid import prices [time_steps]
            export_prices: Grid export prices [time_steps]
            community_prices: Internal trading prices [time_steps]
            battery_specs: Battery specifications dict
            load_flexibility: Load flexibility parameters dict
            
        Returns:
            CVXPY Problem instance
        """
        constraints = []
        
        # 1. Energy balance constraint for each building and time step
        for i in range(self.num_buildings):
            for t in range(self.time_horizon):
                energy_balance = (
                    self.L[i, t] == 
                    pv_generation[i, t] + self.G_down[i, t] + self.B_down[i, t] - 
                    self.G_up[i, t] - self.B_up[i, t]
                )
                constraints.append(energy_balance)
        
        # 2. Battery dynamics and constraints
        for i in range(self.num_buildings):
            # Battery capacity limits
            constraints.extend([
                self.SOC[i, :] <= battery_specs['max_energy'][i],
                self.B_up[i, :] <= battery_specs['max_power'][i],
                self.B_down[i, :] <= battery_specs['max_power'][i]
            ])
            
            # Battery state evolution
            for t in range(self.time_horizon - 1):
                soc_evolution = (
                    self.SOC[i, t + 1] == 
                    self.SOC[i, t] + self.eta_ch * self.B_up[i, t] - self.B_down[i, t] / self.eta_dis
                )
                constraints.append(soc_evolution)
            
            # Initial and final SOC constraints
            constraints.extend([
                self.SOC[i, 0] == battery_specs['initial_soc'][i],
                self.SOC[i, -1] >= battery_specs['final_soc_min'][i]
            ])
        
        # 3. Load flexibility constraints
        for i in range(self.num_buildings):
            constraints.extend([
                self.L[i, :] >= load_flexibility['min_load'][i, :],
                self.L[i, :] <= load_flexibility['max_load'][i, :],
                cp.sum(self.L[i, :]) >= 0.9 * cp.sum(load_flexibility['min_load'][i, :]),
                cp.sum(self.L[i, :]) <= 1.1 * cp.sum(load_flexibility['max_load'][i, :])
            ])
        
        # 4. Peer-to-peer trading constraints
        for t in range(self.time_horizon):
            for i in range(self.num_buildings):
                constraints.append(self.E_comm[i, t] <= self.G_up[i, t])
            
            constraints.append(
                cp.sum(self.E_comm[:, t]) <= cp.sum(self.G_down[:, t])
            )
        
        # 5. Objective function: Minimize total community cost
        total_cost = 0
        for t in range(self.time_horizon):
            import_cost = import_prices[t] * cp.sum(self.G_down[:, t])
            community_revenue = community_prices[t] * cp.sum(self.E_comm[:, t])
            grid_export_revenue = export_prices[t] * cp.sum(self.G_up[:, t] - self.E_comm[:, t])
            total_cost += import_cost - community_revenue - grid_export_revenue
        
        objective = cp.Minimize(total_cost)
        problem = cp.Problem(objective, constraints)
        
        return problem
    
    def solve(self, problem: cp.Problem, solver: str = 'ECOS') -> Dict:
        """
        Solve the optimization problem and return results.
        
        Args:
            problem: CVXPY Problem instance
            solver: Solver to use
            
        Returns:
            Dictionary containing optimization results
        """
        try:
            problem.solve(solver=solver, verbose=False)
            
            if problem.status not in ["infeasible", "unbounded"]:
                results = {
                    'status': problem.status,
                    'objective_value': problem.value,
                    'grid_imports': self.G_down.value,
                    'grid_exports': self.G_up.value,
                    'community_trades': self.E_comm.value,
                    'battery_charge': self.B_up.value,
                    'battery_discharge': self.B_down.value,
                    'battery_soc': self.SOC.value,
                    'flexible_load': self.L.value
                }
                return results
            else:
                return {'status': problem.status, 'objective_value': None}
                
        except Exception as e:
            return {'status': 'error', 'error': str(e), 'objective_value': None}
    
    def calculate_individual_costs(self, 
                                 results: Dict,
                                 import_prices: np.ndarray,
                                 export_prices: np.ndarray,
                                 community_prices: np.ndarray) -> np.ndarray:
        """
        Calculate individual building costs from optimization results.
        
        Args:
            results: Optimization results dictionary
            import_prices: Grid import prices [time_steps]
            export_prices: Grid export prices [time_steps]
            community_prices: Internal trading prices [time_steps]
            
        Returns:
            Individual costs for each building [num_buildings]
        """
        if results['status'] == 'optimal':
            individual_costs = np.zeros(self.num_buildings)
            
            for i in range(self.num_buildings):
                # Import costs
                import_cost = np.sum(import_prices * results['grid_imports'][i, :])
                
                # Community trading revenue
                community_revenue = np.sum(community_prices * results['community_trades'][i, :])
                
                # Grid export revenue
                grid_exports = results['grid_exports'][i, :] - results['community_trades'][i, :]
                grid_export_revenue = np.sum(export_prices * grid_exports)
                
                individual_costs[i] = import_cost - community_revenue - grid_export_revenue
            
            return individual_costs
        else:
            return np.full(self.num_buildings, np.nan)