#!/usr/bin/env python3

import os
import sys
import subprocess
import webbrowser
import time
import argparse
from pathlib import Path

def check_dependencies():
    required_packages = [
        'flask', 'dash', 'dash-bootstrap-components', 
        'plotly', 'pandas', 'numpy'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        print("Please install them with:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def start_web_interface(dev_mode=False, port=8050, host='localhost'):
    print("🚀 Starting Dynamic Tariff Benchmarking Web Interface...")
    print(f"📡 Server will run on http://{host}:{port}")
    
    web_dir = Path(__file__).parent / "web"
    
    if not web_dir.exists():
        print("❌ Web directory not found!")
        return False
    
    if not check_dependencies():
        return False
    
    os.chdir(web_dir)
    sys.path.insert(0, str(web_dir))
    
    try:
        # Add the web directory to Python path before importing
        web_dir_str = str(web_dir)
        if web_dir_str not in sys.path:
            sys.path.insert(0, web_dir_str)
        
        # Import the app module dynamically to avoid static analysis warnings
        import importlib.util
        app_module_path = web_dir / "single_page_app.py"
        
        if not app_module_path.exists():
            print(f"❌ Application file not found: {app_module_path}")
            return False
        
        if dev_mode:
            print("🔧 Running in development mode...")
            spec = importlib.util.spec_from_file_location("single_page_app", app_module_path)
            app_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(app_module)
            app_module.app.run_server(debug=True, host=host, port=port)
        else:
            print("🏃 Running in production mode...")
            subprocess.run([
                sys.executable, "-c",
                f"""
import sys
sys.path.insert(0, '{web_dir}')
import single_page_app
single_page_app.app.run_server(debug=False, host='{host}', port={port})
"""
            ])
    
    except KeyboardInterrupt:
        print("\n⏹️  Server stopped by user")
        return True
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return False

def open_browser(url, delay=3):
    def delayed_open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
            print(f"🌐 Opened browser at {url}")
        except:
            print(f"⚠️  Could not open browser automatically. Please visit {url}")
    
    import threading
    browser_thread = threading.Thread(target=delayed_open, daemon=True)
    browser_thread.start()

def main():
    parser = argparse.ArgumentParser(description="Dynamic Tariff Benchmarking Web Interface")
    parser.add_argument("--dev", action="store_true", help="Run in development mode")
    parser.add_argument("--port", type=int, default=8050, help="Port to run on (default: 8050)")
    parser.add_argument("--host", default="localhost", help="Host to bind to (default: localhost)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    parser.add_argument("--check-deps", action="store_true", help="Only check dependencies")
    
    args = parser.parse_args()
    
    if args.check_deps:
        if check_dependencies():
            print("✅ All dependencies are installed!")
        sys.exit(0)
    
    print("=" * 60)
    print("🏠 DYNAMIC TARIFF BENCHMARKING FRAMEWORK")
    print("   Web Interface for Prosumer Community Optimization")
    print("=" * 60)
    
    if not args.no_browser:
        url = f"http://{args.host}:{args.port}"
        open_browser(url)
    
    success = start_web_interface(
        dev_mode=args.dev,
        port=args.port,
        host=args.host
    )
    
    if success:
        print("✅ Web interface started successfully!")
    else:
        print("❌ Failed to start web interface")
        sys.exit(1)

if __name__ == "__main__":
    main()