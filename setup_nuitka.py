# This builds with nuitka, but antivirus vendors are unfortunately not a fan.
# https://www.virustotal.com/gui/file/fce4ae8f3f8099f4cf2cd0a3bc57086f877632bef83695633cec3ba3b2510cbf/detection
# 5/71, not great. Especially since Microsoft is among them

# Nothing I can do about this, it's just unfortunate that AV vendors will flag anything built with these tools as malicious
# (this is a well documented thing, not only with Nuitka but with pyinstaller as well - cx_freeze seems to be okay now which is nice)

# Maybe in the future this will be more reasonable

import os
import shutil
os.system("py -3.12 -m nuitka --mode=standalone recprocessor.py")

shutil.copy("LICENSE", "./recprocessor.dist/LICENSE")
shutil.copy("README.md", "./recprocessor.dist/README.md")
shutil.copy("recprocessor.ini", "./recprocessor.dist/recprocessor.ini")

shutil.make_archive("recprocessor.dist", "zip", root_dir="./recprocessor.dist")


