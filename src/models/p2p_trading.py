import numpy as np
from typing import Dict, List, Tuple, Optional
import pandas as pd


class P2PTradingMechanism:
    """
    Peer-to-peer trading mechanism for prosumer community.
    Handles energy trading between prosumers with different pricing strategies.
    """
    
    def __init__(self, 
                 num_buildings: int = 10,
                 trading_efficiency: float = 0.95,
                 max_trading_distance: float = 1.0):
        """
        Initialize P2P trading mechanism.
        
        Args:
            num_buildings: Number of buildings in the community
            trading_efficiency: Efficiency of peer-to-peer energy transfer
            max_trading_distance: Maximum normalized distance for trading
        """
        self.num_buildings = num_buildings
        self.trading_efficiency = trading_efficiency
        self.max_trading_distance = max_trading_distance
        
        # Initialize trading matrix (symmetric)
        self.trading_allowed = np.ones((num_buildings, num_buildings))
        np.fill_diagonal(self.trading_allowed, 0)  # No self-trading
    
    def set_trading_network(self, adjacency_matrix: np.ndarray):
        """
        Set the trading network topology.
        
        Args:
            adjacency_matrix: Binary matrix indicating allowed trading pairs
        """
        if adjacency_matrix.shape != (self.num_buildings, self.num_buildings):
            raise ValueError("Adjacency matrix must match number of buildings")
        
        self.trading_allowed = adjacency_matrix.copy()
        np.fill_diagonal(self.trading_allowed, 0)  # Ensure no self-trading
    
    def calculate_trading_potential(self,
                                  generation: np.ndarray,
                                  demand: np.ndarray,
                                  time_step: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate trading potential for each building at a given time step.
        
        Args:
            generation: PV generation [buildings]
            demand: Electricity demand [buildings]
            time_step: Current time step
            
        Returns:
            Tuple of (surplus, deficit) arrays
        """
        net_generation = generation - demand
        
        surplus = np.maximum(net_generation, 0)  # Excess energy available for export
        deficit = np.maximum(-net_generation, 0)  # Energy needed from imports
        
        return surplus, deficit
    
    def optimize_trading_flows(self,
                              surplus: np.ndarray,
                              deficit: np.ndarray,
                              community_price: float,
                              grid_export_price: float,
                              grid_import_price: float) -> Dict:
        """
        Optimize peer-to-peer trading flows for a single time step.
        
        Args:
            surplus: Surplus energy by building [buildings]
            deficit: Deficit energy by building [buildings]
            community_price: Internal trading price
            grid_export_price: Grid export price
            grid_import_price: Grid import price
            
        Returns:
            Dictionary with trading results
        """
        # Initialize trading matrix
        trading_matrix = np.zeros((self.num_buildings, self.num_buildings))
        
        # Calculate trading benefits
        export_benefit = community_price - grid_export_price
        import_benefit = grid_import_price - community_price
        
        # Only trade if beneficial for both parties
        if export_benefit > 0 and import_benefit > 0:
            # Simple greedy allocation
            surplus_remaining = surplus.copy()
            deficit_remaining = deficit.copy()
            
            # Sort by trading priority (highest surplus first)
            surplus_order = np.argsort(-surplus_remaining)
            
            for i in surplus_order:
                if surplus_remaining[i] <= 0:
                    continue
                
                # Find buildings with deficit that can trade with i
                available_traders = np.where(
                    (deficit_remaining > 0) & 
                    (self.trading_allowed[i, :] == 1)
                )[0]
                
                if len(available_traders) == 0:
                    continue
                
                # Sort by highest deficit first
                deficit_order = available_traders[np.argsort(-deficit_remaining[available_traders])]
                
                for j in deficit_order:
                    if surplus_remaining[i] <= 0:
                        break
                    
                    # Calculate tradeable amount
                    trade_amount = min(surplus_remaining[i], deficit_remaining[j])
                    trade_amount *= self.trading_efficiency  # Account for losses
                    
                    if trade_amount > 0.001:  # Minimum trade threshold
                        trading_matrix[i, j] = trade_amount
                        surplus_remaining[i] -= trade_amount / self.trading_efficiency
                        deficit_remaining[j] -= trade_amount
        
        # Calculate post-trading grid interactions
        grid_exports = np.maximum(surplus - np.sum(trading_matrix, axis=1), 0)
        grid_imports = np.maximum(deficit - np.sum(trading_matrix, axis=0), 0)
        
        results = {
            'trading_matrix': trading_matrix,
            'community_exports': np.sum(trading_matrix, axis=1),
            'community_imports': np.sum(trading_matrix, axis=0),
            'grid_exports': grid_exports,
            'grid_imports': grid_imports,
            'total_community_traded': np.sum(trading_matrix),
            'trading_efficiency_loss': np.sum(trading_matrix) * (1 - self.trading_efficiency)
        }
        
        return results
    
    def calculate_trading_costs(self,
                               trading_results: Dict,
                               community_price: float,
                               grid_export_price: float,
                               grid_import_price: float) -> Dict:
        """
        Calculate individual costs/revenues from trading.
        
        Args:
            trading_results: Results from optimize_trading_flows
            community_price: Internal trading price
            grid_export_price: Grid export price
            grid_import_price: Grid import price
            
        Returns:
            Dictionary with cost breakdown by building
        """
        costs = {
            'community_export_revenue': np.zeros(self.num_buildings),
            'community_import_cost': np.zeros(self.num_buildings),
            'grid_export_revenue': np.zeros(self.num_buildings),
            'grid_import_cost': np.zeros(self.num_buildings),
            'net_cost': np.zeros(self.num_buildings)
        }
        
        # Community trading revenues and costs
        costs['community_export_revenue'] = (
            trading_results['community_exports'] * community_price
        )
        costs['community_import_cost'] = (
            trading_results['community_imports'] * community_price
        )
        
        # Grid trading revenues and costs
        costs['grid_export_revenue'] = (
            trading_results['grid_exports'] * grid_export_price
        )
        costs['grid_import_cost'] = (
            trading_results['grid_imports'] * grid_import_price
        )
        
        # Net cost per building (positive = cost, negative = revenue)
        costs['net_cost'] = (
            costs['community_import_cost'] + costs['grid_import_cost'] -
            costs['community_export_revenue'] - costs['grid_export_revenue']
        )
        
        return costs
    
    def simulate_trading_period(self,
                               generation_profiles: np.ndarray,
                               demand_profiles: np.ndarray,
                               import_prices: np.ndarray,
                               export_prices: np.ndarray,
                               community_prices: np.ndarray) -> Dict:
        """
        Simulate peer-to-peer trading over a full time period.
        
        Args:
            generation_profiles: PV generation [buildings x time_steps]
            demand_profiles: Demand profiles [buildings x time_steps]
            import_prices: Grid import prices [time_steps]
            export_prices: Grid export prices [time_steps]
            community_prices: Community trading prices [time_steps]
            
        Returns:
            Dictionary with comprehensive trading results
        """
        time_steps = generation_profiles.shape[1]
        
        # Initialize result arrays
        trading_matrices = np.zeros((time_steps, self.num_buildings, self.num_buildings))
        community_exports = np.zeros((self.num_buildings, time_steps))
        community_imports = np.zeros((self.num_buildings, time_steps))
        grid_exports = np.zeros((self.num_buildings, time_steps))
        grid_imports = np.zeros((self.num_buildings, time_steps))
        
        total_costs = np.zeros((self.num_buildings, time_steps))
        
        # Process each time step
        for t in range(time_steps):
            # Calculate surplus and deficit
            surplus, deficit = self.calculate_trading_potential(
                generation_profiles[:, t],
                demand_profiles[:, t],
                t
            )
            
            # Optimize trading flows
            trading_results = self.optimize_trading_flows(
                surplus, deficit,
                community_prices[t],
                export_prices[t],
                import_prices[t]
            )
            
            # Store results
            trading_matrices[t] = trading_results['trading_matrix']
            community_exports[:, t] = trading_results['community_exports']
            community_imports[:, t] = trading_results['community_imports']
            grid_exports[:, t] = trading_results['grid_exports']
            grid_imports[:, t] = trading_results['grid_imports']
            
            # Calculate costs
            costs = self.calculate_trading_costs(
                trading_results,
                community_prices[t],
                export_prices[t],
                import_prices[t]
            )
            
            total_costs[:, t] = costs['net_cost']
        
        # Aggregate results
        results = {
            'trading_matrices': trading_matrices,
            'community_exports': community_exports,
            'community_imports': community_imports,
            'grid_exports': grid_exports,
            'grid_imports': grid_imports,
            'individual_costs': total_costs,
            'total_community_cost': np.sum(total_costs),
            'total_energy_traded': np.sum(trading_matrices),
            'self_sufficiency_ratio': self._calculate_self_sufficiency(
                generation_profiles, demand_profiles, grid_imports
            ),
            'trading_volumes': {
                'community_traded': np.sum(trading_matrices, axis=(1, 2)),
                'grid_imported': np.sum(grid_imports, axis=0),
                'grid_exported': np.sum(grid_exports, axis=0)
            }
        }
        
        return results
    
    def _calculate_self_sufficiency(self,
                                   generation: np.ndarray,
                                   demand: np.ndarray,
                                   grid_imports: np.ndarray) -> float:
        """Calculate community self-sufficiency ratio."""
        total_demand = np.sum(demand)
        total_grid_imports = np.sum(grid_imports)
        
        if total_demand > 0:
            return 1.0 - (total_grid_imports / total_demand)
        else:
            return 1.0
    
    def analyze_trading_benefits(self,
                                results_with_trading: Dict,
                                results_without_trading: Dict) -> Dict:
        """
        Analyze benefits of peer-to-peer trading compared to grid-only scenario.
        
        Args:
            results_with_trading: Trading simulation results with P2P
            results_without_trading: Trading simulation results without P2P
            
        Returns:
            Dictionary with benefit analysis
        """
        benefits = {
            'cost_savings': {
                'total': (results_without_trading['total_community_cost'] - 
                         results_with_trading['total_community_cost']),
                'individual': (results_without_trading['individual_costs'] - 
                              results_with_trading['individual_costs'])
            },
            'energy_metrics': {
                'community_energy_traded': results_with_trading['total_energy_traded'],
                'grid_dependency_reduction': (
                    np.sum(results_without_trading['grid_imports']) - 
                    np.sum(results_with_trading['grid_imports'])
                ),
                'export_reduction': (
                    np.sum(results_without_trading['grid_exports']) - 
                    np.sum(results_with_trading['grid_exports'])
                )
            },
            'self_sufficiency_improvement': (
                results_with_trading['self_sufficiency_ratio'] - 
                results_without_trading['self_sufficiency_ratio']
            )
        }
        
        return benefits