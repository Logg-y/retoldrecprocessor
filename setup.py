# This script should NOT BE EXECUTED DIRECTLY
# use "python setup.py build" instead (this is how you correctly invoke cx_freeze)

import os
import shutil
import zipfile
import time
import re
import cx_Freeze

if os.path.isdir("build"):
    shutil.rmtree("build")
	
			
ver = "1.0.0"

build_exe_options = {"include_msvcr":False, "excludes":["distutils", "test"]}

cx_Freeze.setup(name="Recprocessor", version=ver,
				description="Recorded game renamer for Age of Mythology Retold",
				options={"build_exe":build_exe_options},
				executables=[cx_Freeze.Executable("recprocessor.py")])

# Permissions.
time.sleep(5)

buildfilename = os.listdir("build")[0]
os.rename(f"build/{buildfilename}", f"build/recprocessor-{ver}")

# cx_Freeze tries to include a bunch of dlls that Windows users may not have permissions to distribute
# but should be present on any recent system (and available through the MS VC redistributables if not)
# therefore clear them from the distribution

for root, dirs, files in os.walk(f"build/recprocessor-{ver}"):
	for file in files:
		if file.startswith("api-ms") or file in ["ucrtbase.dll", "vcruntime140.dll"]:
			print(f"Strip file {file} from output...")
			os.unlink(os.path.join(root, file))
		elif "api-ms" in file:
			print(f"Not stripping {file}, but maybe should be?")

shutil.copy("LICENSE", f"build/recprocessor-{ver}/LICENSE")
shutil.copy("recprocessor.ini", f"build/recprocessor-{ver}/recprocessor.ini")
shutil.copy("readme.md", f"build/recprocessor-{ver}/readme.md")

# change working dir so the /build folder doesn't end up in the zip
os.chdir("build")

zipf = zipfile.ZipFile(f"recprocessor-{ver}.zip", "w", zipfile.ZIP_DEFLATED)
for root, dirs, files in os.walk(f"recprocessor-{ver}"):
    for file in files:
        zipf.write(os.path.join(root, file))

zipf.close()