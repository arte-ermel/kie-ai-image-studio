import os
import sys
import json
import requests

def run():
    if len(sys.argv) < 3:
        print("Usage: python get_kie_image.py <taskId> <output_file>")
        sys.exit(1)
        
    task_id = sys.argv[1]
    output_file = sys.argv[2]
    
    # Load API key: environment variable first, then .env file
    api_key = os.environ.get("KIE_API_KEY", "").strip()
    if not api_key:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('KIE_API_KEY='):
                        api_key = line.strip().split('=', 1)[1].strip('"\'')
                        break
    if not api_key:
        print("ERROR: KIE_API_KEY not found.")
        print("Run 'python agent.py' for guided setup, or set the KIE_API_KEY environment variable.")
        sys.exit(1)
                
    poll_url = "https://api.kie.ai/api/v1/jobs/recordInfo"
    poll_params = {"taskId": task_id}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        poll_resp = requests.get(poll_url, headers=headers, params=poll_params, timeout=15)
        poll_resp.raise_for_status()
        poll_result = poll_resp.json()
    except Exception as e:
        print(f"ERROR polling task: {e}")
        sys.exit(1)
    data = poll_result.get("data", {})
    state = data.get("state")
    
    if state == "success" or state == "completed":
        result_json_str = data.get("resultJson", "{}")
        try:
            result_json = json.loads(result_json_str)
        except (json.JSONDecodeError, ValueError):
            result_json = {}
            
        result_urls = result_json.get("resultUrls", [])
        if result_urls and len(result_urls) > 0:
            image_url = result_urls[0]
            print(f"Downloading image from {image_url}")
            try:
                img_resp = requests.get(image_url, timeout=30)
                img_resp.raise_for_status()
                with open(output_file, 'wb') as f:
                    f.write(img_resp.content)
                print(f"Successfully saved to {output_file}")
            except Exception as e:
                print(f"ERROR downloading image: {e}")
                sys.exit(1)
        else:
            print("No URL found")
    else:
        print(f"Task incomplete: {state}")

if __name__ == "__main__":
    run()
