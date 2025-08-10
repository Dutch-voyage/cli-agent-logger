#!/usr/bin/env python3
"""
CLI for moonshot-api-logger
"""

import argparse
import os

from .mitm_logger import MitmLogger


def main():
    parser = argparse.ArgumentParser(
        description='Capture and log API requests to api.moonshot.cn',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  moonshot-logger                    # Start on default port 8000
  moonshot-logger --port 8080        # Start on port 8080
  moonshot-logger --host 0.0.0.0     # Listen on all interfaces
        '''
    )
    
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8000,
        help='Port to listen on (default: 8000)'
    )
    
    parser.add_argument(
        '--host', '-H',
        default='localhost',
        help='Host to bind to (default: localhost)'
    )
    parser.add_argument(
        '--logs-dir', '-d',
        default='cli-agent-logs',
        help='Directory to save logs (default: cli-agent-logs)'
    )
    
    args = parser.parse_args()
    
    # Change to current working directory so logs are saved where command is run
    os.chdir(os.getcwd())

    logger = MitmLogger(host=args.host, port=args.port, logs_dir=args.logs_dir)
    logger.start()



if __name__ == '__main__':
    main()