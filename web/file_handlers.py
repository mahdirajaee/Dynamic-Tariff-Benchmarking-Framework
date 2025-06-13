import os
import json
import pandas as pd
import numpy as np
from io import StringIO, BytesIO
import base64
from datetime import datetime
from pathlib import Path
import zipfile
import tempfile

from flask import send_file, make_response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch


class FileHandler:
    
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.export_dir = self.data_dir / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def parse_uploaded_file(self, contents, filename):
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(StringIO(decoded.decode('utf-8')))
                return {'type': 'csv', 'data': df.to_dict('records'), 'columns': list(df.columns)}
            elif filename.endswith('.json'):
                data = json.loads(decoded.decode('utf-8'))
                return {'type': 'json', 'data': data}
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(BytesIO(decoded))
                return {'type': 'excel', 'data': df.to_dict('records'), 'columns': list(df.columns)}
            else:
                return {'type': 'unknown', 'error': f'Unsupported file type: {filename}'}
        except Exception as e:
            return {'type': 'error', 'error': str(e)}
    
    def export_results_json(self, results, filename_prefix="simulation_results"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.json"
        filepath = self.export_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=self._json_serialize_helper)
        
        return str(filepath)
    
    def export_results_csv(self, results, filename_prefix="simulation_results"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if 'scenario_results' not in results:
            return None
        
        scenario_data = []
        for name, result in results['scenario_results'].items():
            if result.get('status') == 'success':
                row = {
                    'scenario_name': name,
                    'total_cost': result.get('total_cost', 0),
                    'fairness_cov': result.get('fairness', 0),
                    'with_p2p': result.get('with_p2p', False),
                    'self_sufficiency': result.get('energy_metrics', {}).get('self_sufficiency_ratio', 0),
                    'total_grid_imports': result.get('energy_metrics', {}).get('total_grid_imports', 0),
                    'total_community_trades': result.get('energy_metrics', {}).get('total_community_trades', 0)
                }
                scenario_data.append(row)
        
        df = pd.DataFrame(scenario_data)
        filename = f"{filename_prefix}_{timestamp}.csv"
        filepath = self.export_dir / filename
        df.to_csv(filepath, index=False)
        
        return str(filepath)
    
    def export_results_excel(self, results, filename_prefix="simulation_results"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.xlsx"
        filepath = self.export_dir / filename
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            if 'scenario_results' in results:
                scenario_data = []
                individual_costs_data = []
                
                for name, result in results['scenario_results'].items():
                    if result.get('status') == 'success':
                        row = {
                            'Scenario': name,
                            'Total Cost': result.get('total_cost', 0),
                            'Fairness (CoV)': result.get('fairness', 0),
                            'P2P Trading': result.get('with_p2p', False),
                            'Self Sufficiency': result.get('energy_metrics', {}).get('self_sufficiency_ratio', 0),
                            'Grid Imports': result.get('energy_metrics', {}).get('total_grid_imports', 0),
                            'Community Trades': result.get('energy_metrics', {}).get('total_community_trades', 0)
                        }
                        scenario_data.append(row)
                        
                        if 'individual_costs' in result:
                            for i, cost in enumerate(result['individual_costs']):
                                individual_costs_data.append({
                                    'Scenario': name,
                                    'Building': f"Building_{i+1}",
                                    'Individual_Cost': cost
                                })
                
                if scenario_data:
                    df_scenarios = pd.DataFrame(scenario_data)
                    df_scenarios.to_excel(writer, sheet_name='Scenario_Summary', index=False)
                
                if individual_costs_data:
                    df_individual = pd.DataFrame(individual_costs_data)
                    df_individual.to_excel(writer, sheet_name='Individual_Costs', index=False)
            
            if 'summary_statistics' in results:
                summary_data = []
                summary = results['summary_statistics']
                
                if 'cost_statistics' in summary:
                    for key, value in summary['cost_statistics'].items():
                        summary_data.append({'Metric': f'Cost_{key}', 'Value': value})
                
                if 'fairness_statistics' in summary:
                    for key, value in summary['fairness_statistics'].items():
                        summary_data.append({'Metric': f'Fairness_{key}', 'Value': value})
                
                if summary_data:
                    df_summary = pd.DataFrame(summary_data)
                    df_summary.to_excel(writer, sheet_name='Summary_Statistics', index=False)
        
        return str(filepath)
    
    def export_results_pdf(self, results, filename_prefix="simulation_report"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.pdf"
        filepath = self.export_dir / filename
        
        doc = SimpleDocTemplate(str(filepath), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        title = Paragraph("Dynamic Tariff Benchmarking Results", styles['Title'])
        story.append(title)
        story.append(Spacer(1, 12))
        
        subtitle = Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
        story.append(subtitle)
        story.append(Spacer(1, 24))
        
        if 'scenario_results' in results:
            section_header = Paragraph("Scenario Results Summary", styles['Heading1'])
            story.append(section_header)
            story.append(Spacer(1, 12))
            
            successful_scenarios = {k: v for k, v in results['scenario_results'].items() 
                                  if v.get('status') == 'success'}
            
            if successful_scenarios:
                summary_text = f"Total scenarios analyzed: {len(results['scenario_results'])}<br/>"
                summary_text += f"Successful scenarios: {len(successful_scenarios)}<br/>"
                
                costs = [v['total_cost'] for v in successful_scenarios.values()]
                fairness = [v['fairness'] for v in successful_scenarios.values()]
                
                summary_text += f"Average cost: {np.mean(costs):.2f} €<br/>"
                summary_text += f"Cost range: {np.min(costs):.2f} - {np.max(costs):.2f} €<br/>"
                summary_text += f"Average fairness (CoV): {np.mean(fairness):.3f}<br/>"
                
                summary_para = Paragraph(summary_text, styles['Normal'])
                story.append(summary_para)
                story.append(Spacer(1, 18))
                
                table_data = [['Scenario', 'Total Cost', 'Fairness', 'P2P']]
                for name, result in list(successful_scenarios.items())[:10]:
                    table_data.append([
                        name[:30],
                        f"{result['total_cost']:.2f}",
                        f"{result['fairness']:.3f}",
                        "Yes" if result.get('with_p2p', False) else "No"
                    ])
                
                table = Table(table_data)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), '#4472C4'),
                    ('TEXTCOLOR', (0, 0), (-1, 0), '#FFFFFF'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), '#F2F2F2'),
                    ('GRID', (0, 0), (-1, -1), 1, '#000000')
                ]))
                
                story.append(table)
        
        if 'rankings' in results and results['rankings']:
            story.append(Spacer(1, 24))
            section_header = Paragraph("Top Performing Scenarios", styles['Heading1'])
            story.append(section_header)
            story.append(Spacer(1, 12))
            
            rankings_text = ""
            for i, (name, score) in enumerate(results['rankings'][:5]):
                rankings_text += f"{i+1}. {name}: {score:.3f}<br/>"
            
            rankings_para = Paragraph(rankings_text, styles['Normal'])
            story.append(rankings_para)
        
        doc.build(story)
        return str(filepath)
    
    def create_download_package(self, results, include_options):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        package_name = f"simulation_package_{timestamp}.zip"
        package_path = self.export_dir / package_name
        
        with zipfile.ZipFile(package_path, 'w') as zipf:
            if 'raw' in include_options:
                json_path = self.export_results_json(results, "raw_results")
                zipf.write(json_path, "raw_results.json")
                os.remove(json_path)
            
            if 'summary' in include_options:
                csv_path = self.export_results_csv(results, "summary")
                if csv_path:
                    zipf.write(csv_path, "summary.csv")
                    os.remove(csv_path)
            
            if 'charts' in include_options:
                excel_path = self.export_results_excel(results, "detailed_results")
                zipf.write(excel_path, "detailed_results.xlsx")
                os.remove(excel_path)
            
            if 'config' in include_options:
                config_data = {
                    'export_timestamp': timestamp,
                    'framework_version': '1.0.0',
                    'export_options': include_options
                }
                
                config_path = self.export_dir / "config.json"
                with open(config_path, 'w') as f:
                    json.dump(config_data, f, indent=2)
                
                zipf.write(config_path, "export_config.json")
                os.remove(config_path)
        
        return str(package_path)
    
    def _json_serialize_helper(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        else:
            return str(obj)
    
    def get_export_history(self):
        history = []
        
        for file_path in self.export_dir.glob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                history.append({
                    'filename': file_path.name,
                    'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'size': f"{stat.st_size / 1024:.1f} KB",
                    'path': str(file_path)
                })
        
        return sorted(history, key=lambda x: x['date'], reverse=True)
    
    def cleanup_old_exports(self, days_old=7):
        cutoff_time = datetime.now().timestamp() - (days_old * 24 * 3600)
        
        for file_path in self.export_dir.glob("*"):
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                file_path.unlink()


def create_sample_config():
    return {
        "simulation_config": {
            "num_buildings": 10,
            "time_horizon": 96,
            "num_scenarios": 20
        },
        "tariff_config": {
            "types": ["tou", "cpp", "rtp"],
            "off_peak_price": 0.08,
            "on_peak_price": 0.25,
            "export_ratio": 0.4
        },
        "p2p_config": {
            "enabled": True,
            "trading_efficiency": 0.95,
            "community_spread": 0.5,
            "network_topology": "full"
        },
        "analysis_config": {
            "include_p2p_comparison": True,
            "train_surrogate": True,
            "sensitivity_analysis": False
        }
    }


def save_uploaded_data(file_data, data_type, building_id=None):
    data_dir = Path("data/input")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    if data_type == "load_profiles":
        filename = "load_profiles.csv"
        df = pd.DataFrame(file_data['data'])
        df.to_csv(data_dir / filename, index=False)
    
    elif data_type == "pv_profiles":
        filename = "pv_profiles.csv"
        df = pd.DataFrame(file_data['data'])
        df.to_csv(data_dir / filename, index=False)
    
    elif data_type == "battery_specs":
        filename = "battery_specs.json"
        with open(data_dir / filename, 'w') as f:
            json.dump(file_data['data'], f, indent=2)
    
    elif data_type == "load_flexibility":
        filename = "load_flexibility.json"
        with open(data_dir / filename, 'w') as f:
            json.dump(file_data['data'], f, indent=2)
    
    return str(data_dir / filename)