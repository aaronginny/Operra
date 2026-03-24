import os
import shutil

src = r"D:\Operra project\ai_ops_assistant\app\static\index.html"
dst = r"D:\Operra project\ai_ops_assistant\app\static\dashboard\index.html"

if os.path.exists(src):
    shutil.copyfile(src, dst)
    # Empty it
    with open(src, "w") as f:
        f.write("")
    print("Copied and emptied!")
else:
    print("Src not found:", src)
