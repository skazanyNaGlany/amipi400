import os

atime = os.stat('/mnt/Pinball Dreams (1992)(21st Century)(Disk 1 of 2).adf').st_atime

print(atime)
