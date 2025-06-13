import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import json


class BaseTariff(ABC):
    """Abstract base class for all tariff types."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def get_prices(self, time_horizon: int, **kwargs) -> np.ndarray:
        """
        Get tariff prices for given time horizon.
        
        Args:
            time_horizon: Number of time steps
            **kwargs: Additional parameters specific to tariff type
            
        Returns:
            Array of prices [time_steps]
        """
        pass


class TimeOfUseTariff(BaseTariff):
    """Time-of-Use (ToU) tariff with predefined price levels."""
    
    def __init__(self, 
                 off_peak_price: float = 0.10,
                 mid_peak_price: float = 0.15,
                 on_peak_price: float = 0.25,
                 off_peak_hours: List[int] = None,
                 mid_peak_hours: List[int] = None,
                 on_peak_hours: List[int] = None):
        """
        Initialize ToU tariff.
        
        Args:
            off_peak_price: Off-peak price in €/kWh
            mid_peak_price: Mid-peak price in €/kWh
            on_peak_price: On-peak price in €/kWh
            off_peak_hours: List of off-peak hours (0-23)
            mid_peak_hours: List of mid-peak hours (0-23)
            on_peak_hours: List of on-peak hours (0-23)
        """
        super().__init__("Time-of-Use")
        self.off_peak_price = off_peak_price
        self.mid_peak_price = mid_peak_price
        self.on_peak_price = on_peak_price
        
        # Default time periods if not specified
        self.off_peak_hours = off_peak_hours or list(range(0, 7)) + list(range(23, 24))
        self.mid_peak_hours = mid_peak_hours or list(range(7, 17)) + list(range(20, 23))
        self.on_peak_hours = on_peak_hours or list(range(17, 20))
    
    def get_prices(self, time_horizon: int, **kwargs) -> np.ndarray:
        """Get ToU prices for time horizon."""
        # Assume 15-minute intervals (96 per day)
        intervals_per_hour = 4
        prices = np.zeros(time_horizon)
        
        for t in range(time_horizon):
            # Calculate hour of day (0-23)
            hour = (t // intervals_per_hour) % 24
            
            if hour in self.off_peak_hours:
                prices[t] = self.off_peak_price
            elif hour in self.mid_peak_hours:
                prices[t] = self.mid_peak_price
            else:  # on_peak_hours
                prices[t] = self.on_peak_price
        
        return prices


class CriticalPeakPricingTariff(BaseTariff):
    """Critical Peak Pricing (CPP) tariff with event-based high prices."""
    
    def __init__(self,
                 base_tariff: BaseTariff,
                 critical_price: float = 0.50,
                 critical_hours: List[int] = None,
                 event_days: List[int] = None):
        """
        Initialize CPP tariff.
        
        Args:
            base_tariff: Base tariff for non-critical periods
            critical_price: Critical peak price in €/kWh
            critical_hours: Hours during which critical pricing applies
            event_days: Days when critical events occur (0=Monday, 6=Sunday)
        """
        super().__init__("Critical Peak Pricing")
        self.base_tariff = base_tariff
        self.critical_price = critical_price
        self.critical_hours = critical_hours or [17, 18, 19, 20]  # 5-8 PM
        self.event_days = event_days or [1, 2, 3]  # Tue, Wed, Thu (example)
    
    def get_prices(self, time_horizon: int, start_day: int = 0, **kwargs) -> np.ndarray:
        """
        Get CPP prices for time horizon.
        
        Args:
            time_horizon: Number of time steps
            start_day: Starting day of week (0=Monday)
        """
        # Get base prices
        prices = self.base_tariff.get_prices(time_horizon)
        
        intervals_per_hour = 4
        hours_per_day = 24
        intervals_per_day = intervals_per_hour * hours_per_day
        
        for t in range(time_horizon):
            # Calculate day of week and hour
            day = (start_day + (t // intervals_per_day)) % 7
            hour = (t // intervals_per_hour) % hours_per_day
            
            # Apply critical pricing if it's an event day and critical hour
            if day in self.event_days and hour in self.critical_hours:
                prices[t] = self.critical_price
        
        return prices


class RealTimePricingTariff(BaseTariff):
    """Real-Time Pricing (RTP) tariff with varying prices."""
    
    def __init__(self,
                 base_price: float = 0.15,
                 volatility: float = 0.05,
                 price_pattern: Optional[np.ndarray] = None):
        """
        Initialize RTP tariff.
        
        Args:
            base_price: Base price in €/kWh
            volatility: Price volatility factor
            price_pattern: Predefined price pattern (optional)
        """
        super().__init__("Real-Time Pricing")
        self.base_price = base_price
        self.volatility = volatility
        self.price_pattern = price_pattern
    
    def get_prices(self, time_horizon: int, seed: int = 42, **kwargs) -> np.ndarray:
        """Get RTP prices for time horizon."""
        if self.price_pattern is not None:
            # Use predefined pattern, repeat if necessary
            if len(self.price_pattern) >= time_horizon:
                return self.price_pattern[:time_horizon]
            else:
                repeats = int(np.ceil(time_horizon / len(self.price_pattern)))
                extended_pattern = np.tile(self.price_pattern, repeats)
                return extended_pattern[:time_horizon]
        else:
            # Generate synthetic RTP prices
            np.random.seed(seed)
            
            # Create price variations based on daily pattern
            hours = np.arange(time_horizon) / 4  # Assuming 15-min intervals
            
            # Base daily pattern (higher during day, lower at night)
            daily_pattern = (
                self.base_price * (1 + 0.3 * np.sin(2 * np.pi * hours / 24)) +
                self.volatility * np.random.randn(time_horizon)
            )
            
            # Ensure non-negative prices
            prices = np.maximum(daily_pattern, 0.01)
            
            return prices


class EmergencyDemandResponseTariff(BaseTariff):
    """Emergency Demand Response (EDR) tariff with very high event prices."""
    
    def __init__(self,
                 base_tariff: BaseTariff,
                 emergency_price: float = 1.00,
                 emergency_probability: float = 0.05,
                 emergency_duration: int = 4):  # hours
        """
        Initialize EDR tariff.
        
        Args:
            base_tariff: Base tariff for normal periods
            emergency_price: Emergency price in €/kWh
            emergency_probability: Probability of emergency event per day
            emergency_duration: Duration of emergency events in hours
        """
        super().__init__("Emergency Demand Response")
        self.base_tariff = base_tariff
        self.emergency_price = emergency_price
        self.emergency_probability = emergency_probability
        self.emergency_duration = emergency_duration
    
    def get_prices(self, time_horizon: int, seed: int = 42, **kwargs) -> np.ndarray:
        """Get EDR prices for time horizon."""
        # Get base prices
        prices = self.base_tariff.get_prices(time_horizon)
        
        np.random.seed(seed)
        intervals_per_hour = 4
        intervals_per_day = 96
        emergency_duration_intervals = self.emergency_duration * intervals_per_hour
        
        # Determine emergency events
        num_days = int(np.ceil(time_horizon / intervals_per_day))
        
        for day in range(num_days):
            if np.random.rand() < self.emergency_probability:
                # Emergency event occurs
                day_start = day * intervals_per_day
                day_end = min((day + 1) * intervals_per_day, time_horizon)
                
                # Random start time during peak hours (4 PM - 8 PM)
                peak_start = day_start + 16 * intervals_per_hour  # 4 PM
                peak_end = day_start + 20 * intervals_per_hour    # 8 PM
                
                if peak_end <= day_end:
                    event_start = np.random.randint(peak_start, peak_end - emergency_duration_intervals + 1)
                    event_end = min(event_start + emergency_duration_intervals, time_horizon)
                    
                    # Apply emergency pricing
                    prices[event_start:event_end] = self.emergency_price
        
        return prices


class TariffManager:
    """Manager class for handling different tariff types and scenarios."""
    
    def __init__(self):
        self.tariffs = {}
        self.scenarios = {}
    
    def add_tariff(self, tariff: BaseTariff):
        """Add a tariff to the manager."""
        self.tariffs[tariff.name] = tariff
    
    def get_tariff(self, name: str) -> BaseTariff:
        """Get a tariff by name."""
        return self.tariffs.get(name)
    
    def create_default_tariffs(self):
        """Create default set of tariffs for benchmarking."""
        # Time-of-Use tariff
        tou = TimeOfUseTariff(
            off_peak_price=0.08,
            mid_peak_price=0.12,
            on_peak_price=0.20
        )
        self.add_tariff(tou)
        
        # Critical Peak Pricing based on ToU
        cpp = CriticalPeakPricingTariff(
            base_tariff=tou,
            critical_price=0.40,
            critical_hours=[17, 18, 19, 20]
        )
        self.add_tariff(cpp)
        
        # Real-Time Pricing
        rtp = RealTimePricingTariff(
            base_price=0.12,
            volatility=0.04
        )
        self.add_tariff(rtp)
        
        # Emergency Demand Response based on ToU
        edr = EmergencyDemandResponseTariff(
            base_tariff=tou,
            emergency_price=0.80,
            emergency_probability=0.1
        )
        self.add_tariff(edr)
    
    def create_tariff_scenarios(self, 
                               time_horizon: int = 96,
                               num_scenarios: int = 10) -> Dict:
        """
        Create multiple tariff scenarios for benchmarking.
        
        Args:
            time_horizon: Number of time steps
            num_scenarios: Number of scenarios to generate
            
        Returns:
            Dictionary mapping scenario names to price arrays
        """
        scenarios = {}
        
        # Ensure default tariffs exist
        if not self.tariffs:
            self.create_default_tariffs()
        
        # Base scenarios for each tariff type
        for tariff_name, tariff in self.tariffs.items():
            scenarios[f"{tariff_name}_base"] = tariff.get_prices(time_horizon)
        
        # Variations for sensitivity analysis
        for i in range(num_scenarios - len(self.tariffs)):
            scenario_name = f"variation_{i+1}"
            
            # Randomly select base tariff and modify
            base_tariff = np.random.choice(list(self.tariffs.keys()))
            base_prices = self.tariffs[base_tariff].get_prices(time_horizon, seed=i)
            
            # Apply random scaling
            scale_factor = 0.8 + 0.4 * np.random.rand()  # 0.8 to 1.2
            scenarios[scenario_name] = base_prices * scale_factor
        
        return scenarios
    
    def get_export_prices(self, 
                         import_prices: np.ndarray,
                         export_ratio: float = 0.4) -> np.ndarray:
        """
        Generate export prices based on import prices.
        
        Args:
            import_prices: Import price array
            export_ratio: Ratio of export to import prices
            
        Returns:
            Export price array
        """
        return import_prices * export_ratio
    
    def get_community_prices(self,
                           import_prices: np.ndarray,
                           export_prices: np.ndarray,
                           community_spread: float = 0.5) -> np.ndarray:
        """
        Generate community trading prices.
        
        Args:
            import_prices: Import price array
            export_prices: Export price array  
            community_spread: Community price as fraction from export to import
            
        Returns:
            Community trading price array
        """
        return export_prices + community_spread * (import_prices - export_prices)
    
    def save_scenarios(self, scenarios: Dict, filepath: str):
        """Save tariff scenarios to file."""
        # Convert numpy arrays to lists for JSON serialization
        scenarios_json = {}
        for name, prices in scenarios.items():
            scenarios_json[name] = prices.tolist()
        
        with open(filepath, 'w') as f:
            json.dump(scenarios_json, f, indent=2)
    
    def load_scenarios(self, filepath: str) -> Dict:
        """Load tariff scenarios from file."""
        with open(filepath, 'r') as f:
            scenarios_json = json.load(f)
        
        # Convert lists back to numpy arrays
        scenarios = {}
        for name, prices in scenarios_json.items():
            scenarios[name] = np.array(prices)
        
        return scenarios