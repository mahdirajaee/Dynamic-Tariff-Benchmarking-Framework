# Dynamic Tariff Benchmarking Framework for Prosumer Communities

A comprehensive simulation framework for evaluating dynamic electricity tariffs and peer-to-peer trading in prosumer communities with rooftop PV and battery storage.

## Overview

This framework implements a data-driven approach to benchmark different tariff structures (ToU, CPP, RTP, EDR) combined with peer-to-peer trading mechanisms. It uses mixed-integer linear programming (MILP) optimization and XGBoost surrogate modeling for rapid scenario evaluation.

## Key Features

- **🌐 Interactive Web Interface**: User-friendly dashboard with real-time progress tracking
- **⚡ Multi-tariff Support**: Time-of-Use, Critical Peak Pricing, Real-Time Pricing, Emergency Demand Response
- **🔄 P2P Trading**: Community energy sharing with configurable pricing mechanisms  
- **🎯 MILP Optimization**: Joint optimization of load shifting, battery dispatch, and trading decisions
- **🤖 Surrogate Modeling**: XGBoost-based rapid scenario evaluation
- **⚖️ Fairness Analysis**: Multiple fairness metrics including Coefficient of Variation, Gini coefficient
- **📊 Comprehensive Benchmarking**: Automated scenario generation and ranking
- **📈 Interactive Visualizations**: Dynamic charts and analysis tools
- **💾 Multi-format Export**: JSON, CSV, Excel, PDF report generation

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Web Interface (Recommended)

```bash
# Start the interactive web interface
python run_web_interface.py

# Development mode with debug features
python run_web_interface.py --dev

# Custom port
python run_web_interface.py --port 9000
```

The web interface will open automatically at `http://localhost:8050` and provides:
- Interactive configuration panels
- Real-time simulation progress tracking
- Dynamic result visualization and analysis
- Export functionality for multiple formats

### Command Line Usage

```bash
# Run example simulation
python example_usage.py

# Run full benchmark
python run_benchmark.py --scenarios 20 --verbose

# Run with surrogate model training
python run_benchmark.py --scenarios 30 --train-surrogate --rapid-eval 1000
```

### Programmatic Usage

```python
from src.simulation_orchestrator import SimulationOrchestrator

orchestrator = SimulationOrchestrator(num_buildings=10, time_horizon=96)
orchestrator.initialize()

# Run benchmark
results = orchestrator.benchmark_tariff_scenarios(num_scenarios=20)

# Train surrogate model
surrogate_results = orchestrator.train_surrogate_model()

# Rapid evaluation
rapid_results = orchestrator.rapid_scenario_evaluation(1000)
```

## Framework Architecture

### Core Components

1. **Data Loader** (`src/data/data_loader.py`)
   - Load/generate prosumer profiles, battery specs, flexibility parameters

2. **Tariff Manager** (`src/tariffs/dynamic_tariffs.py`)
   - Implement ToU, CPP, RTP, EDR tariff structures
   - Generate scenario variations

3. **Optimization Engine** (`src/optimization/prosumer_optimizer.py`)
   - MILP formulation for community energy management
   - Battery dynamics, load flexibility, P2P trading constraints

4. **P2P Trading** (`src/models/p2p_trading.py`)
   - Community energy sharing mechanism
   - Trading flow optimization

5. **Surrogate Model** (`src/models/surrogate_model.py`)
   - XGBoost models for cost and fairness prediction
   - Feature engineering from price profiles

6. **Fairness Analyzer** (`src/analysis/fairness_analyzer.py`)
   - Multiple fairness metrics calculation
   - Scenario comparison and ranking

7. **Simulation Orchestrator** (`src/simulation_orchestrator.py`)
   - Coordinate all components
   - Manage benchmark execution

## Input Data

The framework expects the following input files in `data/input/`:

- `load_profiles.csv`: Electricity demand profiles [buildings × time_steps]
- `pv_profiles.csv`: PV generation profiles [buildings × time_steps]  
- `battery_specs.json`: Battery specifications (capacity, power, SOC limits)
- `load_flexibility.json`: Load flexibility bounds (min/max load per time step)

Sample data is automatically generated if files are not present.

## Configuration

### Default Parameters

- **Buildings**: 10 prosumer buildings
- **Time Horizon**: 96 time steps (15-min intervals, 24 hours)
- **Battery Efficiency**: 95% charge/discharge
- **P2P Trading Efficiency**: 95%

### Tariff Parameters

- **ToU**: Off-peak (€0.08), Mid-peak (€0.12), On-peak (€0.20)
- **CPP**: Critical events at €0.40 during peak hours
- **RTP**: Variable pricing with daily patterns and volatility
- **EDR**: Emergency events at €0.80 with 5-10% probability

## Output and Results

Results are saved to `data/output/` in JSON format containing:

- Individual building costs and fairness metrics
- Energy flow optimization results  
- Scenario rankings and comparisons
- Surrogate model performance metrics
- Sensitivity analysis results

### Key Metrics

- **Cost**: Total community electricity cost (€)
- **Fairness**: Coefficient of Variation of individual costs
- **Self-Sufficiency**: Ratio of local energy use to total demand
- **P2P Benefits**: Cost savings from community trading

## Advanced Features

### Sensitivity Analysis

```python
sensitivity_ranges = {
    'export_ratio': [0.2, 0.3, 0.4, 0.5, 0.6],
    'community_spread': [0.3, 0.4, 0.5, 0.6, 0.7]
}
results = orchestrator.sensitivity_analysis(sensitivity_ranges)
```

### Visualization

```python
from src.utils.visualization import ResultsVisualizer

visualizer = ResultsVisualizer()
visualizer.plot_scenario_comparison(results)
visualizer.plot_fairness_vs_cost(results)
visualizer.create_interactive_dashboard(results)
```

### Custom Scenarios

```python
import numpy as np

# Define custom price profile
import_prices = np.array([0.08, 0.12, 0.20] * 32)  
export_prices = import_prices * 0.4
community_prices = export_prices + 0.5 * (import_prices - export_prices)

result = orchestrator.run_single_scenario(
    import_prices, export_prices, community_prices,
    with_p2p=True, scenario_name="custom_scenario"
)
```

## Command Line Options

```bash
python run_benchmark.py --help

Options:
  --buildings INT       Number of prosumer buildings (default: 10)
  --time-horizon INT    Number of time steps (default: 96)  
  --scenarios INT       Number of tariff scenarios (default: 20)
  --output STR          Output file name (default: benchmark_results.json)
  --train-surrogate     Train surrogate model
  --rapid-eval INT      Number of rapid evaluations (default: 0)
  --sensitivity         Run sensitivity analysis
  --verbose             Verbose output
```

## Requirements

- Python 3.8+
- NumPy, Pandas, SciPy
- CVXPY (optimization)
- XGBoost (surrogate modeling)
- Matplotlib, Seaborn, Plotly (visualization)
- scikit-learn, PyYAML, tqdm

## License

MIT License

## Citation

If you use this framework in your research, please cite:

```
@misc{prosumer_tariff_framework,
  title={Dynamic Tariff Benchmarking Framework for Prosumer Communities},
  author={Your Name},
  year={2024},
  url={https://github.com/your-repo}
}
```