#!/usr/bin/env python3
"""
Extract logs from mitmweb capture into JSON format
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from mitmproxy import io
    from mitmproxy.http import HTTPFlow
except ImportError:
    print("mitmproxy not found. Install with: pip install mitmproxy")
    sys.exit(1)


def extract_flows_to_json(mitm_file, output_file=None, merge_streaming=True):
    """Convert mitmweb flow file to JSON with both merged and unmerged options"""
    # Ensure output directory exists if output_file is specified
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not os.path.exists(mitm_file):
        print(f"❌ File not found: {mitm_file}")
        return False
    
    flows_original = []
    flows_merged = []
    
    try:
        with open(mitm_file, 'rb') as f:
            flow_reader = io.FlowReader(f)
            
            for flow in flow_reader.stream():
                if hasattr(flow, 'request') and hasattr(flow, 'response') and flow.response is not None:
                    # Extract request details
                    request_body = flow.request.get_text() if flow.request and flow.request.content else None
                    response_body = flow.response.get_text() if flow.response and flow.response.content else None
                    
                    # Original (unmerged) response
                    original_response = {
                        'status_code': flow.response.status_code if flow.response else None,
                        'headers': dict(flow.response.headers) if flow.response and hasattr(flow.response, 'headers') else {},
                        'response_body': response_body,
                        'size': len(flow.response.content) if flow.response and flow.response.content else 0,
                        'is_streaming': 'data: ' in (response_body or '')
                    }
                    
                    # Merged response (if applicable)
                    merged_response = original_response.copy()
                    merged_body = response_body
                    
                    if response_body and 'data:' in response_body and merge_streaming:
                        lines = response_body.strip().split('\n')
                        merged_content = ""
                        full_response = None
                        
                        for line in lines:
                            line = line.strip()
                            if line.startswith('data:'):
                                try:
                                    data_str = line[5:].strip()
                                    if data_str == '[DONE]':
                                        continue
                                    
                                    chunk = json.loads(data_str)
                                    
                                    # Handle different message types
                                    if chunk.get('type') == 'message_start':
                                        full_response = chunk.get('message', {})
                                    elif chunk.get('type') == 'content_block_start':
                                        pass  # Initialize content if needed
                                    elif chunk.get('type') == 'content_block_delta':
                                        delta_content = chunk.get('delta', {}).get('text', '')
                                        merged_content += delta_content
                                    elif chunk.get('type') == 'message_delta':
                                        # Update usage tokens from final message_delta
                                        delta_usage = chunk.get('usage', {})
                                        if 'output_tokens' in delta_usage:
                                            final_output_tokens = delta_usage['output_tokens']
                                            if full_response and 'usage' in full_response:
                                                full_response['usage']['output_tokens'] = final_output_tokens
                                
                                except (json.JSONDecodeError, KeyError):
                                    continue
                        
                        if full_response and merged_content:
                            # Build merged response with proper structure
                            merged_response = {
                                'id': full_response.get('id'),
                                'type': 'message',
                                'role': full_response.get('role', 'assistant'),
                                'content': [{
                                    'type': 'text',
                                    'text': merged_content
                                }],
                                'model': full_response.get('model'),
                                'stop_reason': 'end_turn',
                                'usage': full_response.get('usage', {})
                            }
                            
                            merged_body = json.dumps(merged_response, ensure_ascii=False)
                    
                    # Parse request_body as JSON if possible
                    parsed_request_body = None
                    if request_body:
                        try:
                            parsed_request_body = json.loads(request_body)
                        except (json.JSONDecodeError, ValueError):
                            parsed_request_body = request_body
                    
                    # Build request data with clean structure
                    request_data = {
                        'timestamp': datetime.fromtimestamp(flow.request.timestamp_start).isoformat() if flow.request and hasattr(flow.request, 'timestamp_start') else datetime.now().isoformat(),
                        'request_body': parsed_request_body,
                        'response': {}
                    }
                    
                    # Original format
                    flows_original.append({
                        **request_data,
                        'response': {
                            'status_code': original_response['status_code'],
                            'response_body': original_response['response_body'],
                            'type': 'original'
                        }
                    })
                    
                    # Merged format
                    flows_merged.append({
                        **request_data,
                        'response': {
                            **merged_response,
                            'type': 'merged'
                        }
                    })
    
    except Exception as e:
        print(f"❌ Error reading flows: {e}")
        return False
    
    if not flows_original:
        print(f"ℹ️  No flows found in {mitm_file}")
        return False
    
    # Save both formats
    base_name = mitm_file.replace('.mitm', '')
    
    # Original format
    original_file = output_file or f"{base_name}_original.json"
    merged_file = f"{base_name}_merged.json"
    
    # Ensure directories exist for output files
    Path(original_file).parent.mkdir(parents=True, exist_ok=True)
    Path(merged_file).parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Save original (unmerged)
        with open(original_file, 'w', encoding='utf-8') as f:
            json.dump(flows_original, f, indent=2, ensure_ascii=False, default=str)
        
        # Save merged
        with open(merged_file, 'w', encoding='utf-8') as f:
            json.dump(flows_merged, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"✅ Extracted {len(flows_original)} flows")
        print(f"   📄 Original: {original_file}")
        print(f"   🔗 Merged: {merged_file}")
        return True
        
    except Exception as e:
        print(f"❌ Error writing JSON: {e}")
        return False


def extract_from_both_locations():
    """Extract logs from local files and copy JSON to global locations"""
    from pathlib import Path
    import shutil
    
    # Check local directory for mitm files
    local_logs_dir = Path("cli-agent-logs")
    
    # Process all mitm files in local directory
    mitm_files = list(local_logs_dir.glob("*.mitm"))
    if not mitm_files:
        mitm_files = [local_logs_dir / "cli_agent_requests.mitm"]
    
    extracted_count = 0
    
    for mitm_file in mitm_files:
        if mitm_file.exists():
            # Create global directory based on current working directory path
            current_dir = Path.cwd()
            # Create a safe directory name from the full path
            dir_name = str(current_dir).replace('/', '-').replace(':', '-').replace(' ', '-')
            global_logs_dir = Path.home() / ".claude" / "projects" / dir_name
            global_logs_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"🔄 Processing: {mitm_file}")
            print(f"   📁 Global JSON output: {global_logs_dir}")
            
            # Extract JSON files to local directory first
            success = extract_flows_to_json(str(mitm_file))
            
            if success:
                # Copy merged JSON file to global directory with timestamp
                from datetime import datetime
                
                base_name = str(mitm_file).replace('.mitm', '')
                
                merged_json_file = f"{base_name}_merged.json"
                local_json = Path(merged_json_file)
                if local_json.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    global_json = global_logs_dir / f"cli_agent_requests_{timestamp}.json"
                    shutil.copy2(local_json, global_json)
                    print(f"   • Copied merged JSON to global directory: {global_json}")
                        
                extracted_count += 1
                print(f"✅ Extracted and copied to global directory")
            else:
                print(f"⚠️  Failed to extract")
    
    if extracted_count == 0:
        print("❌ No mitm files found in local directory")
        return False
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Convert mitmweb flows to JSON')
    parser.add_argument('mitm_file', nargs='?', help='Path to .mitm flow file')
    parser.add_argument('-o', '--output', help='Output JSON file')
    parser.add_argument('--all', action='store_true', help='Extract from both local and global locations')
    
    args = parser.parse_args()
    
    if args.all:
        extract_from_both_locations()
    elif args.mitm_file:
        extract_flows_to_json(args.mitm_file, args.output)
    else:
        # Default behavior: check both locations
        extract_from_both_locations()


if __name__ == '__main__':
    main()