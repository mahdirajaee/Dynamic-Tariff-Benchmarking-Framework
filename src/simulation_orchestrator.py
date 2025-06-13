import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import time
from pathlib import Path
import json

from .data.data_loader import ProsumerDataLoader
from .tariffs.dynamic_tariffs import TariffManager
from .optimization.prosumer_optimizer import ProsumerCommunityOptimizer
from .models.p2p_trading import P2PTradingMechanism
from .models.surrogate_model import TariffSurrogateModel
from .analysis.fairness_analyzer import FairnessAnalyzer


class SimulationOrchestrator:
    
    def __init__(self, 
                 num_buildings: int = 10,
                 time_horizon: int = 96,
                 data_dir: str = "data"):
        
        self.num_buildings = num_buildings
        self.time_horizon = time_horizon
        self.data_dir = Path(data_dir)
        
        self.data_loader = ProsumerDataLoader(str(self.data_dir / "input"))
        self.tariff_manager = TariffManager()
        self.optimizer = ProsumerCommunityOptimizer(num_buildings, time_horizon)
        self.p2p_trading = P2PTradingMechanism(num_buildings)
        self.surrogate_model = TariffSurrogateModel(time_horizon, num_buildings)
        self.fairness_analyzer = FairnessAnalyzer(num_buildings)
        
        self.results = {}
        self.is_initialized = False
        
    def initialize(self):
        
        self.load_profiles = self.data_loader.load_load_profiles(
            num_buildings=self.num_buildings,
            time_horizon=self.time_horizon
        )
        
        self.pv_profiles = self.data_loader.load_pv_profiles(
            num_buildings=self.num_buildings,
            time_horizon=self.time_horizon
        )
        
        self.battery_specs = self.data_loader.load_battery_specifications(
            num_buildings=self.num_buildings
        )
        
        self.load_flexibility = self.data_loader.load_load_flexibility(
            num_buildings=self.num_buildings,
            time_horizon=self.time_horizon
        )
        
        self.tariff_manager.create_default_tariffs()
        
        self.is_initialized = True
    
    def run_single_scenario(self,
                          import_prices: np.ndarray,
                          export_prices: np.ndarray,
                          community_prices: np.ndarray,
                          with_p2p: bool = True,
                          scenario_name: str = "default") -> Dict[str, Any]:
        
        if not self.is_initialized:
            self.initialize()
        
        try:
            problem = self.optimizer.setup_problem(
                demand=self.load_profiles,
                pv_generation=self.pv_profiles,
                import_prices=import_prices,
                export_prices=export_prices,
                community_prices=community_prices if with_p2p else export_prices,
                battery_specs=self.battery_specs,
                load_flexibility=self.load_flexibility
            )
            
            optimization_results = self.optimizer.solve(problem)
            
            if optimization_results['status'] != 'optimal':
                return {
                    'scenario_name': scenario_name,
                    'status': 'failed',
                    'error': f"Optimization failed: {optimization_results['status']}"
                }
            
            individual_costs = self.optimizer.calculate_individual_costs(
                optimization_results,
                import_prices,
                export_prices,
                community_prices if with_p2p else export_prices
            )
            
            fairness_metrics = self.fairness_analyzer.analyze_fairness_metrics(individual_costs)
            
            energy_metrics = self._calculate_energy_metrics(optimization_results)
            
            results = {
                'scenario_name': scenario_name,
                'status': 'success',
                'with_p2p': with_p2p,
                'total_cost': fairness_metrics['total_cost'],
                'individual_costs': individual_costs.tolist(),
                'fairness': fairness_metrics['coefficient_of_variation'],
                'fairness_metrics': fairness_metrics,
                'energy_metrics': energy_metrics,
                'optimization_results': {
                    'objective_value': optimization_results['objective_value'],
                    'grid_imports': optimization_results['grid_imports'].tolist() if optimization_results['grid_imports'] is not None else None,
                    'grid_exports': optimization_results['grid_exports'].tolist() if optimization_results['grid_exports'] is not None else None,
                    'community_trades': optimization_results['community_trades'].tolist() if optimization_results['community_trades'] is not None else None
                },
                'prices': {
                    'import': import_prices.tolist(),
                    'export': export_prices.tolist(), 
                    'community': community_prices.tolist()
                }
            }
            
            return results
            
        except Exception as e:
            return {
                'scenario_name': scenario_name,
                'status': 'error',
                'error': str(e)
            }
    
    def _calculate_energy_metrics(self, optimization_results: Dict) -> Dict[str, float]:
        
        if optimization_results['grid_imports'] is None:
            return {}
        
        total_grid_imports = np.sum(optimization_results['grid_imports'])
        total_grid_exports = np.sum(optimization_results['grid_exports'])
        total_community_trades = np.sum(optimization_results['community_trades'])
        total_demand = np.sum(self.load_flexibility['min_load'])
        total_pv_generation = np.sum(self.pv_profiles)
        
        metrics = {
            'total_grid_imports': total_grid_imports,
            'total_grid_exports': total_grid_exports,
            'total_community_trades': total_community_trades,
            'total_demand': total_demand,
            'total_pv_generation': total_pv_generation,
            'self_sufficiency_ratio': 1 - (total_grid_imports / total_demand) if total_demand > 0 else 0,
            'pv_utilization_ratio': (total_pv_generation - total_grid_exports) / total_pv_generation if total_pv_generation > 0 else 0,
            'community_trade_ratio': total_community_trades / total_grid_exports if total_grid_exports > 0 else 0
        }
        
        return metrics
    
    def benchmark_tariff_scenarios(self, 
                                 num_scenarios: int = 20,
                                 include_p2p_comparison: bool = True) -> Dict[str, Any]:
        
        if not self.is_initialized:
            self.initialize()
        
        scenario_results = {}
        
        tariff_scenarios = self.tariff_manager.create_tariff_scenarios(
            time_horizon=self.time_horizon,
            num_scenarios=num_scenarios
        )
        
        for scenario_name, import_prices in tariff_scenarios.items():
            export_prices = self.tariff_manager.get_export_prices(import_prices)
            community_prices = self.tariff_manager.get_community_prices(import_prices, export_prices)
            
            if include_p2p_comparison:
                with_p2p = self.run_single_scenario(
                    import_prices, export_prices, community_prices,
                    with_p2p=True, scenario_name=f"{scenario_name}_with_p2p"
                )
                scenario_results[f"{scenario_name}_with_p2p"] = with_p2p
                
                without_p2p = self.run_single_scenario(
                    import_prices, export_prices, export_prices,
                    with_p2p=False, scenario_name=f"{scenario_name}_without_p2p"
                )
                scenario_results[f"{scenario_name}_without_p2p"] = without_p2p
            else:
                result = self.run_single_scenario(
                    import_prices, export_prices, community_prices,
                    with_p2p=True, scenario_name=scenario_name
                )
                scenario_results[scenario_name] = result
        
        successful_results = {k: v for k, v in scenario_results.items() if v['status'] == 'success'}
        
        if successful_results:
            fairness_metrics = {k: v['fairness_metrics'] for k, v in successful_results.items()}
            rankings = self.fairness_analyzer.rank_scenarios(fairness_metrics)
            
            summary = self.fairness_analyzer.generate_summary_report(
                fairness_metrics,
                baseline_scenario=list(successful_results.keys())[0] if successful_results else None
            )
            
            benchmark_results = {
                'scenario_results': scenario_results,
                'successful_scenarios': len(successful_results),
                'total_scenarios': len(scenario_results),
                'rankings': rankings,
                'summary': summary,
                'execution_timestamp': time.time()
            }
        else:
            benchmark_results = {
                'scenario_results': scenario_results,
                'successful_scenarios': 0,
                'total_scenarios': len(scenario_results),
                'error': 'No scenarios completed successfully'
            }
        
        self.results['benchmark'] = benchmark_results
        return benchmark_results
    
    def train_surrogate_model(self, training_scenarios: Optional[Dict] = None) -> Dict[str, Any]:
        
        if training_scenarios is None:
            if 'benchmark' not in self.results:
                self.benchmark_tariff_scenarios(num_scenarios=50)
            training_scenarios = self.results['benchmark']['scenario_results']
        
        successful_scenarios = {k: v for k, v in training_scenarios.items() if v['status'] == 'success'}
        
        if len(successful_scenarios) < 10:
            return {'status': 'failed', 'error': 'Insufficient training data'}
        
        try:
            X, y_cost, y_fairness = self.surrogate_model.prepare_training_data(successful_scenarios)
            
            training_results = self.surrogate_model.train_models(X, y_cost, y_fairness)
            
            return {
                'status': 'success',
                'training_samples': len(successful_scenarios),
                'model_performance': training_results,
                'feature_importance': training_results.get('feature_importance', {})
            }
            
        except Exception as e:
            return {'status': 'failed', 'error': str(e)}
    
    def rapid_scenario_evaluation(self, 
                                num_evaluations: int = 1000) -> Dict[str, Any]:
        
        if not self.surrogate_model.is_fitted:
            training_result = self.train_surrogate_model()
            if training_result['status'] != 'success':
                return training_result
        
        evaluation_results = []
        
        for i in range(num_evaluations):
            import_prices = 0.08 + 0.15 * np.random.rand(self.time_horizon)
            export_prices = import_prices * (0.3 + 0.3 * np.random.rand())
            community_prices = export_prices + (import_prices - export_prices) * np.random.rand()
            
            prediction = self.surrogate_model.predict(import_prices, export_prices, community_prices)
            
            evaluation_results.append({
                'evaluation_id': i,
                'predicted_cost': prediction['predicted_cost'],
                'predicted_fairness': prediction['predicted_fairness'],
                'import_prices': import_prices.tolist(),
                'export_prices': export_prices.tolist(),
                'community_prices': community_prices.tolist()
            })
        
        sorted_by_cost = sorted(evaluation_results, key=lambda x: x['predicted_cost'])
        sorted_by_fairness = sorted(evaluation_results, key=lambda x: x['predicted_fairness'])
        
        return {
            'total_evaluations': num_evaluations,
            'best_cost_scenarios': sorted_by_cost[:10],
            'best_fairness_scenarios': sorted_by_fairness[:10],
            'all_evaluations': evaluation_results
        }
    
    def sensitivity_analysis(self, 
                           parameter_ranges: Dict[str, List[float]]) -> Dict[str, Any]:
        
        base_import_prices = self.tariff_manager.get_tariff('Time-of-Use').get_prices(self.time_horizon)
        base_export_prices = self.tariff_manager.get_export_prices(base_import_prices)
        base_community_prices = self.tariff_manager.get_community_prices(base_import_prices, base_export_prices)
        
        sensitivity_results = {}
        
        for param_name, param_values in parameter_ranges.items():
            param_results = {}
            
            for param_value in param_values:
                if param_name == 'export_ratio':
                    export_prices = self.tariff_manager.get_export_prices(base_import_prices, param_value)
                    community_prices = base_community_prices
                elif param_name == 'community_spread':
                    export_prices = base_export_prices
                    community_prices = self.tariff_manager.get_community_prices(
                        base_import_prices, base_export_prices, param_value
                    )
                else:
                    continue
                
                result = self.run_single_scenario(
                    base_import_prices, export_prices, community_prices,
                    scenario_name=f"{param_name}_{param_value}"
                )
                
                if result['status'] == 'success':
                    param_results[f"{param_name}_{param_value}"] = result['fairness_metrics']
            
            if param_results:
                sensitivity_data = self.fairness_analyzer.sensitivity_analysis(
                    param_results, {param_name: param_values}, param_name
                )
                sensitivity_results[param_name] = sensitivity_data
        
        return sensitivity_results
    
    def save_results(self, filepath: str):
        output_path = self.data_dir / "output" / filepath
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.fairness_analyzer.export_results(self.results, str(output_path))
    
    def load_results(self, filepath: str):
        input_path = self.data_dir / "output" / filepath
        self.results = self.fairness_analyzer.load_results(str(input_path))
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        
        if 'benchmark' not in self.results:
            return {'error': 'No benchmark results available'}
        
        successful_results = {
            k: v for k, v in self.results['benchmark']['scenario_results'].items() 
            if v['status'] == 'success'
        }
        
        if not successful_results:
            return {'error': 'No successful scenarios'}
        
        costs = [result['total_cost'] for result in successful_results.values()]
        fairness_scores = [result['fairness'] for result in successful_results.values()]
        
        p2p_scenarios = {k: v for k, v in successful_results.items() if v.get('with_p2p', False)}
        no_p2p_scenarios = {k: v for k, v in successful_results.items() if not v.get('with_p2p', True)}
        
        summary = {
            'total_scenarios': len(successful_results),
            'cost_statistics': {
                'mean': np.mean(costs),
                'std': np.std(costs),
                'min': np.min(costs),
                'max': np.max(costs),
                'range': np.max(costs) - np.min(costs)
            },
            'fairness_statistics': {
                'mean': np.mean(fairness_scores),
                'std': np.std(fairness_scores),
                'min': np.min(fairness_scores),
                'max': np.max(fairness_scores)
            }
        }
        
        if p2p_scenarios and no_p2p_scenarios:
            p2p_costs = [result['total_cost'] for result in p2p_scenarios.values()]
            no_p2p_costs = [result['total_cost'] for result in no_p2p_scenarios.values()]
            
            summary['p2p_analysis'] = {
                'p2p_mean_cost': np.mean(p2p_costs),
                'no_p2p_mean_cost': np.mean(no_p2p_costs),
                'average_savings': np.mean(no_p2p_costs) - np.mean(p2p_costs),
                'savings_percentage': ((np.mean(no_p2p_costs) - np.mean(p2p_costs)) / np.mean(no_p2p_costs)) * 100
            }
        
        return summary