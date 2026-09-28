import socket
import urllib.request
import re
from concurrent.futures import ThreadPoolExecutor
import yaml

PORTS_TO_SCAN = [8080, 4747]  # 8080 for IP Webcam, 4747 for DroidCam
TIMEOUT = 0.5  # half second timeout per IP for fast scanning

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to public DNS to get the local interface IP used
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "192.168.1.100"
    finally:
        s.close()
    return ip

def check_ip_port(ip, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        result = sock.connect_ex((ip, port))
        sock.close()
        if result == 0:
            return ip, port
    except Exception:
        pass
    return None

def scan_network():
    local_ip = get_local_ip()
    ip_parts = local_ip.split('.')
    if len(ip_parts) != 4:
        print(f"[ERROR] Could not parse local IP: {local_ip}")
        return []
    
    subnet_base = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}."
    print(f"Scanning subnet {subnet_base}0/24 on ports {PORTS_TO_SCAN}...")
    print(f"Your PC local IP: {local_ip}")
    print("Please ensure DroidCam or IP Webcam is running on your phone!\n")

    found_devices = []
    
    # Scan IPs from 1 to 254 using ThreadPoolExecutor for high performance
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = []
        for i in range(1, 255):
            target_ip = f"{subnet_base}{i}"
            # Skip checking the PC itself to save time/noise
            if target_ip == local_ip:
                continue
            for port in PORTS_TO_SCAN:
                futures.append(executor.submit(check_ip_port, target_ip, port))
                
        for future in futures:
            res = future.result()
            if res:
                found_devices.append(res)
                
    return found_devices

def update_config(ip, port):
    config_path = "config.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            
        # Determine stream URL
        if port == 8080:
            # IP Webcam stream URLs
            url = f"rtsp://{ip}:{port}/h264_ulaw.sdp"
            fallback_url = f"http://{ip}:{port}/video"
            mode = "IP Webcam (RTSP)"
        else:
            # DroidCam stream URLs
            url = f"http://{ip}:{port}/video"
            fallback_url = f"http://{ip}:{port}/mjpegfeed"
            mode = "DroidCam"

        # Update the second camera (cam_2) source in config
        for camera in config.get("cameras", []):
            if camera.get("camera_id") == "cam_2":
                camera["source"] = url
                break
                
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
            
        print(f"\n[SUCCESS] UPDATED config.yaml!")
        print(f"   Camera: cam_2")
        print(f"   Mode:   {mode}")
        print(f"   URL:    {url}")
        return True
    except Exception as e:
        print(f"[ERROR] Could not update config.yaml: {e}")
        return False

def main():
    devices = scan_network()
    
    if not devices:
        print("[ERROR] No active phone camera servers found on your local WiFi.")
        print("\nCommon fixes:")
        print("1. Make sure both your Phone and PC are connected to the SAME WiFi network.")
        print("2. Open the camera app on your phone (IP Webcam or DroidCam) and make sure it is actively running/streaming.")
        print("3. Check if your router has AP Isolation / Client Isolation enabled (which blocks WiFi device communication).")
        return

    print("Found active devices:")
    for idx, (ip, port) in enumerate(devices):
        service = "IP Webcam" if port == 8080 else "DroidCam"
        print(f"  [{idx + 1}] {service} active at {ip}:{port}")
        
    # Auto-use the first discovered device
    target_ip, target_port = devices[0]
    update_config(target_ip, target_port)

if __name__ == "__main__":
    main()
