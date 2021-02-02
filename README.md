# RAmiga


Changed
Known partitions:
/dev/sda
  mountpoint: /tmp/berrymiga/dev/sda
  internal_mountpoint: /tmp/berrymiga/dev/sda
  label: BM_DF0

/dev/mmcblk0
  mountpoint: 
  internal_mountpoint: /tmp/berrymiga/dev/mmcblk0
  label: 

/dev/mmcblk0p1
  mountpoint: /boot
  internal_mountpoint: /tmp/berrymiga/dev/mmcblk0p1
  label: boot

/dev/mmcblk0p2
  mountpoint: /
  internal_mountpoint: /tmp/berrymiga/dev/mmcblk0p2
  label: rootfs

dddddddddddddd
New mounted /dev/sda
Traceback (most recent call last):
  File "berrymiga.py", line 362, in <module>
    insert_mounted(partitions, old_partitions)
  File "berrymiga.py", line 195, in insert_mounted
    if insert_mounted_floppy(key, value, force):
  File "berrymiga.py", line 179, in insert_mounted_floppy
    assign_floppy_from_mountpoint(ipartition_data['mountpoint'])
  File "berrymiga.py", line 205, in assign_floppy_from_mountpoint
    for file in os.listdir(mountpoint):
OSError: [Errno 74] Bad message: '/tmp/berrymiga/dev/sda'




sudo mkdosfs -F 12 -n BM_DF0 /dev/sdb



./amiberry -m a1200 -G -c 8192 -F 8192 -s amiberry.gfx_correct_aspect=0 -s gfx_fullscreen_amiga=true -s gfx_fullscreen_picasso=true -s gfx_center_horizontal=smart -s gfx_center_vertical=smart -s amiberry.gfx_auto_height=true


./amiberry -m a1200 -G -c 8192 -F 8192 -s amiberry.gfx_correct_aspect=0 -s gfx_fullscreen_amiga=true -s gfx_fullscreen_picasso=true -s gfx_center_horizontal=smart -s gfx_center_vertical=smart -0 /tmp/berrymiga/dev/sda/Traps\ n\ Treasures\ \(1993\)\(Starbyte\)\(En\)\[cr\ PSG\]\(Disk\ 1\ of\ 2\).adf

./amiberry -m a1200 -G -c 8192 -F 8192 -r bios/Kickstart3.1.rom -s amiberry.gfx_correct_aspect=0 -s gfx_fullscreen_amiga=true -s gfx_fullscreen_picasso=true -s gfx_center_horizontal=smart -s gfx_center_vertical=smart

./fs-uae --fullscreen --smoothing=1 --amiga-model=a1200 --kickstarts_dir=bios --writable_floppy_images=1 --chip_memory=8192 --fast_memory=8192 --floppy_drive_count=4 --disable_f12_key=1 --disable_mod_key=1 --disable_on_screen_keyboard=1 --disable_menu_key_info=1 --disable_keyboard_shortcuts=1 --enable_stretch_mode=1 --disable_cursor_notice=1 --disable_vsync_notice=1 --floppy_drive_volume=0


./fs-uae --fullscreen --stretch=1 --zoom=auto --smoothing=1 --amiga-model=a1200 --floppy-drive-0=rom --kickstarts_dir=bios

./fs-uae --fullscreen --stretch=1 --zoom=auto --smoothing=1 --amiga-model=a1200 --kickstarts_dir=bios --floppy-drive-0=games/Traps\ n\ Treasures\ \(1993\)\(Starbyte\)\(En\)\[cr\ PSG\]\(Disk\ 1\ of\ 2\).adf

./fs-uae --fullscreen --stretch=1 --zoom=auto --smoothing=1 --amiga-model=a1200 --kickstarts_dir=bios --writable_floppy_images=1

./fs-uae --fullscreen --stretch=1 --zoom=auto --smoothing=1 --amiga-model=a1200 --kickstarts_dir=bios --writable_floppy_images=1 --floppy-drive-0=games/Traps\ n\ Treasures\ \(1993\)\(Starbyte\)\(En\)\[cr\ PSG\]\(Disk\ 1\ of\ 2\).adf --floppy-image-0=games/Traps\ n\ Treasures\ \(1993\)\(Starbyte\)\(En\)\[cr\ PSG\]\(Disk\ 1\ of\ 2\).adf --floppy-image-1=games/Traps\ n\ Treasures\ \(1993\)\(Starbyte\)\(En\)\[cr\ PSG\]\(Disk\ 2\ of\ 2\).adf > log2
