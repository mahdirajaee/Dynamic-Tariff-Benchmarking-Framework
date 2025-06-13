#!/usr/bin/env python3

import sys
import time
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

from src.simulation_orchestrator import SimulationOrchestrator


def main():
    parser = argparse.ArgumentParser(description="Benchmark Dynamic Tariffs for Prosumer Communities")
    parser.add_argument("--buildings", type=int, default=10, help="Number of prosumer buildings")
    parser.add_argument("--time-horizon", type=int, default=96, help="Number of time steps")
    parser.add_argument("--scenarios", type=int, default=20, help="Number of tariff scenarios")
    parser.add_argument("--output", type=str, default="benchmark_results.json", help="Output file name")
    parser.add_argument("--train-surrogate", action="store_true", help="Train surrogate model")
    parser.add_argument("--rapid-eval", type=int, default=0, help="Number of rapid evaluations using surrogate")
    parser.add_argument("--sensitivity", action="store_true", help="Run sensitivity analysis")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        print(f"Initializing simulation with {args.buildings} buildings and {args.time_horizon} time steps...")
    
    orchestrator = SimulationOrchestrator(
        num_buildings=args.buildings,
        time_horizon=args.time_horizon
    )
    
    start_time = time.time()
    
    if args.verbose:
        print("Loading data and initializing components...")
    
    orchestrator.initialize()
    
    if args.verbose:
        print(f"Running benchmark with {args.scenarios} scenarios...")
    
    benchmark_results = orchestrator.benchmark_tariff_scenarios(
        num_scenarios=args.scenarios,
        include_p2p_comparison=True
    )
    
    if benchmark_results['successful_scenarios'] == 0:
        print("ERROR: No scenarios completed successfully!")
        return 1
    
    if args.verbose:
        print(f"Benchmark completed: {benchmark_results['successful_scenarios']}/{benchmark_results['total_scenarios']} scenarios successful")
    
    if args.train_surrogate:
        if args.verbose:
            print("Training surrogate model...")
        
        surrogate_results = orchestrator.train_surrogate_model()
        
        if surrogate_results['status'] == 'success':
            if args.verbose:
                print(f"Surrogate model trained with {surrogate_results['training_samples']} samples")
                if 'model_performance' in surrogate_results:
                    cost_r2 = surrogate_results['model_performance'].get('cost_metrics', {}).get('test_r2', 'N/A')
                    fairness_r2 = surrogate_results['model_performance'].get('fairness_metrics', {}).get('test_r2', 'N/A')
                    print(f"Model performance - Cost R²: {cost_r2:.3f}, Fairness R²: {fairness_r2:.3f}")
        else:
            print(f"WARNING: Surrogate model training failed: {surrogate_results.get('error', 'Unknown error')}")
    
    if args.rapid_eval > 0:
        if args.verbose:
            print(f"Running {args.rapid_eval} rapid evaluations...")
        
        rapid_results = orchestrator.rapid_scenario_evaluation(args.rapid_eval)
        
        if 'best_cost_scenarios' in rapid_results:
            best_cost = rapid_results['best_cost_scenarios'][0]['predicted_cost']
            best_fairness = min(rapid_results['best_fairness_scenarios'], key=lambda x: x['predicted_fairness'])['predicted_fairness']
            
            if args.verbose:
                print(f"Rapid evaluation completed - Best predicted cost: {best_cost:.2f}, Best fairness: {best_fairness:.3f}")
    
    if args.sensitivity:
        if args.verbose:
            print("Running sensitivity analysis...")
        
        sensitivity_ranges = {
            'export_ratio': [0.2, 0.3, 0.4, 0.5, 0.6],
            'community_spread': [0.3, 0.4, 0.5, 0.6, 0.7]
        }
        
        sensitivity_results = orchestrator.sensitivity_analysis(sensitivity_ranges)
        
        if args.verbose:
            for param, results in sensitivity_results.items():
                cost_corr = results.get('cost_correlation', 'N/A')
                fairness_corr = results.get('fairness_correlation', 'N/A')
                print(f"Sensitivity {param} - Cost correlation: {cost_corr:.3f}, Fairness correlation: {fairness_corr:.3f}")
    
    if args.verbose:
        print("Generating summary statistics...")
    
    summary_stats = orchestrator.get_summary_statistics()
    
    if 'error' not in summary_stats:
        if args.verbose:
            print(f"Summary Statistics:")
            print(f"  Total scenarios: {summary_stats['total_scenarios']}")
            print(f"  Mean cost: {summary_stats['cost_statistics']['mean']:.2f}")
            print(f"  Cost range: {summary_stats['cost_statistics']['range']:.2f}")
            print(f"  Mean fairness (CoV): {summary_stats['fairness_statistics']['mean']:.3f}")
            
            if 'p2p_analysis' in summary_stats:
                print(f"  P2P average savings: {summary_stats['p2p_analysis']['savings_percentage']:.1f}%")
    
    if args.verbose:
        print(f"Saving results to {args.output}...")
    
    orchestrator.save_results(args.output)
    
    execution_time = time.time() - start_time
    
    print(f"Benchmark completed in {execution_time:.1f} seconds")
    
    rankings = benchmark_results.get('rankings', [])
    if rankings:
        print(f"Best scenario: {rankings[0][0]} (score: {rankings[0][1]:.3f})")
        if len(rankings) > 1:
            print(f"Worst scenario: {rankings[-1][0]} (score: {rankings[-1][1]:.3f})")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())