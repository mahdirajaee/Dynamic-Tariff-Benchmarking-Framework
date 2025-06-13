import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
from pathlib import Path
import json


class ProsumerDataLoader:
    """
    Data loader for prosumer community simulation.
    Handles load profiles, PV generation, and building specifications.
    """
    
    def __init__(self, data_dir: str = "data/input"):
        """
        Initialize data loader.
        
        Args:
            data_dir: Directory containing input data files
        """
        self.data_dir = Path(data_dir)
        
    def load_load_profiles(self, 
                          file_path: Optional[str] = None,
                          num_buildings: int = 10,
                          time_horizon: int = 96) -> np.ndarray:
        """
        Load electricity demand profiles for prosumer buildings.
        
        Args:
            file_path: Path to load profiles CSV file
            num_buildings: Number of buildings
            time_horizon: Number of time steps
            
        Returns:
            Load profiles array [buildings x time_steps] in kWh
        """
        if file_path and Path(file_path).exists():
            df = pd.read_csv(file_path)
            return df.values[:num_buildings, :time_horizon]
        else:
            # Generate synthetic load profiles if no file provided
            return self._generate_synthetic_load_profiles(num_buildings, time_horizon)
    
    def load_pv_profiles(self, 
                        file_path: Optional[str] = None,
                        num_buildings: int = 10,
                        time_horizon: int = 96) -> np.ndarray:
        """
        Load PV generation profiles for prosumer buildings.
        
        Args:
            file_path: Path to PV profiles CSV file
            num_buildings: Number of buildings
            time_horizon: Number of time steps
            
        Returns:
            PV generation profiles array [buildings x time_steps] in kWh
        """
        if file_path and Path(file_path).exists():
            df = pd.read_csv(file_path)
            return df.values[:num_buildings, :time_horizon]
        else:
            # Generate synthetic PV profiles if no file provided
            return self._generate_synthetic_pv_profiles(num_buildings, time_horizon)
    
    def load_battery_specifications(self, 
                                  file_path: Optional[str] = None,
                                  num_buildings: int = 10) -> Dict:
        """
        Load battery specifications for each building.
        
        Args:
            file_path: Path to battery specs JSON file
            num_buildings: Number of buildings
            
        Returns:
            Dictionary containing battery specifications
        """
        if file_path and Path(file_path).exists():
            with open(file_path, 'r') as f:
                specs = json.load(f)
            return specs
        else:
            # Generate default battery specifications
            return self._generate_default_battery_specs(num_buildings)
    
    def load_load_flexibility(self, 
                            file_path: Optional[str] = None,
                            num_buildings: int = 10,
                            time_horizon: int = 96) -> Dict:
        """
        Load load flexibility parameters for each building.
        
        Args:
            file_path: Path to load flexibility JSON file
            num_buildings: Number of buildings
            time_horizon: Number of time steps
            
        Returns:
            Dictionary containing load flexibility bounds
        """
        if file_path and Path(file_path).exists():
            with open(file_path, 'r') as f:
                flexibility = json.load(f)
            return flexibility
        else:
            # Generate default load flexibility
            return self._generate_default_load_flexibility(num_buildings, time_horizon)
    
    def _generate_synthetic_load_profiles(self, 
                                        num_buildings: int, 
                                        time_horizon: int) -> np.ndarray:
        """Generate synthetic load profiles with realistic patterns."""
        np.random.seed(42)  # For reproducibility
        
        # Create 24-hour pattern (assuming 15-min intervals)
        hours = np.arange(0, 24, 0.25)
        
        # Base load pattern (higher in evening, lower at night)
        base_pattern = (
            3.0 +  # Base load
            2.0 * np.sin(2 * np.pi * (hours - 6) / 24) +  # Daily cycle
            1.5 * np.sin(2 * np.pi * (hours - 18) / 12) +  # Evening peak
            0.5 * np.random.randn(len(hours))  # Random noise
        )
        base_pattern = np.maximum(base_pattern, 0.5)  # Minimum load
        
        # Repeat pattern for multiple days if needed
        if time_horizon > len(base_pattern):
            repeats = int(np.ceil(time_horizon / len(base_pattern)))
            base_pattern = np.tile(base_pattern, repeats)
        
        base_pattern = base_pattern[:time_horizon]
        
        # Create variations for different buildings
        load_profiles = np.zeros((num_buildings, time_horizon))
        for i in range(num_buildings):
            # Add building-specific variations
            scale_factor = 0.8 + 0.4 * np.random.rand()  # 0.8 to 1.2
            phase_shift = np.random.randint(0, 4)  # 0 to 1 hour shift
            
            shifted_pattern = np.roll(base_pattern, phase_shift)
            load_profiles[i, :] = scale_factor * shifted_pattern
            
            # Add random variations
            load_profiles[i, :] += 0.2 * np.random.randn(time_horizon)
            load_profiles[i, :] = np.maximum(load_profiles[i, :], 0.1)
        
        return load_profiles
    
    def _generate_synthetic_pv_profiles(self, 
                                      num_buildings: int, 
                                      time_horizon: int) -> np.ndarray:
        """Generate synthetic PV generation profiles."""
        np.random.seed(43)  # Different seed for PV
        
        # Create 24-hour PV pattern (assuming 15-min intervals)
        hours = np.arange(0, 24, 0.25)
        
        # PV generation pattern (peak at noon, zero at night)
        pv_pattern = np.zeros_like(hours)
        for i, hour in enumerate(hours):
            if 6 <= hour <= 18:  # Daylight hours
                # Bell curve centered at noon
                pv_pattern[i] = 5.0 * np.exp(-0.5 * ((hour - 12) / 3) ** 2)
            else:
                pv_pattern[i] = 0.0
        
        # Add weather variations
        pv_pattern *= (0.7 + 0.3 * np.random.rand(len(hours)))
        
        # Repeat pattern for multiple days if needed
        if time_horizon > len(pv_pattern):
            repeats = int(np.ceil(time_horizon / len(pv_pattern)))
            pv_pattern = np.tile(pv_pattern, repeats)
        
        pv_pattern = pv_pattern[:time_horizon]
        
        # Create variations for different buildings
        pv_profiles = np.zeros((num_buildings, time_horizon))
        for i in range(num_buildings):
            # Different PV system sizes
            capacity_factor = 0.5 + 0.5 * np.random.rand()  # 0.5 to 1.0
            pv_profiles[i, :] = capacity_factor * pv_pattern
            
            # Add small random variations for weather/shading
            pv_profiles[i, :] *= (0.9 + 0.2 * np.random.rand(time_horizon))
            pv_profiles[i, :] = np.maximum(pv_profiles[i, :], 0.0)
        
        return pv_profiles
    
    def _generate_default_battery_specs(self, num_buildings: int) -> Dict:
        """Generate default battery specifications."""
        np.random.seed(44)
        
        specs = {
            'max_energy': [],  # kWh
            'max_power': [],   # kW
            'initial_soc': [], # kWh
            'final_soc_min': [] # kWh
        }
        
        for i in range(num_buildings):
            # Battery capacity between 10-20 kWh
            max_energy = 10 + 10 * np.random.rand()
            max_power = max_energy * 0.5  # C-rate of 0.5
            
            specs['max_energy'].append(max_energy)
            specs['max_power'].append(max_power)
            specs['initial_soc'].append(max_energy * 0.5)  # Start at 50%
            specs['final_soc_min'].append(max_energy * 0.2)  # End with at least 20%
        
        return specs
    
    def _generate_default_load_flexibility(self, 
                                         num_buildings: int, 
                                         time_horizon: int) -> Dict:
        """Generate default load flexibility parameters."""
        np.random.seed(45)
        
        # Generate base load profiles
        base_loads = self._generate_synthetic_load_profiles(num_buildings, time_horizon)
        
        flexibility = {
            'min_load': [],
            'max_load': []
        }
        
        for i in range(num_buildings):
            # Allow ±20% flexibility around base load
            min_load = 0.8 * base_loads[i, :]
            max_load = 1.2 * base_loads[i, :]
            
            flexibility['min_load'].append(min_load)
            flexibility['max_load'].append(max_load)
        
        # Convert to numpy arrays
        flexibility['min_load'] = np.array(flexibility['min_load'])
        flexibility['max_load'] = np.array(flexibility['max_load'])
        
        return flexibility
    
    def create_sample_data_files(self, output_dir: str = "data/input"):
        """
        Create sample data files for testing.
        
        Args:
            output_dir: Directory to save sample files
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate and save sample load profiles
        load_profiles = self._generate_synthetic_load_profiles(10, 96)
        pd.DataFrame(load_profiles).to_csv(output_path / "load_profiles.csv", index=False)
        
        # Generate and save sample PV profiles
        pv_profiles = self._generate_synthetic_pv_profiles(10, 96)
        pd.DataFrame(pv_profiles).to_csv(output_path / "pv_profiles.csv", index=False)
        
        # Generate and save battery specifications
        battery_specs = self._generate_default_battery_specs(10)
        with open(output_path / "battery_specs.json", 'w') as f:
            json.dump(battery_specs, f, indent=2)
        
        # Generate and save load flexibility
        load_flexibility = self._generate_default_load_flexibility(10, 96)
        # Convert numpy arrays to lists for JSON serialization
        flexibility_json = {
            'min_load': load_flexibility['min_load'].tolist(),
            'max_load': load_flexibility['max_load'].tolist()
        }
        with open(output_path / "load_flexibility.json", 'w') as f:
            json.dump(flexibility_json, f, indent=2)