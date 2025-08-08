#!/usr/bin/env python3
"""
CLI Agent Logger using mitmweb for capturing API requests across any source
"""

import os
import sys
import subprocess
import signal
import time
from pathlib import Path


class MitmLogger:
    def __init__(self, host="localhost", port=8000, logs_dir="logs", target_url="https://api.moonshot.cn"):
        self.host = host
        self.port = port
        self.logs_dir = Path(logs_dir)
        self.target_url = target_url
        self.process = None
        
    def setup_logs_directory(self):
        """Create logs directory and configuration"""
        self.logs_dir.mkdir(exist_ok=True)
        
        # Create mitmweb configuration
        config_dir = self.logs_dir / ".mitmproxy"
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
        
    def start(self):
        """Start mitmweb logger"""
        self.setup_logs_directory()
        
        print(f"🚀 Starting CLI Agent Logger with mitmweb...")
        print(f"   Proxy: http://localhost:{self.port}")
        print(f"   Web UI: http://localhost:{self.port + 1000}")
        print(f"   Target: {self.target_url}")
        print(f"   Logs: {self.logs_dir}/")
        print("")
        print("Configure your client to use:")
        print(f"  Base URL: http://localhost:{self.port}")
        print("")
        
        # Start mitmweb with correct working directory
        try:
            cmd = [
                "mitmweb",
                "--mode", f"reverse:{self.target_url}",
                "--listen-port", str(self.port),
                "--web-host", self.host,
                "--web-port", str(self.port + 1000),
                "--set", f"save_stream_file=cli_agent_requests.mitm",
                "--set", "stream_large_bodies=1m"
            ]
            
            self.process = subprocess.Popen(cmd, cwd=self.logs_dir)
            
            print("✅ Logger started successfully!")
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
        print("\n✅ Logger stopped")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='CLI Agent Logger using mitmweb')
    parser.add_argument('--host', '-H', default='localhost', help='Host to bind to')
    parser.add_argument('--port', '-p', type=int, default=8000, help='Port to listen on')
    parser.add_argument('--logs-dir', '-d', default='logs', help='Directory to save logs')
    parser.add_argument('--target', '-t', default='https://api.moonshot.cn', help='Target API URL to proxy')
    
    args = parser.parse_args()

    logger = MitmLogger(host=args.host, port=args.port, logs_dir=args.logs_dir, target_url=args.target)
    logger.start()


if __name__ == '__main__':
    main()