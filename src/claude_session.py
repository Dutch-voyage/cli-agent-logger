#!/usr/bin/env python3
"""
Integrated command to run Claude CLI with API logging
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from .mitm_logger import MitmLogger
from .extract_logs import extract_flows_to_json


class ClaudeSession:
    def __init__(self, base_url, port=8000, logs_dir="logs"):
        self.base_url = base_url
        self.port = port
        self.logs_dir = Path(logs_dir)
        self.logger = None
        self.original_env = {}

    def parse_url(self, url):
        """Parse URL to extract target and path"""
        parsed = urlparse(url)
        target = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path.lstrip("/") if parsed.path else ""
        return target, path

    def start_logger(self, target_url):
        """Start the logger in background terminal"""
        # Ensure logs directory exists
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"🚀 Starting API logger in background...")
        print(f"   Target: {target_url}")
        print(f"   Proxy: http://localhost:{self.port}")
        print(f"   Logs: {self.logs_dir}/")

        # Start mitmweb directly in background terminal
        cmd = [
            "mitmweb",
            "--mode", f"reverse:{target_url}",
            "--listen-port", str(self.port),
            "--web-host", "localhost",
            "--web-port", str(self.port + 1000),
            "--set", f"save_stream_file=cli_agent_requests.mitm",
            "--set", "stream_large_bodies=1m"
        ]
        
        # Start logger process with correct working directory
        try:
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
        """Extract logs after session ends"""
        print("📝 Extracting logs...")

        # Find the latest .mitm file
        mitm_files = list(self.logs_dir.glob("*.mitm"))
        if not mitm_files:
            print("ℹ️  No log files found in", self.logs_dir)
            # Also check if there's a cli_agent_requests.mitm file
            expected_file = self.logs_dir / "cli_agent_requests.mitm"
            if expected_file.exists():
                latest_mitm = expected_file
            else:
                return
        else:
            latest_mitm = max(mitm_files, key=lambda x: x.stat().st_mtime)
        
        # Ensure file is written and closed
        time.sleep(1)
        
        # Use the extract function directly
        try:
            success = extract_flows_to_json(str(latest_mitm))
            if success:
                print("✅ Logs extracted successfully!")
                # Show extracted files
                base_name = str(latest_mitm).replace('.mitm', '').replace('moonshot_requests', 'cli_agent_requests')
                original_file = f"{base_name}_original.json"
                merged_file = f"{base_name}_merged.json"
                if os.path.exists(original_file):
                    print(f"   📄 Original: {original_file}")
                if os.path.exists(merged_file):
                    print(f"   🔗 Merged: {merged_file}")
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

    args = parser.parse_args()

    # Use environment variable as fallback
    base_url = args.base_url or os.environ.get(
        "ANTHROPIC_BASE_URL", "https://api.moonshot.cn/anthropic"
    )

    if not base_url:
        print("❌ No base_url provided and ANTHROPIC_BASE_URL not set")
        sys.exit(1)

    session = ClaudeSession(base_url=base_url, port=args.port, logs_dir=args.logs_dir)

    session.run()


if __name__ == "__main__":
    main()
