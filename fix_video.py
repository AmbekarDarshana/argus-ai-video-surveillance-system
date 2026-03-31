# fix_video.py
# Run this: python fix_video.py

import os
import subprocess

# Step 1: Get FFmpeg
print("=" * 50)
print("STEP 1: Finding FFmpeg...")
print("=" * 50)

ffmpeg_path = None

try:
    import imageio_ffmpeg
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    print(f"Found FFmpeg at: {ffmpeg_path}")
except ImportError:
    print("imageio-ffmpeg NOT installed!")
    print("Installing now...")
    os.system("pip install imageio-ffmpeg")
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        print(f"Found FFmpeg at: {ffmpeg_path}")
    except:
        print("FAILED to install. Try manually: pip install imageio-ffmpeg")
        exit(1)

# Step 2: Find all video files
print("\n" + "=" * 50)
print("STEP 2: Finding all video files...")
print("=" * 50)

video_files = []
search_folders = ['uploads', 'static/videos', 'static/recordings']

for folder in search_folders:
    if os.path.isdir(folder):
        files = os.listdir(folder)
        print(f"\n  {folder}/: {files}")
        for f in files:
            if f.endswith(('.mp4', '.avi')):
                full_path = os.path.join(folder, f)
                size_mb = os.path.getsize(full_path) / (1024 * 1024)
                print(f"    -> {f} ({size_mb:.1f} MB)")
                video_files.append(full_path)
    else:
        print(f"\n  {folder}/: DOES NOT EXIST")

if not video_files:
    print("\nNo video files found!")
    exit(0)

# Step 3: Convert each file
print("\n" + "=" * 50)
print(f"STEP 3: Converting {len(video_files)} files...")
print("=" * 50)

success = 0
failed = 0

for video_path in video_files:
    print(f"\nConverting: {video_path}")
    
    output_path = video_path + ".converted.mp4"
    
    cmd = [
        ffmpeg_path, '-y',
        '-i', video_path,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-c:a', 'aac',
        '-movflags', '+faststart',
        output_path
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300
        )
        
        if result.returncode != 0:
            print(f"  FFmpeg error: {result.stderr.decode()[:200]}")
            failed += 1
            if os.path.exists(output_path):
                os.remove(output_path)
            continue
        
        # Check output file
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            old_size = os.path.getsize(video_path)
            new_size = os.path.getsize(output_path)
            
            # Replace original
            os.remove(video_path)
            os.rename(output_path, video_path)
            
            print(f"  SUCCESS! {old_size/1024/1024:.1f}MB -> {new_size/1024/1024:.1f}MB")
            success += 1
        else:
            print(f"  Output file empty or missing")
            failed += 1
            if os.path.exists(output_path):
                os.remove(output_path)
                
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT (took > 5 minutes)")
        failed += 1
        if os.path.exists(output_path):
            os.remove(output_path)
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1
        if os.path.exists(output_path):
            os.remove(output_path)

print("\n" + "=" * 50)
print(f"DONE! Success: {success}, Failed: {failed}")
print("=" * 50)
print("\nNow restart Flask: python run.py")
print("Then try viewing the video again.")