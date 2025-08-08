# CLI Agent Logger

A Python-based tool for capturing and logging API requests from CLI applications like Claude Code. Built on mitmweb from the mitmproxy project.

## Features

- **Real-time API logging**: Captures all HTTP/HTTPS requests and responses
- **Streaming response merging**: Merges SSE (Server-Sent Events) chunks into complete responses
- **JSON export**: Converts captured flows to clean JSON format
- **Continuous logging**: Appends to existing logs instead of overwriting
- **Multiple API support**: Works with any API endpoint, not just Claude
- **Background execution**: Runs in background without interfering with CLI display

## Installation

1. **Install mitmproxy**:
   ```bash
   pip install mitmproxy
   ```

2. **Install the package**:
   ```bash
   pip install -e .
   ```

## Usage

### Basic Usage

Run Claude CLI with API logging using the default Moonshot API:

```bash
claude-with-logging
```

### Custom API Endpoint

Use with a specific API endpoint:

```bash
claude-with-logging https://api.moonshot.cn/anthropic
```

### Custom Configuration

```bash
# Custom port
claude-with-logging --port 8080

# Custom logs directory
claude-with-logging --logs-dir my-logs

# Full command
claude-with-logging https://api.custom.com/anthropic --port 9000 --logs-dir ./logs
```

### Environment Variables

The tool will automatically use `ANTHROPIC_BASE_URL` if set:

```bash
export ANTHROPIC_BASE_URL=https://api.moonshot.cn/anthropic
claude-with-logging  # Uses the environment variable
```

## How It Works

1. **Proxy Setup**: Starts mitmweb in reverse proxy mode
2. **Environment**: Sets `ANTHROPIC_BASE_URL` to point to the local proxy
3. **CLI Execution**: Runs Claude CLI which connects through the proxy
4. **Logging**: Captures all requests and responses to `.mitm` files
5. **Extraction**: Converts captured data to JSON format on exit

## File Structure

```
logs/
├── cli_agent_requests.mitm     # Raw mitmweb capture file
├── cli_agent_requests_original.json  # Original responses
├── cli_agent_requests_merged.json    # Merged streaming responses
└── .mitmproxy/              # mitmweb configuration
```

## JSON Output Format

The tool generates two JSON files:

### Original Format
Contains raw responses including streaming chunks:
```json
[
  {
    "timestamp": "2024-01-01T12:00:00",
    "request_body": {...},
    "response": {
      "status_code": 200,
      "response_body": "data: {...}\n\ndata: {...}\n\ndata: [DONE]",
      "type": "original"
    }
  }
]
```

### Merged Format
Contains merged streaming responses:
```json
[
  {
    "timestamp": "2024-01-01T12:00:00",
    "request_body": {...},
    "response": {
      "id": "msg_123",
      "type": "message",
      "role": "assistant",
      "content": [{"type": "text", "text": "Complete response..."}],
      "model": "claude-3-sonnet-20240229",
      "stop_reason": "end_turn",
      "usage": {"input_tokens": 100, "output_tokens": 150},
      "type": "merged"
    }
  }
]
```

## Manual Extraction

You can manually extract logs from any `.mitm` file:

```bash
python -m src.extract_logs logs/cli_agent_requests.mitm
```

## Troubleshooting

### Common Issues

1. **"No log files found"**: Ensure mitmweb is running and receiving traffic
2. **"Error reading flows"**: The `.mitm` file may be empty or corrupted
3. **Port conflicts**: Use `--port` flag to use a different port
4. **Connection issues**: Check firewall settings and port availability

### Debug Mode

Check if mitmweb is running:
```bash
# Check processes
ps aux | grep mitmweb

# Check web interface
open http://localhost:9000
```

### Manual Testing

Test the proxy directly:
```bash
# Start proxy manually
mitmweb --mode reverse:https://api.moonshot.cn --listen-port 8000

# Test with curl
curl -x http://localhost:8000 https://api.moonshot.cn/v1/chat/completions
```

## Security Notes

- This tool is designed for **defensive security analysis only**
- Only use for logging your own API traffic
- Do not use for unauthorized interception
- Logs contain sensitive data - handle appropriately

## Dependencies

- Python 3.6+
- mitmproxy
- No additional Python packages required

## License

MIT License - see LICENSE file for details.