# Web Interface User Guide

## Quick Start

### 1. Installation
```bash
# Install required dependencies
pip install -r requirements.txt

# Start the web interface
python run_web_interface.py
```

The interface will automatically open in your browser at `http://localhost:8050`

### 2. Alternative Launch Methods
```bash
# Development mode with debug features
python run_web_interface.py --dev

# Custom port and host
python run_web_interface.py --port 9000 --host 0.0.0.0

# Check dependencies only
python run_web_interface.py --check-deps
```

## Interface Overview

### Main Navigation
- **Configuration**: Set up simulation parameters
- **Results Overview**: View summary of completed simulations  
- **Interactive Analysis**: Explore results with dynamic charts
- **Scenario Details**: Deep dive into individual scenarios
- **Export & Download**: Export results in various formats

## Configuration Tab

### Basic Settings
- **Number of Buildings**: 2-50 prosumer buildings (default: 10)
- **Time Horizon**: 24-672 time intervals (default: 96 = 24 hours in 15-min intervals)
- **Simulation Scenarios**: 5-100 tariff scenarios to evaluate (default: 20)
- **Rapid Evaluations**: 0-10,000 surrogate model evaluations (default: 1000)

### Analysis Options
- **P2P Trading Comparison**: Compare scenarios with and without peer-to-peer trading
- **Train Surrogate Model**: Train XGBoost model for rapid evaluations
- **Sensitivity Analysis**: Analyze parameter sensitivity
- **Export Detailed Results**: Include individual building data in exports

### Tariff Configuration
- **Tariff Types**: Select which tariff structures to include
  - Time-of-Use (ToU)
  - Critical Peak Pricing (CPP)  
  - Real-Time Pricing (RTP)
  - Emergency Demand Response (EDR)
- **Price Ranges**: Set off-peak and on-peak price bounds
- **Export Ratio**: Ratio of export to import prices (0-1)
- **Volatility**: Price volatility for RTP tariffs

### P2P Trading Settings
- **Trading Efficiency**: Energy transfer efficiency (50-100%)
- **Community Spread**: Price spread between grid and community rates (0-1)
- **Network Topology**: 
  - Full Network: All buildings can trade with each other
  - Local Network: Only neighboring buildings
  - Hub Network: Centralized trading point

### Advanced Options
- **Battery Configuration**: Capacity ranges and efficiency settings
- **Solver Settings**: Optimization solver configuration
- **Timeout Settings**: Maximum solve time limits

## Running Simulations

### 1. Start Simulation
1. Configure parameters in the Configuration tab
2. Click "Start Simulation" 
3. Monitor progress in the status panel or progress modal
4. Simulation typically takes 30 seconds to 5 minutes depending on settings

### 2. Progress Tracking
- Real-time progress bar showing completion percentage
- Status messages indicating current task:
  - Initializing framework
  - Running benchmark scenarios  
  - Training surrogate model
  - Performing rapid evaluations
  - Running sensitivity analysis

### 3. Stopping Simulations
- Click "Stop" button to halt running simulation
- Progress will be saved up to the stopping point

## Results Analysis

### Results Overview Tab
- **Summary Cards**: Key metrics at a glance
  - Number of successful scenarios
  - P2P vs non-P2P scenario counts
  - Average cost and fairness
- **Top Scenarios**: Ranking of best-performing configurations
- **Performance Summary**: Cost vs fairness scatter plot

### Interactive Analysis Tab
- **Analysis Type**: Choose what to analyze
  - Cost Comparison
  - Fairness Analysis
  - Energy Flows
  - P2P Benefits
- **Chart Type**: Select visualization style
  - Bar Chart
  - Scatter Plot
  - Box Plot
  - Heatmap
- **Filters**: Include/exclude scenario types

### Scenario Details Tab
- **Detailed View**: Individual scenario examination
- **Energy Flows**: Battery, grid, and trading patterns
- **Cost Breakdown**: Detailed cost analysis per building
- **Optimization Results**: Raw solver outputs

## Key Metrics Explained

### Cost Metrics
- **Total Cost**: Sum of all building electricity costs (€)
- **Individual Costs**: Cost per building
- **Average Cost**: Mean cost across all buildings

### Fairness Metrics
- **Coefficient of Variation (CoV)**: Standard deviation / mean of individual costs
  - Lower values = more fair distribution
  - 0 = perfectly equal costs
- **Gini Coefficient**: Inequality measure (0-1 scale)
- **Jain Fairness Index**: Fairness measure (0-1 scale, 1 = perfectly fair)

### Energy Metrics
- **Self-Sufficiency Ratio**: Local energy use / total demand
- **PV Utilization**: (PV generation - grid exports) / PV generation
- **Community Trade Ratio**: Community trades / total exports

## Export & Download

### Export Formats
- **JSON**: Raw simulation data and results
- **CSV**: Summary table of all scenarios
- **Excel**: Multi-sheet workbook with detailed breakdowns
- **PDF**: Formatted report with charts and summary

### Export Options
- **Raw Results**: Complete simulation output
- **Summary Statistics**: Aggregated metrics only
- **Charts**: Include visualization data
- **Configuration**: Simulation settings used

### Download Package
- Creates ZIP file containing selected export formats
- Includes metadata about export settings
- Automatic file naming with timestamps

## Advanced Features

### File Upload
- Upload custom prosumer data files
- Supported formats: CSV, JSON, Excel
- Files types:
  - Load profiles (electricity demand)
  - PV generation profiles
  - Battery specifications
  - Load flexibility parameters

### API Access
The web interface exposes REST APIs for integration:
- `GET /api/status` - Simulation status
- `POST /api/start_simulation` - Start new simulation
- `POST /api/stop_simulation` - Stop running simulation
- `GET /api/results` - Get simulation results
- `GET /api/download_results` - Download results file

### Batch Processing
For large-scale studies:
1. Configure base scenario in web interface
2. Use API endpoints to programmatically run multiple configurations
3. Aggregate results using the analysis tools

## Performance Tips

### For Faster Simulations
- Reduce number of buildings (< 10)
- Reduce time horizon (< 96 intervals)
- Limit scenarios (< 20)
- Disable surrogate model training for quick tests

### For Comprehensive Analysis
- Use 10+ buildings for realistic communities
- Include 24-hour time horizon (96 intervals)
- Run 50+ scenarios for robust statistics
- Enable all analysis options

### Memory Management
- Large simulations (50+ scenarios, 20+ buildings) may require 4+ GB RAM
- Clear browser cache if interface becomes slow
- Restart application for memory-intensive runs

## Troubleshooting

### Common Issues

**Simulation Fails to Start**
- Check that all dependencies are installed
- Verify input data is properly formatted
- Ensure sufficient memory is available

**Slow Performance** 
- Reduce simulation size
- Close other browser tabs
- Restart the application

**Missing Dependencies**
```bash
python run_web_interface.py --check-deps
pip install -r requirements.txt
```

**Port Already in Use**
```bash
python run_web_interface.py --port 9000
```

### Browser Compatibility
- Recommended: Chrome, Firefox, Safari (latest versions)
- JavaScript must be enabled
- Minimum screen resolution: 1024x768

### Data Limits
- Maximum buildings: 50 (for performance)
- Maximum time horizon: 672 intervals (1 week)
- Maximum scenarios: 100 per simulation
- File uploads: < 50 MB per file

## Support

For technical issues or questions:
1. Check this guide first
2. Review the main README.md
3. Check console output for error messages
4. Report issues with full error logs and configuration details