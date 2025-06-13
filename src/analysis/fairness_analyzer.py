import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from scipy import stats
import json


class FairnessAnalyzer:
    
    def __init__(self, num_buildings: int = 10):
        self.num_buildings = num_buildings
        
    def calculate_coefficient_of_variation(self, costs: np.ndarray) -> float:
        if np.std(costs) == 0:
            return 0.0
        return np.std(costs) / np.mean(costs)
    
    def calculate_gini_coefficient(self, costs: np.ndarray) -> float:
        costs_sorted = np.sort(costs)
        n = len(costs_sorted)
        index = np.arange(1, n + 1)
        return (2 * np.sum(index * costs_sorted)) / (n * np.sum(costs_sorted)) - (n + 1) / n
    
    def calculate_jain_fairness_index(self, costs: np.ndarray) -> float:
        sum_costs = np.sum(costs)
        sum_squared_costs = np.sum(costs ** 2)
        n = len(costs)
        
        if sum_squared_costs == 0:
            return 1.0
        return (sum_costs ** 2) / (n * sum_squared_costs)
    
    def calculate_range_ratio(self, costs: np.ndarray) -> float:
        if np.min(costs) == 0:
            return np.inf
        return np.max(costs) / np.min(costs)
    
    def calculate_theil_index(self, costs: np.ndarray) -> float:
        mean_cost = np.mean(costs)
        if mean_cost == 0:
            return 0.0
        
        ratios = costs / mean_cost
        positive_ratios = ratios[ratios > 0]
        if len(positive_ratios) == 0:
            return 0.0
        
        return np.mean(positive_ratios * np.log(positive_ratios))
    
    def analyze_fairness_metrics(self, individual_costs: np.ndarray) -> Dict[str, float]:
        metrics = {
            'coefficient_of_variation': self.calculate_coefficient_of_variation(individual_costs),
            'gini_coefficient': self.calculate_gini_coefficient(individual_costs),
            'jain_fairness_index': self.calculate_jain_fairness_index(individual_costs),
            'range_ratio': self.calculate_range_ratio(individual_costs),
            'theil_index': self.calculate_theil_index(individual_costs),
            'total_cost': np.sum(individual_costs),
            'mean_cost': np.mean(individual_costs),
            'std_cost': np.std(individual_costs),
            'min_cost': np.min(individual_costs),
            'max_cost': np.max(individual_costs)
        }
        return metrics
    
    def compare_scenarios(self, 
                         baseline_costs: np.ndarray,
                         scenario_costs: np.ndarray) -> Dict[str, Any]:
        
        baseline_metrics = self.analyze_fairness_metrics(baseline_costs)
        scenario_metrics = self.analyze_fairness_metrics(scenario_costs)
        
        cost_savings = baseline_costs - scenario_costs
        relative_savings = cost_savings / baseline_costs * 100
        
        comparison = {
            'baseline_metrics': baseline_metrics,
            'scenario_metrics': scenario_metrics,
            'absolute_savings': {
                'total': np.sum(cost_savings),
                'mean': np.mean(cost_savings),
                'individual': cost_savings.tolist()
            },
            'relative_savings': {
                'mean_percent': np.mean(relative_savings),
                'individual_percent': relative_savings.tolist()
            },
            'fairness_improvement': {
                'cov_change': scenario_metrics['coefficient_of_variation'] - baseline_metrics['coefficient_of_variation'],
                'gini_change': scenario_metrics['gini_coefficient'] - baseline_metrics['gini_coefficient'],
                'jain_change': scenario_metrics['jain_fairness_index'] - baseline_metrics['jain_fairness_index']
            }
        }
        
        return comparison
    
    def rank_scenarios(self, 
                      scenarios_results: Dict[str, Dict],
                      weight_cost: float = 0.7,
                      weight_fairness: float = 0.3) -> List[Tuple[str, float]]:
        
        scores = []
        
        costs = [result['total_cost'] for result in scenarios_results.values()]
        fairness_scores = [1 - result['coefficient_of_variation'] for result in scenarios_results.values()]
        
        min_cost, max_cost = min(costs), max(costs)
        min_fairness, max_fairness = min(fairness_scores), max(fairness_scores)
        
        for scenario_name, results in scenarios_results.items():
            normalized_cost = 1 - (results['total_cost'] - min_cost) / (max_cost - min_cost + 1e-10)
            normalized_fairness = (1 - results['coefficient_of_variation'] - min_fairness) / (max_fairness - min_fairness + 1e-10)
            
            composite_score = weight_cost * normalized_cost + weight_fairness * normalized_fairness
            scores.append((scenario_name, composite_score))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    def statistical_significance_test(self, 
                                    costs1: np.ndarray, 
                                    costs2: np.ndarray) -> Dict[str, float]:
        
        t_stat, p_value_ttest = stats.ttest_ind(costs1, costs2)
        u_stat, p_value_mannwhitney = stats.mannwhitneyu(costs1, costs2, alternative='two-sided')
        
        return {
            'ttest_statistic': t_stat,
            'ttest_p_value': p_value_ttest,
            'mannwhitney_statistic': u_stat,
            'mannwhitney_p_value': p_value_mannwhitney,
            'effect_size_cohens_d': (np.mean(costs1) - np.mean(costs2)) / np.sqrt((np.var(costs1) + np.var(costs2)) / 2)
        }
    
    def generate_summary_report(self, 
                              scenarios_results: Dict[str, Dict],
                              baseline_scenario: str = None) -> Dict[str, Any]:
        
        rankings = self.rank_scenarios(scenarios_results)
        
        summary = {
            'num_scenarios': len(scenarios_results),
            'best_scenario': rankings[0][0],
            'best_score': rankings[0][1],
            'worst_scenario': rankings[-1][0],
            'worst_score': rankings[-1][1],
            'rankings': rankings
        }
        
        if baseline_scenario and baseline_scenario in scenarios_results:
            if 'individual_costs' in scenarios_results[baseline_scenario]:
                baseline_costs = np.array(scenarios_results[baseline_scenario]['individual_costs'])
            else:
                baseline_costs = None
            
            if baseline_costs is not None:
                comparisons = {}
                for scenario_name, results in scenarios_results.items():
                    if scenario_name != baseline_scenario and 'individual_costs' in results:
                        scenario_costs = np.array(results['individual_costs'])
                        comparison = self.compare_scenarios(baseline_costs, scenario_costs)
                        comparisons[scenario_name] = comparison
                
                summary['baseline_comparisons'] = comparisons
        
        summary['scenario_details'] = scenarios_results
        
        return summary
    
    def export_results(self, results: Dict[str, Any], filepath: str):
        
        def convert_numpy(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            return obj
        
        def recursive_convert(obj):
            if isinstance(obj, dict):
                return {k: recursive_convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [recursive_convert(item) for item in obj]
            else:
                return convert_numpy(obj)
        
        serializable_results = recursive_convert(results)
        
        with open(filepath, 'w') as f:
            json.dump(serializable_results, f, indent=2)
    
    def load_results(self, filepath: str) -> Dict[str, Any]:
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def create_fairness_dataframe(self, scenarios_results: Dict[str, Dict]) -> pd.DataFrame:
        
        rows = []
        for scenario_name, results in scenarios_results.items():
            row = {
                'scenario': scenario_name,
                'total_cost': results['total_cost'],
                'mean_cost': results['mean_cost'],
                'std_cost': results['std_cost'],
                'coefficient_of_variation': results['coefficient_of_variation'],
                'gini_coefficient': results['gini_coefficient'],
                'jain_fairness_index': results['jain_fairness_index'],
                'range_ratio': results['range_ratio'],
                'theil_index': results['theil_index']
            }
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def sensitivity_analysis(self, 
                           base_results: Dict[str, Dict],
                           parameter_variations: Dict[str, List[float]],
                           parameter_name: str) -> Dict[str, Any]:
        
        sensitivity_data = {
            'parameter_name': parameter_name,
            'parameter_values': parameter_variations[parameter_name],
            'cost_sensitivity': [],
            'fairness_sensitivity': []
        }
        
        for param_value in parameter_variations[parameter_name]:
            param_key = f"{parameter_name}_{param_value}"
            if param_key in base_results:
                sensitivity_data['cost_sensitivity'].append(base_results[param_key]['total_cost'])
                sensitivity_data['fairness_sensitivity'].append(base_results[param_key]['coefficient_of_variation'])
        
        if len(sensitivity_data['cost_sensitivity']) > 1:
            cost_correlation = np.corrcoef(
                sensitivity_data['parameter_values'][:len(sensitivity_data['cost_sensitivity'])],
                sensitivity_data['cost_sensitivity']
            )[0, 1]
            
            fairness_correlation = np.corrcoef(
                sensitivity_data['parameter_values'][:len(sensitivity_data['fairness_sensitivity'])],
                sensitivity_data['fairness_sensitivity']
            )[0, 1]
            
            sensitivity_data['cost_correlation'] = cost_correlation
            sensitivity_data['fairness_correlation'] = fairness_correlation
        
        return sensitivity_data