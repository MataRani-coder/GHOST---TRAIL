from PIL import Image
import os

img_path = r"C:\Users\lucky\.gemini\antigravity\brain\2566f79a-13f5-48ad-a4b2-dd40d3da9842\sentinel_shield_eye_1781419379413.png"
assets_dir = r"C:\Users\lucky\multi-cam-tracker\assets"

if not os.path.exists(assets_dir):
    os.makedirs(assets_dir)

# Load the generated image
img = Image.open(img_path)

# Convert to RGBA just in case
img = img.convert("RGBA")

# Save as PNG
png_path = os.path.join(assets_dir, "tray_icon.png")
img.save(png_path, format="PNG")

# Save as ICO with multiple sizes for Windows
ico_path = os.path.join(assets_dir, "tray_icon.ico")
img.save(ico_path, format="ICO", sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])

print(f"Successfully saved {png_path} and {ico_path}")
