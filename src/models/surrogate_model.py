import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score
from typing import Dict, List, Tuple, Optional, Any
import pickle
import json
from pathlib import Path


class TariffSurrogateModel:
    """
    XGBoost-based surrogate model for rapid evaluation of tariff scenarios.
    Maps tariff parameters to cost and fairness outcomes.
    """
    
    def __init__(self, 
                 time_horizon: int = 96,
                 num_buildings: int = 10):
        """
        Initialize surrogate model.
        
        Args:
            time_horizon: Number of time steps
            num_buildings: Number of buildings
        """
        self.time_horizon = time_horizon
        self.num_buildings = num_buildings
        
        # Model components
        self.cost_model = None
        self.fairness_model = None
        self.scaler = StandardScaler()
        
        # Feature engineering settings
        self.feature_names = []
        self.is_fitted = False
        
        # Model parameters
        self.xgb_params = {
            'objective': 'reg:squarederror',
            'max_depth': 6,
            'learning_rate': 0.1,
            'n_estimators': 100,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42
        }
    
    def extract_features(self, 
                        import_prices: np.ndarray,
                        export_prices: np.ndarray,
                        community_prices: np.ndarray) -> np.ndarray:
        """
        Extract features from price profiles for surrogate modeling.
        
        Args:
            import_prices: Import price array [time_steps]
            export_prices: Export price array [time_steps]
            community_prices: Community price array [time_steps]
            
        Returns:
            Feature vector
        """
        features = []
        
        # Statistical features for each price type
        for prices, prefix in [(import_prices, 'import'), 
                              (export_prices, 'export'), 
                              (community_prices, 'community')]:
            # Basic statistics
            features.extend([
                np.mean(prices),
                np.std(prices),
                np.min(prices),
                np.max(prices),
                np.median(prices)
            ])
            
            # Percentiles
            features.extend([
                np.percentile(prices, 25),
                np.percentile(prices, 75),
                np.percentile(prices, 90),
                np.percentile(prices, 95)
            ])
            
            # Volatility measures
            features.extend([
                np.var(prices),
                np.max(prices) - np.min(prices),  # Range
                np.std(prices) / np.mean(prices) if np.mean(prices) > 0 else 0  # CV
            ])
        
        # Price relationships
        features.extend([
            np.mean(import_prices - export_prices),  # Average spread
            np.mean(community_prices - export_prices),  # Community premium
            np.mean(import_prices - community_prices),  # Import premium
            np.corrcoef(import_prices, export_prices)[0, 1],  # Price correlation
        ])
        
        # Time-based features
        # Peak/off-peak ratios (assuming 15-min intervals)
        peak_hours = list(range(68, 80))  # 5-8 PM in 15-min intervals
        off_peak_hours = list(range(0, 28)) + list(range(92, 96))  # Night hours
        
        if len(peak_hours) > 0 and len(off_peak_hours) > 0:
            peak_import = np.mean(import_prices[peak_hours])
            off_peak_import = np.mean(import_prices[off_peak_hours])
            features.append(peak_import / off_peak_import if off_peak_import > 0 else 1.0)
        else:
            features.append(1.0)
        
        # Trend features (linear trend slope)
        time_index = np.arange(len(import_prices))
        import_trend = np.polyfit(time_index, import_prices, 1)[0]
        export_trend = np.polyfit(time_index, export_prices, 1)[0]
        features.extend([import_trend, export_trend])
        
        # Frequency domain features (simplified)
        # Daily pattern strength
        if len(import_prices) >= 96:  # Full day
            daily_pattern = import_prices[:96]
            morning_avg = np.mean(daily_pattern[28:44])  # 7-11 AM
            evening_avg = np.mean(daily_pattern[68:84])  # 5-9 PM
            night_avg = np.mean(daily_pattern[0:28])     # 0-7 AM
            
            features.extend([
                morning_avg / night_avg if night_avg > 0 else 1.0,
                evening_avg / night_avg if night_avg > 0 else 1.0
            ])
        else:
            features.extend([1.0, 1.0])
        
        return np.array(features)
    
    def create_feature_names(self):
        """Create feature names for interpretability."""
        names = []
        
        # Statistical features
        stat_names = ['mean', 'std', 'min', 'max', 'median', 'p25', 'p75', 'p90', 'p95', 'var', 'range', 'cv']
        for prefix in ['import', 'export', 'community']:
            for stat in stat_names:
                names.append(f'{prefix}_{stat}')
        
        # Price relationships
        names.extend([
            'import_export_spread',
            'community_export_premium', 
            'import_community_premium',
            'import_export_correlation'
        ])
        
        # Time-based features
        names.extend([
            'peak_offpeak_ratio',
            'import_trend',
            'export_trend',
            'morning_night_ratio',
            'evening_night_ratio'
        ])
        
        self.feature_names = names
        return names
    
    def prepare_training_data(self, 
                            scenarios: Dict[str, Dict],
                            feature_scaler: bool = True) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Prepare training data from scenario results.
        
        Args:
            scenarios: Dictionary mapping scenario names to results
            feature_scaler: Whether to apply feature scaling
            
        Returns:
            Tuple of (features, costs, fairness_metrics)
        """
        features_list = []
        costs_list = []
        fairness_list = []
        
        for scenario_name, results in scenarios.items():
            if 'prices' in results and 'total_cost' in results and 'fairness' in results:
                # Extract features from prices
                features = self.extract_features(
                    np.array(results['prices']['import']),
                    np.array(results['prices']['export']), 
                    np.array(results['prices']['community'])
                )
                
                features_list.append(features)
                costs_list.append(results['total_cost'])
                fairness_list.append(results['fairness'])
        
        if not features_list:
            raise ValueError("No valid scenarios found for training")
        
        # Convert to arrays
        X = np.array(features_list)
        y_cost = np.array(costs_list)
        y_fairness = np.array(fairness_list)
        
        # Feature scaling
        if feature_scaler:
            X = self.scaler.fit_transform(X)
        
        # Create feature names if not exists
        if not self.feature_names:
            self.create_feature_names()
        
        return X, y_cost, y_fairness
    
    def train_models(self, 
                    X: np.ndarray,
                    y_cost: np.ndarray,
                    y_fairness: np.ndarray,
                    test_size: float = 0.2,
                    validation: bool = True) -> Dict:
        """
        Train XGBoost models for cost and fairness prediction.
        
        Args:
            X: Feature matrix
            y_cost: Cost targets
            y_fairness: Fairness targets
            test_size: Test set size for validation
            validation: Whether to perform validation
            
        Returns:
            Training results and metrics
        """
        results = {}
        
        if validation:
            # Split data
            X_train, X_test, y_cost_train, y_cost_test, y_fairness_train, y_fairness_test = \
                train_test_split(X, y_cost, y_fairness, test_size=test_size, random_state=42)
        else:
            X_train, X_test = X, X
            y_cost_train, y_cost_test = y_cost, y_cost
            y_fairness_train, y_fairness_test = y_fairness, y_fairness
        
        # Train cost model
        self.cost_model = xgb.XGBRegressor(**self.xgb_params)
        self.cost_model.fit(X_train, y_cost_train)
        
        # Train fairness model
        self.fairness_model = xgb.XGBRegressor(**self.xgb_params)
        self.fairness_model.fit(X_train, y_fairness_train)
        
        self.is_fitted = True
        
        # Evaluate models
        if validation:
            # Cost model evaluation
            cost_pred_train = self.cost_model.predict(X_train)
            cost_pred_test = self.cost_model.predict(X_test)
            
            results['cost_metrics'] = {
                'train_mse': mean_squared_error(y_cost_train, cost_pred_train),
                'test_mse': mean_squared_error(y_cost_test, cost_pred_test),
                'train_r2': r2_score(y_cost_train, cost_pred_train),
                'test_r2': r2_score(y_cost_test, cost_pred_test)
            }
            
            # Fairness model evaluation
            fairness_pred_train = self.fairness_model.predict(X_train)
            fairness_pred_test = self.fairness_model.predict(X_test)
            
            results['fairness_metrics'] = {
                'train_mse': mean_squared_error(y_fairness_train, fairness_pred_train),
                'test_mse': mean_squared_error(y_fairness_test, fairness_pred_test),
                'train_r2': r2_score(y_fairness_train, fairness_pred_train),
                'test_r2': r2_score(y_fairness_test, fairness_pred_test)
            }
            
            # Cross-validation
            cv_cost_scores = cross_val_score(self.cost_model, X_train, y_cost_train, cv=5, scoring='r2')
            cv_fairness_scores = cross_val_score(self.fairness_model, X_train, y_fairness_train, cv=5, scoring='r2')
            
            results['cross_validation'] = {
                'cost_cv_mean': np.mean(cv_cost_scores),
                'cost_cv_std': np.std(cv_cost_scores),
                'fairness_cv_mean': np.mean(cv_fairness_scores),
                'fairness_cv_std': np.std(cv_fairness_scores)
            }
        
        # Feature importance
        results['feature_importance'] = {
            'cost_importance': dict(zip(self.feature_names, self.cost_model.feature_importances_)),
            'fairness_importance': dict(zip(self.feature_names, self.fairness_model.feature_importances_))
        }
        
        return results
    
    def predict(self, 
               import_prices: np.ndarray,
               export_prices: np.ndarray,
               community_prices: np.ndarray) -> Dict:
        """
        Predict cost and fairness for given price profiles.
        
        Args:
            import_prices: Import price array
            export_prices: Export price array
            community_prices: Community price array
            
        Returns:
            Dictionary with predictions
        """
        if not self.is_fitted:
            raise ValueError("Model must be trained before prediction")
        
        # Extract features
        features = self.extract_features(import_prices, export_prices, community_prices)
        features_scaled = self.scaler.transform(features.reshape(1, -1))
        
        # Make predictions
        cost_pred = self.cost_model.predict(features_scaled)[0]
        fairness_pred = self.fairness_model.predict(features_scaled)[0]
        
        return {
            'predicted_cost': cost_pred,
            'predicted_fairness': fairness_pred,
            'features': dict(zip(self.feature_names, features))
        }
    
    def batch_predict(self, scenarios: Dict[str, Dict]) -> Dict:
        """
        Make batch predictions for multiple scenarios.
        
        Args:
            scenarios: Dictionary of scenarios with price data
            
        Returns:
            Dictionary with predictions for each scenario
        """
        predictions = {}
        
        for scenario_name, scenario_data in scenarios.items():
            if 'prices' in scenario_data:
                pred = self.predict(
                    scenario_data['prices']['import'],
                    scenario_data['prices']['export'],
                    scenario_data['prices']['community']
                )
                predictions[scenario_name] = pred
        
        return predictions
    
    def save_model(self, filepath: str):
        """Save trained model to file."""
        model_data = {
            'cost_model': self.cost_model,
            'fairness_model': self.fairness_model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'time_horizon': self.time_horizon,
            'num_buildings': self.num_buildings,
            'xgb_params': self.xgb_params,
            'is_fitted': self.is_fitted
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)
    
    def load_model(self, filepath: str):
        """Load trained model from file."""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)
        
        self.cost_model = model_data['cost_model']
        self.fairness_model = model_data['fairness_model']
        self.scaler = model_data['scaler']
        self.feature_names = model_data['feature_names']
        self.time_horizon = model_data['time_horizon']
        self.num_buildings = model_data['num_buildings']
        self.xgb_params = model_data['xgb_params']
        self.is_fitted = model_data['is_fitted']
    
    def get_feature_importance_plot_data(self) -> Dict:
        """Get data for plotting feature importance."""
        if not self.is_fitted:
            raise ValueError("Model must be trained before getting feature importance")
        
        cost_importance = self.cost_model.feature_importances_
        fairness_importance = self.fairness_model.feature_importances_
        
        # Sort by cost importance
        sorted_indices = np.argsort(cost_importance)[::-1]
        
        return {
            'feature_names': [self.feature_names[i] for i in sorted_indices],
            'cost_importance': cost_importance[sorted_indices],
            'fairness_importance': fairness_importance[sorted_indices]
        }
    
    def explain_prediction(self, 
                          import_prices: np.ndarray,
                          export_prices: np.ndarray,
                          community_prices: np.ndarray,
                          top_features: int = 10) -> Dict:
        """
        Explain a prediction by showing top contributing features.
        
        Args:
            import_prices: Import price array
            export_prices: Export price array
            community_prices: Community price array
            top_features: Number of top features to explain
            
        Returns:
            Dictionary with explanation
        """
        prediction = self.predict(import_prices, export_prices, community_prices)
        
        # Get feature importance
        cost_importance = self.cost_model.feature_importances_
        fairness_importance = self.fairness_model.feature_importances_
        
        # Get top features
        top_cost_indices = np.argsort(cost_importance)[::-1][:top_features]
        top_fairness_indices = np.argsort(fairness_importance)[::-1][:top_features]
        
        explanation = {
            'prediction': prediction,
            'top_cost_features': [
                {
                    'name': self.feature_names[i],
                    'value': prediction['features'][self.feature_names[i]],
                    'importance': cost_importance[i]
                }
                for i in top_cost_indices
            ],
            'top_fairness_features': [
                {
                    'name': self.feature_names[i],
                    'value': prediction['features'][self.feature_names[i]],
                    'importance': fairness_importance[i]
                }
                for i in top_fairness_indices
            ]
        }
        
        return explanation