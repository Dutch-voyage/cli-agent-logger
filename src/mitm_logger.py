#!/usr/bin/env python3
"""
CLI Agent Logger using mitmweb for capturing API requests across any source
"""

import os
import sys
import subprocess
import signal
import time
import socket
from pathlib import Path
from urllib.parse import urlparse


class MitmLogger:
    def __init__(self, host="localhost", port=8000, logs_dir="cli-agent-logs", target_url="https://api.moonshot.cn", debug=False):
        self.host = host
        self.port = port
        self.logs_dir = Path(logs_dir)
        self.target_url = target_url
        self.debug = debug
        self.process = None
        self.local_logs_dir = Path(logs_dir)
        
        # Create global directory based on target URL
        parsed_url = urlparse(target_url)
        url_path = parsed_url.netloc.replace(':', '-').replace('/', '-')
        self.global_logs_dir = Path.home() / ".claude" / "projects" / url_path
        
    def find_available_port(self, start_port=8000):
        """Find an available port starting from start_port"""
        port = start_port
        while port < start_port + 100:  # Try 100 ports max
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    result = s.connect_ex((self.host, port))
                    if result != 0:  # Port is available
                        return port
                    port += 1
            except Exception:
                port += 1
        return None
        
    def setup_logs_directory(self):
        """Create logs directories for both local and global locations"""
        # Create local logs directory (cwd)
        self.local_logs_dir.mkdir(exist_ok=True)
        
        # Create global logs directory (~/.claude/projects/cli-agent-logs)
        self.global_logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create mitmweb configuration for both locations
        for logs_dir in [self.local_logs_dir, self.global_logs_dir]:
            config_dir = logs_dir / ".mitmproxy"
            config_dir.mkdir(exist_ok=True)
            
            # Create custom mitmweb config
            config_file = config_dir / "config.yaml"
            config_content = f"""
# Mitmproxy configuration for CLI Agent logging
save_stream_file: cli_agent_requests.mitm
web_host: {self.host}
web_port: {self.port + 1000}
listen_port: {self.port}
mode: reverse:{self.target_url}
"""
            # Write the configuration file
            with open(config_file, 'w') as f:
                f.write(config_content.strip())
        
    def start(self):
        """Start mitmweb logger with port conflict handling"""
        self.setup_logs_directory()
        
        # Check if port is available
        original_port = self.port
        available_port = self.find_available_port(self.port)
        
        if available_port is None:
            print(f"❌ No available ports found starting from port {self.port}")
            return None
            
        if available_port != self.port:
            print(f"⚠️  Port {self.port} is occupied, using port {available_port} instead")
            self.port = available_port
        
        print(f"🚀 Starting CLI Agent Logger with mitmweb...")
        print(f"   Proxy: http://localhost:{self.port}")
        print(f"   Web UI: http://localhost:{self.port + 1000}")
        print(f"   Target: {self.target_url}")
        print(f"   Local Logs: {self.local_logs_dir}/")
        print(f"   Global Logs: {self.global_logs_dir}/")
        print("")
        print("Configure your client to use:")
        print(f"  Base URL: http://localhost:{self.port}")
        print("")
        
        # Start mitmweb with correct working directory (using local logs dir by default)
        try:
            cmd = [
                "mitmweb",
                "--mode", f"reverse:{self.target_url}",
                "--listen-port", str(self.port),
                "--web-host", self.host,
                "--web-port", str(self.port + 1000),
                "--set", f"save_stream_file=cli_agent_requests.mitm",
                "--set", "stream_large_bodies=10m",
                "--set", "body_size_limit=50m",
                "--set", "connection_timeout=30",
                "--set", "read_timeout=30",
                "--set", "keep_alive_timeout=75",
                "--set", "http2_ping_keepalive=30",
                "--set", "upstream_cert=false"
            ]
            
            # Add debug settings if debug mode is enabled
            if self.debug:
                cmd.extend([
                    "--set", "flow_detail=3",
                    "--set", "proxy_debug=true",
                    "--set", "verbose=true",
                    "--set", "debug=true"
                ])
            
            self.process = subprocess.Popen(cmd, cwd=self.local_logs_dir)
            
            print("✅ Logger started successfully!")
            if self.debug:
                print("🐛 Debug mode enabled - verbose logging active")
            print("📁 Logs will be saved to both local and global locations")
            print(f"   • Local: {self.local_logs_dir}/cli_agent_requests.mitm")
            print(f"   • Global: {self.global_logs_dir}/cli_agent_requests.mitm")
            
            # Don't wait - let caller control lifecycle
            return self.process
            
        except FileNotFoundError:
            print("❌ mitmweb not found. Please install mitmproxy:")
            print("   pip install mitmproxy")
            return None
        except Exception as e:
            print(f"❌ Failed to start logger: {e}")
            return None
    
    def stop(self):
        """Stop mitmweb logger"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        # Copy logs to global location when stopping
        self._sync_logs_to_global()
        print("\n✅ Logger stopped")
        print("📁 Logs synchronized to global location")
    
    def _sync_logs_to_global(self):
        """Copy JSON files to global directory based on working directory path"""
        try:
            from .extract_logs import extract_flows_to_json
            import shutil
            
            # Create global directory based on current working directory path
            current_dir = Path.cwd()
            dir_name = str(current_dir).replace('/', '-').replace(':', '-').replace(' ', '-')
            global_logs_dir = Path.home() / ".claude" / "projects" / dir_name
            global_logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract JSON files to local directory first
            local_mitm = self.local_logs_dir / "cli_agent_requests.mitm"
            if local_mitm.exists():
                print(f"   • Extracting JSON files to local directory")
                success = extract_flows_to_json(str(local_mitm))
                
                if success:
                    # Copy merged JSON file to global directory with timestamp
                    from datetime import datetime
                    
                    base_name = str(local_mitm).replace('.mitm', '')
                    merged_json_file = f"{base_name}_merged.json"
                    
                    local_json = Path(merged_json_file)
                    if local_json.exists():
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        global_json = global_logs_dir / f"cli_agent_requests_{timestamp}.json"
                        shutil.copy2(local_json, global_json)
                        print(f"   • Copied merged JSON to global directory: {global_json}")
            else:
                print(f"   ⚠️  No mitm file found: {local_mitm}")
                    
        except Exception as e:
            print(f"   ⚠️  Failed to generate global JSON files: {e}")
    
    def get_log_locations(self):
        """Get both local and global log locations"""
        return {
            "local": self.local_logs_dir,
            "global": self.global_logs_dir
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='CLI Agent Logger using mitmweb')
    parser.add_argument('--host', '-H', default='localhost', help='Host to bind to')
    parser.add_argument('--port', '-p', type=int, default=8000, help='Port to listen on')
    parser.add_argument('--logs-dir', '-d', default='logs', help='Directory to save logs')
    parser.add_argument('--target', '-t', default='https://api.moonshot.cn', help='Target API URL to proxy')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with verbose logging')
    
    args = parser.parse_args()

    logger = MitmLogger(host=args.host, port=args.port, logs_dir=args.logs_dir, target_url=args.target, debug=args.debug)
    logger.start()


if __name__ == '__main__':
    main()