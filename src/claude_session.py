#!/usr/bin/env python3
"""
Integrated command to run Claude CLI with API logging
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from .mitm_logger import MitmLogger
from .extract_logs import extract_flows_to_json


class ClaudeSession:
    def __init__(self, base_url, port=8000, logs_dir="cli-agent-logs", debug=False):
        self.base_url = base_url
        self.port = port
        self.logs_dir = Path(logs_dir)
        self.debug = debug
        self.logger = None
        self.original_env = {}

    def find_available_port(self, start_port=8000):
        """Find an available port starting from start_port"""
        port = start_port
        while port < start_port + 100:  # Try 100 ports max
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    result = s.connect_ex(('localhost', port))
                    if result != 0:  # Port is available
                        return port
                    port += 1
            except Exception:
                port += 1
        return None
        
    def parse_url(self, url):
        """Parse URL to extract target and path"""
        parsed = urlparse(url)
        target = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.lstrip("/") if parsed.path else ""
        return target, path

    def start_logger(self, target_url):
        """Start the logger in background terminal"""
        # Ensure logs directory exists (absolute path)
        self.logs_dir = self.logs_dir.resolve()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if port is available
        original_port = self.port
        available_port = self.find_available_port(self.port)
        
        if available_port is None:
            print(f"❌ No available ports found starting from port {self.port}")
            return None
            
        if available_port != self.port:
            print(f"⚠️  Port {self.port} is occupied, using port {available_port} instead")
            self.port = available_port
        
        print(f"🚀 Starting API logger in background...")
        print(f"   Target: {target_url}")
        print(f"   Proxy: http://localhost:{self.port}")
        print(f"   Logs: {self.logs_dir}/")
        if self.debug:
            print("🐛 Debug mode enabled - verbose logging active")

        # Start mitmweb directly in background terminal
        cmd = [
            "mitmweb",
            "--mode", f"reverse:{target_url}",
            "--listen-port", str(self.port),
            "--web-host", "localhost",
            "--web-port", str(self.port + 1000),
            "--set", f"save_stream_file=cli_agent_requests.mitm",
            "--set", "stream_large_bodies=100m",
            "--set", "body_size_limit=500m",
            "--set", "connection_timeout=300",
            "--set", "read_timeout=300",
            "--set", "response_timeout=600",
            "--set", "keep_alive_timeout=300",
            "--set", "http2_ping_keepalive=60",
            "--set", "upstream_cert=false",
            "--set", "stream_websockets=true",
            "--set", "anticomp=true"
        ]
        
        # Add debug settings if debug mode is enabled
        if self.debug:
            cmd.extend([
                "--set", "proxy_debug=true",
                "--set", "web_debug=true",
                "--set", "termlog_verbosity=debug"
            ])
        
        # Start logger process with correct working directory
        try:
            debug_log_file = self.logs_dir / "mitm_debug.log"
            if self.debug:
                # In debug mode, redirect ALL output to file using shell
                env = os.environ.copy()
                env['MITMPROXY_DEBUG'] = '1'
                
                # Use shell to redirect both stdout and stderr
                cmd_str = ' '.join(f'"{arg}"' for arg in cmd) + f' >"{debug_log_file}" 2>&1'
                self.logger_process = subprocess.Popen(
                    cmd_str,
                    shell=True,
                    env=env,
                    cwd=self.logs_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print(f"🐛 Debug mode enabled - logs written to: {debug_log_file}")
            else:
                # In normal mode, suppress output
                self.logger_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    cwd=self.logs_dir
                )
            
            # Wait for logger to start
            time.sleep(3)
            return self.logger_process
            
        except Exception as e:
            print(f"❌ Failed to start logger: {e}")
            return None

    def setup_environment(self, path):
        """Set up environment variables"""
        local_url = f"http://localhost:{self.port}"
        if path:
            local_url = f"{local_url}/{path}"

        print(f"🌍 Setting ANTHROPIC_BASE_URL={local_url}")
        self.original_env = os.environ.copy()
        os.environ["ANTHROPIC_BASE_URL"] = local_url

    def run_claude_cli(self):
        """Run Claude CLI"""
        print("🤖 Starting Claude CLI...")
        print("   Press Ctrl+D or type 'exit' to quit")
        print("=" * 50)

        try:
            subprocess.run(["claude"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Claude CLI error: {e}")
            return False
        except FileNotFoundError:
            print("❌ Claude CLI not found. Please install it first.")
            return False
        return True

    def cleanup(self):
        """Clean up environment and stop logger"""
        # Restore original environment
        if self.original_env:
            os.environ.clear()
            os.environ.update(self.original_env)


        # Stop logger
        print("🛑 Stopping logger...")
        if hasattr(self, 'logger_process') and self.logger_process:
            try:
                self.logger_process.terminate()
                self.logger_process.wait(timeout=5)
                print("✅ Logger terminated successfully")
            except subprocess.TimeoutExpired:
                self.logger_process.kill()
                self.logger_process.wait()
                print("⚠️  Logger force-killed")
            except Exception as e:
                print(f"❌ Error terminating logger: {e}")
                # Fallback: kill any remaining mitmweb processes
                subprocess.run(["pkill", "-f", "mitmweb.*reverse.*"], check=False)
                subprocess.run(["pkill", "-f", "mitmproxy"], check=False)

    def extract_logs(self):
        """Extract logs to global directory based on target URL"""
        print("📝 Extracting logs to global directory...")

        # Find the latest .mitm file in local directory
        mitm_files = list(self.logs_dir.glob("*.mitm"))
        if not mitm_files:
            # Also check if there's a cli_agent_requests.mitm file
            expected_file = self.logs_dir / "cli_agent_requests.mitm"
            if expected_file.exists():
                latest_mitm = expected_file
            else:
                print("ℹ️  No mitm files found")
                return None
        else:
            latest_mitm = max(mitm_files, key=lambda x: x.stat().st_mtime if x.exists() else 0)
        
        # Ensure file is written and closed
        time.sleep(1)
        
        # Create global directory based on current working directory path
        current_dir = Path.cwd()
        dir_name = str(current_dir).replace('/', '-').replace(':', '-').replace(' ', '-')
        global_logs_dir = Path.home() / ".claude" / "projects" / dir_name
        global_logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Use the extract function to generate JSON in global directory
        try:
            success = extract_flows_to_json(
                str(latest_mitm),
                output_file=str(global_logs_dir / "cli_agent_requests_original.json")
            )
            if success:
                # Copy merged JSON file to global directory with timestamp
                from datetime import datetime
                
                base_name = str(latest_mitm).replace('.mitm', '')
                merged_json_file = f"{base_name}_merged.json"
                
                local_json = Path(merged_json_file)
                if local_json.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    global_json = global_logs_dir / f"cli_agent_requests_{timestamp}.json"
                    shutil.copy2(local_json, global_json)
                    print("✅ Logs extracted successfully!")
                    print(f"   📁 Global directory: {global_logs_dir}")
                    print(f"   📄 Merged JSON: {global_json}")
                else:
                    print("❌ Merged JSON file not found")
            else:
                print("❌ Failed to extract logs")
        except Exception as e:
            print(f"❌ Error extracting logs: {e}")

    def run(self):
        """Run complete session"""
        try:
            # Parse URL
            target, path = self.parse_url(self.base_url)

            # Start logger
            logger_proc = self.start_logger(target)

            # Setup environment
            self.setup_environment(path)

            # Run Claude CLI
            success = self.run_claude_cli()

            return success

        finally:
            # Always cleanup
            self.cleanup()
            self.extract_logs()


def main():
    parser = argparse.ArgumentParser(description="Run Claude CLI with API logging")
    parser.add_argument(
        "base_url",
        nargs="?",
        help="Base API URL (e.g., https://api.moonshot.cn/anthropic). Defaults to ANTHROPIC_BASE_URL env var or https://api.moonshot.cn/anthropic",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8000, help="Port for logger proxy"
    )
    parser.add_argument(
        "--logs-dir", "-d", default="cli-agent-logs", help="Directory to save logs"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode with verbose logging"
    )

    args = parser.parse_args()

    # Use environment variable as fallback
    base_url = args.base_url or os.environ.get(
        "ANTHROPIC_BASE_URL", "https://api.moonshot.cn/anthropic"
    )

    if not base_url:
        print("❌ No base_url provided and ANTHROPIC_BASE_URL not set")
        sys.exit(1)

    session = ClaudeSession(base_url=base_url, port=args.port, logs_dir=args.logs_dir, debug=args.debug)

    session.run()


if __name__ == "__main__":
    main()
