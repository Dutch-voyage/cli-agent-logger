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
    if not os.path.exists(mitm_file):
        print(f"❌ File not found: {mitm_file}")
        return False
    
    flows_original = []
    flows_merged = []
    
    try:
        with open(mitm_file, 'rb') as f:
            flow_reader = io.FlowReader(f)
            
            for flow in flow_reader.stream():
                if hasattr(flow, 'request') and hasattr(flow, 'response'):
                    # Extract request details
                    request_body = flow.request.get_text() if flow.request.content else None
                    response_body = flow.response.get_text() if flow.response.content else None
                    
                    # Original (unmerged) response
                    original_response = {
                        'status_code': flow.response.status_code,
                        'headers': dict(flow.response.headers),
                        'response_body': response_body,
                        'size': len(flow.response.content) if flow.response.content else 0,
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
                        'timestamp': datetime.fromtimestamp(flow.request.timestamp_start).isoformat(),
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
    base_name = mitm_file.replace('.mitm', '').replace('moonshot_requests', 'cli_agent_requests')
    
    # Original format
    original_file = output_file or f"{base_name}_original.json"
    merged_file = f"{base_name}_merged.json"
    
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


def main():
    parser = argparse.ArgumentParser(description='Convert mitmweb flows to JSON')
    parser.add_argument('mitm_file', help='Path to .mitm flow file')
    parser.add_argument('-o', '--output', help='Output JSON file')
    
    args = parser.parse_args()
    
    extract_flows_to_json(args.mitm_file, args.output)


if __name__ == '__main__':
    main()