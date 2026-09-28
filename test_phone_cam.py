"""
Test IP Webcam connection with multiple backends and URLs.
Run this while IP Webcam server is running on your phone.
"""
import cv2
import urllib.request

PHONE_IP = "192.168.1.6"  # correct phone IP seen in DroidCam/OBS
PORT = 8080

urls_to_try = [
    f"http://{PHONE_IP}:{PORT}/video",
    f"http://{PHONE_IP}:{PORT}/videofeed",
    f"http://{PHONE_IP}:{PORT}/mjpeg",
    f"rtsp://{PHONE_IP}:{PORT}/h264_ulaw.sdp",
    f"http://{PHONE_IP}:{PORT}/shot.jpg",
]

print(f"Testing connection to phone at {PHONE_IP}:{PORT}...\n")

# Step 1: Basic HTTP reachability test
print("Step 1: HTTP ping test...")
try:
    response = urllib.request.urlopen(f"http://{PHONE_IP}:{PORT}/", timeout=3)
    print(f"  ✅ Phone is reachable! HTTP status: {response.status}")
except Exception as e:
    print(f"  ❌ Cannot reach phone: {e}")
    print("  → Make sure IP Webcam server is running on your phone!")
    print("  → Make sure both devices are on same WiFi")
    exit()

# Step 2: Try each video URL
print("\nStep 2: Testing video stream URLs...")
for url in urls_to_try:
    print(f"\n  Trying: {url}")
    cap = cv2.VideoCapture(url)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            print(f"  ✅ SUCCESS! This URL works!")
            print(f"\n>>> USE THIS IN config.yaml:")
            print(f'    source: "{url}"')
            cv2.imshow(f"Phone Camera - {url}", frame)
            print("\nPress any key to continue testing...")
            cv2.waitKey(3000)
            cv2.destroyAllWindows()
        else:
            print(f"  ⚠️  Opened but no frames")
    else:
        print(f"  ❌ Could not open")
    cap.release()

print("\nDone! Use whichever URL showed ✅ SUCCESS in config.yaml")
