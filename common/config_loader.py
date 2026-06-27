import os
import json

def load_server_config():
    # Find the path relative to this utility script 
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config.json")
    
    defaults = {
        "host": "",
        "port": 8888,
        "timeout_seconds": 15.0,
        "max_read_chunk": 1024
    }
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)
                defaults.update(config_data)
        except Exception:
            print("Warning: Failed to parse config.json. Using fallback defaults.")
            
    return defaults