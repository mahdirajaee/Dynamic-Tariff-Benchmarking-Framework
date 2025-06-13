#!/usr/bin/env python3

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "src"))

from src.simulation_orchestrator import SimulationOrchestrator
import numpy as np


def main():
    
    orchestrator = SimulationOrchestrator(
        num_buildings=10,
        time_horizon=96
    )
    
    print("Initializing simulation...")
    orchestrator.initialize()
    
    print("Running single scenario test...")
    
    import_prices = np.array([0.08, 0.12, 0.20] * 32)
    export_prices = import_prices * 0.4
    community_prices = export_prices + 0.5 * (import_prices - export_prices)
    
    result = orchestrator.run_single_scenario(
        import_prices=import_prices,
        export_prices=export_prices, 
        community_prices=community_prices,
        with_p2p=True,
        scenario_name="test_scenario"
    )
    
    if result['status'] == 'success':
        print(f"✓ Single scenario completed successfully")
        print(f"  Total cost: {result['total_cost']:.2f}")
        print(f"  Fairness (CoV): {result['fairness']:.3f}")
        print(f"  Self-sufficiency: {result['energy_metrics']['self_sufficiency_ratio']:.2f}")
    else:
        print(f"✗ Single scenario failed: {result.get('error', 'Unknown error')}")
        return 1
    
    print("\nRunning mini benchmark (5 scenarios)...")
    
    benchmark_results = orchestrator.benchmark_tariff_scenarios(
        num_scenarios=5,
        include_p2p_comparison=True
    )
    
    if benchmark_results['successful_scenarios'] > 0:
        print(f"✓ Benchmark completed: {benchmark_results['successful_scenarios']}/{benchmark_results['total_scenarios']} scenarios")
        
        rankings = benchmark_results.get('rankings', [])
        if rankings:
            print(f"  Best scenario: {rankings[0][0]} (score: {rankings[0][1]:.3f})")
    else:
        print(f"✗ Benchmark failed")
        return 1
    
    print("\nTraining surrogate model...")
    
    surrogate_results = orchestrator.train_surrogate_model()
    
    if surrogate_results['status'] == 'success':
        print(f"✓ Surrogate model trained with {surrogate_results['training_samples']} samples")
        
        if 'model_performance' in surrogate_results:
            cost_metrics = surrogate_results['model_performance'].get('cost_metrics', {})
            fairness_metrics = surrogate_results['model_performance'].get('fairness_metrics', {})
            
            cost_r2 = cost_metrics.get('test_r2', 'N/A')
            fairness_r2 = fairness_metrics.get('test_r2', 'N/A')
            
            print(f"  Cost model R²: {cost_r2:.3f}")
            print(f"  Fairness model R²: {fairness_r2:.3f}")
    else:
        print(f"✗ Surrogate training failed: {surrogate_results.get('error', 'Unknown error')}")
    
    print("\nRunning rapid evaluation (100 scenarios)...")
    
    rapid_results = orchestrator.rapid_scenario_evaluation(100)
    
    if 'best_cost_scenarios' in rapid_results:
        best_cost = rapid_results['best_cost_scenarios'][0]['predicted_cost']
        best_fairness_scenario = min(rapid_results['best_fairness_scenarios'], key=lambda x: x['predicted_fairness'])
        best_fairness = best_fairness_scenario['predicted_fairness']
        
        print(f"✓ Rapid evaluation completed")
        print(f"  Best predicted cost: {best_cost:.2f}")
        print(f"  Best predicted fairness: {best_fairness:.3f}")
    else:
        print(f"✗ Rapid evaluation failed")
    
    print("\nGenerating summary statistics...")
    
    summary = orchestrator.get_summary_statistics()
    
    if 'error' not in summary:
        print(f"✓ Summary generated")
        print(f"  Total scenarios analyzed: {summary['total_scenarios']}")
        print(f"  Mean cost: {summary['cost_statistics']['mean']:.2f}")
        print(f"  Mean fairness: {summary['fairness_statistics']['mean']:.3f}")
        
        if 'p2p_analysis' in summary:
            print(f"  P2P savings: {summary['p2p_analysis']['savings_percentage']:.1f}%")
    else:
        print(f"✗ Summary failed: {summary['error']}")
    
    print("\nSaving results...")
    orchestrator.save_results("example_results.json")
    print("✓ Results saved to data/output/example_results.json")
    
    print("\n🎉 Example completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())