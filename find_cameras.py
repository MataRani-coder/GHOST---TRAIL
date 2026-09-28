"""Find all available cameras and their indices."""
import cv2

print("Scanning for cameras... please wait\n")
found = []
for i in range(6):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        ret, frame = cap.read()
        status = "WORKING" if ret else "Opens but no frame"
        print(f"  Camera index {i}: {status}")
        found.append(i)
        # Show a preview window for 2 seconds
        if ret:
            cv2.imshow(f"Camera {i} - press any key", frame)
            cv2.waitKey(2000)
            cv2.destroyAllWindows()
    else:
        print(f"  Camera index {i}: Not found")
    cap.release()

print(f"\nAvailable cameras: {found}")
if len(found) >= 2:
    print(f"\nFor config.yaml:")
    print(f"  cam_1 -> source: {found[0]}   (your PC webcam)")
    print(f"  cam_2 -> source: {found[1]}   (likely DroidCam)")
elif len(found) == 1:
    print("\nOnly 1 camera found. Make sure DroidCam client is connected first!")
else:
    print("\nNo cameras found!")
