import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


class ResultsVisualizer:
    
    def __init__(self, style: str = 'seaborn-v0_8', figsize: tuple = (12, 8)):
        plt.style.use(style)
        self.figsize = figsize
        sns.set_palette("husl")
    
    def plot_scenario_comparison(self, 
                               scenarios_results: Dict[str, Dict],
                               metric: str = 'total_cost',
                               save_path: Optional[str] = None) -> plt.Figure:
        
        scenario_names = []
        values = []
        p2p_status = []
        
        for name, result in scenarios_results.items():
            if result['status'] == 'success':
                scenario_names.append(name.replace('_with_p2p', '').replace('_without_p2p', ''))
                values.append(result[metric])
                p2p_status.append('With P2P' if result.get('with_p2p', False) else 'Without P2P')
        
        df = pd.DataFrame({
            'Scenario': scenario_names,
            'Value': values,
            'P2P': p2p_status
        })
        
        fig, ax = plt.subplots(figsize=self.figsize)
        
        if 'P2P' in df.columns and len(df['P2P'].unique()) > 1:
            sns.barplot(data=df, x='Scenario', y='Value', hue='P2P', ax=ax)
            ax.legend(title='Trading Mode')
        else:
            sns.barplot(data=df, x='Scenario', y='Value', ax=ax)
        
        ax.set_title(f'Scenario Comparison: {metric.replace("_", " ").title()}')
        ax.set_xlabel('Tariff Scenario')
        ax.set_ylabel(metric.replace("_", " ").title())
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def plot_fairness_vs_cost(self,
                             scenarios_results: Dict[str, Dict],
                             save_path: Optional[str] = None) -> plt.Figure:
        
        costs = []
        fairness = []
        scenario_names = []
        p2p_status = []
        
        for name, result in scenarios_results.items():
            if result['status'] == 'success':
                costs.append(result['total_cost'])
                fairness.append(result['fairness'])
                scenario_names.append(name)
                p2p_status.append('With P2P' if result.get('with_p2p', False) else 'Without P2P')
        
        fig, ax = plt.subplots(figsize=self.figsize)
        
        df = pd.DataFrame({
            'Cost': costs,
            'Fairness (CoV)': fairness,
            'P2P': p2p_status,
            'Scenario': scenario_names
        })
        
        if len(df['P2P'].unique()) > 1:
            for p2p_type in df['P2P'].unique():
                subset = df[df['P2P'] == p2p_type]
                ax.scatter(subset['Cost'], subset['Fairness (CoV)'], 
                          label=p2p_type, alpha=0.7, s=60)
        else:
            ax.scatter(df['Cost'], df['Fairness (CoV)'], alpha=0.7, s=60)
        
        ax.set_xlabel('Total Community Cost')
        ax.set_ylabel('Fairness (Coefficient of Variation)')
        ax.set_title('Cost vs Fairness Trade-off')
        
        if len(df['P2P'].unique()) > 1:
            ax.legend()
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def plot_individual_costs(self,
                            scenarios_results: Dict[str, Dict],
                            scenario_names: Optional[List[str]] = None,
                            save_path: Optional[str] = None) -> plt.Figure:
        
        if scenario_names is None:
            scenario_names = [name for name, result in scenarios_results.items() 
                            if result['status'] == 'success'][:5]
        
        fig, axes = plt.subplots(1, len(scenario_names), figsize=(4*len(scenario_names), 6))
        if len(scenario_names) == 1:
            axes = [axes]
        
        for idx, scenario_name in enumerate(scenario_names):
            if scenario_name in scenarios_results:
                result = scenarios_results[scenario_name]
                if result['status'] == 'success':
                    individual_costs = result['individual_costs']
                    building_ids = list(range(1, len(individual_costs) + 1))
                    
                    axes[idx].bar(building_ids, individual_costs)
                    axes[idx].set_title(f'{scenario_name}')
                    axes[idx].set_xlabel('Building ID')
                    axes[idx].set_ylabel('Individual Cost')
                    axes[idx].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def plot_energy_flows(self,
                         optimization_results: Dict,
                         time_horizon: int = 96,
                         building_id: int = 0,
                         save_path: Optional[str] = None) -> plt.Figure:
        
        if optimization_results['grid_imports'] is None:
            raise ValueError("No optimization results available")
        
        time_steps = list(range(time_horizon))
        
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))
        
        ax1.plot(time_steps, optimization_results['grid_imports'][building_id], 
                label='Grid Imports', linewidth=2)
        ax1.plot(time_steps, optimization_results['grid_exports'][building_id], 
                label='Grid Exports', linewidth=2)
        ax1.set_title(f'Grid Interactions - Building {building_id + 1}')
        ax1.set_ylabel('Energy (kWh)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        ax2.plot(time_steps, optimization_results['battery_charge'][building_id], 
                label='Battery Charge', linewidth=2)
        ax2.plot(time_steps, optimization_results['battery_discharge'][building_id], 
                label='Battery Discharge', linewidth=2)
        ax2.set_title(f'Battery Operations - Building {building_id + 1}')
        ax2.set_ylabel('Power (kW)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        ax3.plot(time_steps, optimization_results['battery_soc'][building_id], 
                linewidth=2, color='green')
        ax3.set_title(f'Battery State of Charge - Building {building_id + 1}')
        ax3.set_xlabel('Time Step')
        ax3.set_ylabel('SOC (kWh)')
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def plot_feature_importance(self,
                              feature_importance: Dict[str, Dict],
                              top_n: int = 15,
                              save_path: Optional[str] = None) -> plt.Figure:
        
        cost_importance = feature_importance.get('cost_importance', {})
        fairness_importance = feature_importance.get('fairness_importance', {})
        
        if not cost_importance and not fairness_importance:
            raise ValueError("No feature importance data available")
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
        
        if cost_importance:
            features = list(cost_importance.keys())[:top_n]
            importance = [cost_importance[f] for f in features]
            
            y_pos = np.arange(len(features))
            ax1.barh(y_pos, importance)
            ax1.set_yticks(y_pos)
            ax1.set_yticklabels(features)
            ax1.set_xlabel('Importance')
            ax1.set_title('Feature Importance - Cost Model')
            ax1.grid(True, alpha=0.3)
        
        if fairness_importance:
            features = list(fairness_importance.keys())[:top_n]
            importance = [fairness_importance[f] for f in features]
            
            y_pos = np.arange(len(features))
            ax2.barh(y_pos, importance)
            ax2.set_yticks(y_pos)
            ax2.set_yticklabels(features)
            ax2.set_xlabel('Importance')
            ax2.set_title('Feature Importance - Fairness Model')
            ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig
    
    def create_interactive_dashboard(self,
                                   scenarios_results: Dict[str, Dict],
                                   save_path: Optional[str] = None) -> go.Figure:
        
        data = []
        for name, result in scenarios_results.items():
            if result['status'] == 'success':
                data.append({
                    'Scenario': name,
                    'Total Cost': result['total_cost'],
                    'Fairness (CoV)': result['fairness'],
                    'P2P Trading': 'Yes' if result.get('with_p2p', False) else 'No',
                    'Self Sufficiency': result.get('energy_metrics', {}).get('self_sufficiency_ratio', 0),
                    'Community Trades': result.get('energy_metrics', {}).get('total_community_trades', 0)
                })
        
        df = pd.DataFrame(data)
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Cost vs Fairness', 'Self Sufficiency Distribution', 
                          'Cost by P2P Status', 'Community Trading Volume'),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )
        
        scatter = px.scatter(df, x='Total Cost', y='Fairness (CoV)', 
                           color='P2P Trading', hover_data=['Scenario'])
        for trace in scatter.data:
            fig.add_trace(trace, row=1, col=1)
        
        hist = px.histogram(df, x='Self Sufficiency', nbins=10)
        for trace in hist.data:
            fig.add_trace(trace, row=1, col=2)
        
        box = px.box(df, x='P2P Trading', y='Total Cost')
        for trace in box.data:
            fig.add_trace(trace, row=2, col=1)
        
        bar = px.bar(df, x='Scenario', y='Community Trades')
        for trace in bar.data:
            fig.add_trace(trace, row=2, col=2)
        
        fig.update_layout(height=800, showlegend=True, 
                         title_text="Prosumer Community Tariff Analysis Dashboard")
        
        if save_path:
            fig.write_html(save_path)
        
        return fig
    
    def plot_sensitivity_analysis(self,
                                sensitivity_results: Dict[str, Any],
                                save_path: Optional[str] = None) -> plt.Figure:
        
        num_params = len(sensitivity_results)
        fig, axes = plt.subplots(2, num_params, figsize=(5*num_params, 10))
        
        if num_params == 1:
            axes = axes.reshape(-1, 1)
        
        for idx, (param_name, results) in enumerate(sensitivity_results.items()):
            param_values = results['parameter_values']
            cost_sensitivity = results['cost_sensitivity']
            fairness_sensitivity = results['fairness_sensitivity']
            
            axes[0, idx].plot(param_values, cost_sensitivity, 'o-', linewidth=2, markersize=6)
            axes[0, idx].set_title(f'Cost Sensitivity - {param_name}')
            axes[0, idx].set_xlabel(param_name.replace('_', ' ').title())
            axes[0, idx].set_ylabel('Total Cost')
            axes[0, idx].grid(True, alpha=0.3)
            
            axes[1, idx].plot(param_values, fairness_sensitivity, 'o-', 
                            linewidth=2, markersize=6, color='red')
            axes[1, idx].set_title(f'Fairness Sensitivity - {param_name}')
            axes[1, idx].set_xlabel(param_name.replace('_', ' ').title())
            axes[1, idx].set_ylabel('Fairness (CoV)')
            axes[1, idx].grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        return fig