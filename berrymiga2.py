import sys

assert sys.platform == 'linux', "This script must be run only on Linux"
assert sys.version_info.major >= 3 and sys.version_info.minor >= 5, "This script requires Python 3.5+"

try:
    import pyudev
    import psutil
    import sh
    import time
    import os
    import tempfile
    import sys
    import fnmatch
    import re
    import psutil
    import subprocess

    from pprint import pprint
    from collections import OrderedDict
    from typing import Optional
    from io import StringIO
    from pynput.keyboard import Key, Listener
except ImportError as xie:
    print(xie)
    sys.exit(1)


APP_UNIXNAME = 'berrymiga'
OWN_MOUNT_POINT_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
EMULATOR_EXE_PATHNAME = 'amiberry'
EMULATOR_TMP_INI_PATHNAME = os.path.join(os.path.dirname(os.path.realpath(EMULATOR_EXE_PATHNAME)), 'amiberry.tmp.ini')
MAX_FLOPPIES = 4
MAX_DRIVES = 10
EMULATOR_RUN_PATTERN = '{executable} -m a1200 -G -s amiberry.gfx_correct_aspect=0 -s gfx_width=720 -s gfx_width_windowed=720 -s gfx_height=568 -s gfx_height_windowed=568 -s gfx_fullscreen_amiga=false -s gfx_fullscreen_picasso=false -s gfx_fullscreen_amiga=fullwindow -s gfx_fullscreen_picasso=fullwindow -c 2048 -s joyport1=none -s chipset=aga -s finegrain_cpu_speed=1024 -r kickstarts/Kickstart3.1.rom {floppies} {drives} {cdimage}'
# EMULATOR_RUN_PATTERN = '{executable} -m a1200 -G -s amiberry.gfx_correct_aspect=0 -s gfx_width=720 -s gfx_width_windowed=720 -s gfx_fullscreen_amiga=false -s gfx_fullscreen_picasso=false -s gfx_fullscreen_amiga=fullwindow -s gfx_fullscreen_picasso=fullwindow -c 2048 -s joyport1=none -s chipset=aga -s finegrain_cpu_speed=1024 -r kickstarts/Kickstart3.1.rom -s amiberry.open_gui=none -s magic_mouse=none {floppies} {cdimage}'
# EMULATOR_RUN_PATTERN = '{executable} -m a1200 -G -c 8192 -F 8192 -s amiberry.gfx_correct_aspect=0 -s gfx_fullscreen_amiga=true -s gfx_fullscreen_picasso=true -s gfx_center_horizontal=smart -s gfx_center_vertical=smart -s amiberry.gfx_auto_height=true -s joyport1=none -s chipset=aga -s finegrain_cpu_speed=1024 -r kickstarts/Kickstart3.1.rom -s amiberry.open_gui=none {floppies} {cdimage}'
# EMULATOR_RUN_PATTERN = '-m a1200 -G -c 8192 -F 8192 -s amiberry.gfx_correct_aspect=0 -s gfx_fullscreen_amiga=true -s gfx_fullscreen_picasso=true -s gfx_center_horizontal=smart -s gfx_center_vertical=smart -s amiberry.gfx_auto_height=true -s joyport1=none -s chipset=aga -s finegrain_cpu_speed=1024 -r kickstarts/Kickstart3.1.rom -s amiberry.open_gui=none {floppies} {cdimage}'
AUTORUN_EMULATOR = True

floppies = [None for x in range(MAX_FLOPPIES)]
drives = [None for x in range(MAX_DRIVES)]
commands = []

partitions = None
old_partitions = None
key_ctrl_pressed = False
key_alt_pressed = False
key_delete_pressed = False

os.makedirs(OWN_MOUNT_POINT_PREFIX, exist_ok=True)


def check_pre_requirements():
    check_emulator()
    check_system_binaries()


def check_emulator():
    global EMULATOR_EXE_PATHNAME

    emu_real_pathname = os.path.realpath(EMULATOR_EXE_PATHNAME)

    if not os.path.exists(emu_real_pathname):
        print('Emulator executable ' + EMULATOR_EXE_PATHNAME + ' does not exists')
        sys.exit(1)

    EMULATOR_EXE_PATHNAME = emu_real_pathname


def check_system_binaries():
    bins = [
        'sync',
        'echo',
        'fsck',
        'mount',
        'umount',
        'chmod',
        'killall',
        'lsblk',
        'fincore'
    ]

    for ibin in bins:
        if not sh.which(ibin):
            print(ibin + ': command not found')
            sys.exit(1)


def get_partitions2() -> OrderedDict:
    lsblk_buf = StringIO()
    pattern = r'NAME="(\w*)" SIZE="(\d{0,}.\d{0,}[G|M|K])" TYPE="(\w*)" MOUNTPOINT="(.*)" LABEL="(.*)"'
    ret = OrderedDict()

    sh.lsblk('-P', '-o', 'name,size,type,mountpoint,label', '-n', _out=lsblk_buf)

    for line in lsblk_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        found = re.search(pattern,line).groups()

        full_path = os.path.join(os.path.sep, 'dev', found[0])
        device_data = {
            'mountpoint': found[3],
            'internal_mountpoint': os.path.join(
                OWN_MOUNT_POINT_PREFIX,
                get_relative_path(full_path)
            ),
            'label': found[4]
        }

        ret[full_path] = device_data

    return ret


def get_relative_path(pathname: str) -> str:
    if pathname[0] == os.path.sep:
        return pathname[1:]

    return pathname


def print_partitions(partitions: dict):
    if not partitions:
        return

    print('Known partitions:')

    for key, value in partitions.items():
        print(key)

        print('  mountpoint: ' + str(value['mountpoint']))
        print('  internal_mountpoint: ' + value['internal_mountpoint'])
        # print('  removable: ' + str(value['removable']))
        print('  label: ' + str(value['label']))

        print()


def print_attached_floppies():
    print('Attached floppies:')

    for idf_index, ifloppy_data in enumerate(floppies):
        if not ifloppy_data:
            continue

        print('DF{index}: {pathname}'.format(
            index=idf_index,
            pathname=ifloppy_data['pathname']
        ))


def print_attached_hard_disks():
    print('Attached hard disks:')

    for ihd_no, ihd_data in enumerate(drives):
        if not ihd_data:
            continue

        print('DH{index}: {pathname}'.format(
            index=ihd_no,
            pathname=ihd_data['pathname']
        ))


def print_commands():
    if not commands:
        return

    print('Commands:')

    for index, icmd in enumerate(commands):
        print('cmd{index}={cmd}'.format(
            index=index,
            cmd=icmd
        ))


def send_SIGUSR1_signal():
    print('Sending SIGUSR1 signal to Amiberry emulator')

    try:
        sh.killall('-USR1', 'amiberry')
    except sh.ErrorReturnCode_1:
        print('No process found')


def execute_commands():
    global commands

    if not commands:
        return

    contents = '[commands]\n'

    for index, icmd in enumerate(commands):
        contents += 'cmd{index}={cmd}\n'.format(
            index=index,
            cmd=icmd
        )

    commands = []

    print(EMULATOR_TMP_INI_PATHNAME + ' contents:')
    print(contents)

    with open(EMULATOR_TMP_INI_PATHNAME, 'w+', newline=None) as f:
        f.write(contents)

    send_SIGUSR1_signal()


def mount_partitions(partitions: dict) -> list:
    mounted = []

    for key, value in partitions.items():
        if value['mountpoint']:
            continue

        if not is_floppy_label(value['label']) and not is_hard_drive_label(value['label']):
            continue

        print('Mounting ' + key + ' as ' + value['internal_mountpoint'])

        os.makedirs(value['internal_mountpoint'], exist_ok=True)

        force_fsck(key)
        force_all_rw(key)

        sh.mount(key, '-ouser,umask=0000', value['internal_mountpoint'])

        partitions[key]['mountpoint'] = value['internal_mountpoint']

        mounted.append(key)

    return mounted


def unmount_partitions(partitions: dict, old_partitions: dict):
    unmounted = []

    if old_partitions:
        for iold_part_dev, iold_part_data in old_partitions.items():
            if iold_part_dev not in partitions:
                unmounted.append(iold_part_dev)
            else:
                if iold_part_data['mountpoint']:
                    if not partitions[iold_part_dev]['mountpoint']:
                        unmounted.append(iold_part_dev)

    for idevice in unmounted:
        force_umount(idevice)

        if idevice in partitions:
            partitions[idevice]['mountpoint'] = ''

    return unmounted


def is_floppy_label(label: str) -> bool:
    if len(label) != 6:
        return False

    if not label.startswith('BM_DF'):
        return False

    if not label[5].isdigit():
        return False

    return True


def is_hard_drive_label(label: str) -> bool:
    if len(label) != 6:
        return False

    if not label.startswith('BM_DH'):
        return False

    if not label[5].isdigit():
        return False

    return True


def get_label_floppy_index(label: str):
    return int(label[5])


def get_label_hard_disk_index(label: str):
    return int(label[5])


def force_umount(pathname: str):
    try:
        sh.umount('-l', pathname)
    except (sh.ErrorReturnCode_1, sh.ErrorReturnCode_32) as x:
        print(str(x))
        print('Failed to force-umount ' + pathname + ', maybe it is umounted already')


def force_fsck(pathname: str):
    try:
        sh.fsck('-y', pathname)
    except (sh.ErrorReturnCode_1, sh.ErrorReturnCode_6) as x:
        print(str(x))
        print('Failed to force-fsck ' + pathname)


def force_all_rw(pathname: str):
    try:
        sh.chmod('-R', 'a+rw', pathname)
    except sh.ErrorReturnCode_1 as x1:
        print(str(x1))
        print('Failed to chmod a+rw ' + pathname)


def process_new_mounted(partitions: dict, new_mounted: list):
    attached = []

    for idevice in new_mounted:
        ipart_data = partitions[idevice]

        if not ipart_data['mountpoint']:
            continue

        if is_floppy_label(ipart_data['label']):
            if attach_mountpoint_floppy(idevice, ipart_data):
                attached.append(idevice)
        elif is_hard_drive_label(ipart_data['label']):
            if attach_mountpoint_hard_disk(idevice, ipart_data):
                attached.append(idevice)

    return attached


def attach_mountpoint_hard_disk(ipart_dev, ipart_data):
    global drives

    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    hd_no = get_label_hard_disk_index(ipart_data['label'])

    if not drives[hd_no] or drives[hd_no]['pathname'] != mountpoint:
        print('Attaching "{mountpoint}" to DH{index}'.format(
            mountpoint=mountpoint,
            index=hd_no
        ))

        drives[hd_no] = {
            'pathname': mountpoint,
            'mountpoint': ipart_data['mountpoint'],
            'label': ipart_data['label'],
            'device': ipart_dev
        }

        put_command('ext_hd_disk_dir_attach DH{index},{mountpoint},1'.format(
            index=hd_no,
            mountpoint=mountpoint
        ))

        return True
    else:
        print('DH{index} already attached'.format(
            index=hd_no
        ))

    return False


# def attach_mounted_hard_drive(ipartition: str, ipartition_data, force: Optional[bool] = False):
#     new_mounted = False

#     if not old_partitions:
#         new_mounted = True

#     if not new_mounted:
#         if ipartition not in old_partitions:
#             new_mounted = True

#         if not new_mounted:
#             for key2, value2 in old_partitions.items():
#                 if key2 == ipartition and (not value2['mountpoint'] or not value2['label']):
#                     new_mounted = True
#                     break

#     if force:
#         new_mounted = True

#     if new_mounted:
#         print('New mounted ' + ipartition)

#         try:
#             sh.chmod('-R', 'a+rw', ipartition_data['mountpoint'])
#         except sh.ErrorReturnCode_1 as x1:
#             print(str(x1))

#         hd_no = int(ipartition_data['label'][5])

#         if not drives[hd_no] or drives[hd_no]['pathname'] != ipartition:
#             print('Assigning "' + ipartition + '" to DH' + str(hd_no))

#             drives[hd_no] = {
#                 'pathname': ipartition_data['mountpoint'],
#                 'mountpoint': ipartition_data['mountpoint'],
#                 'label': ipartition_data['label']
#             }

#         return True

#     return False


def process_unmounted(unmounted: list):
    global floppies
    global drives

    detached = []

    for idevice in unmounted:
        for idf_index, ifloppy_data in enumerate(floppies):
            if not ifloppy_data:
                continue

            if ifloppy_data['device'] == idevice:
                print('Detaching "{pathname}" from DF{index}'.format(
                    pathname=ifloppy_data['pathname'],
                    index=idf_index
                ))

                floppies[idf_index] = None

                put_command('ext_disk_eject {index}'.format(
                    index=idf_index
                ))

                detached.append(idevice)

        for idh_no, ihd_data in enumerate(drives):
            if not ihd_data:
                continue

            if ihd_data['device'] == idevice:
                print('Detaching "{pathname}" from DH{index}'.format(
                    pathname=ihd_data['pathname'],
                    index=idh_no
                ))

                drives[idh_no] = None

                put_command('ext_hd_disk_dir_detach {index}'.format(
                    index=idh_no
                ))
                put_command('uae_reset 0,0')

                detached.append(idevice)

    return detached


def attach_mountpoint_floppy(ipart_dev, ipart_data):
    adfs = []
    mountpoint = ipart_data['mountpoint']

    for file in os.listdir(mountpoint):
        file_lower = file.lower()

        if not fnmatch.fnmatch(file_lower, '*.adf'):
            continue

        adfs.append(os.path.join(mountpoint, file))

    adfs = sorted(adfs)

    if adfs:
        index = get_label_floppy_index(ipart_data['label'])

        if not floppies[index] or floppies[index]['pathname'] != adfs[0]:
            print('Attaching "{pathname}" to DF{index}'.format(
                pathname=adfs[0],
                index=index
            ))

            floppies[index] = {
                'pathname': adfs[0],
                'mountpoint': mountpoint,
                'device': ipart_dev,
                'file_size': os.path.getsize(adfs[0]),
                'last_access_ts': 0,
                'last_cached_size': 0
            }

            put_command('ext_disk_insert_force {df_no},{pathname},0'.format(
                df_no=index,
                pathname=adfs[0]
            ))

            return True
        else:
            print('Floppy already attached to DF{index}, eject it first'.format(
                index=index
            ))

    return False


def clear_system_cache(force = False):
    print('Clearing system cache')

    os.system('sync')
    os.system('echo 1 > /proc/sys/vm/drop_caches')
    os.system('sync')


def put_command(command: str, reset: bool = False):
    """
    # ext_disk_eject <df_no>
    # ext_disk_insert_force <df_no>,<pathname>,<1/0 write protected>
    # uae_reset <1/0>,<1/0>
    # uae_quit
    # ext_hd_disk_dir_detach <hd_no>
    # ext_hd_disk_dir_attach <device_name>,<pathname>,<1/0 bootable>
    """
    global commands

    if commands:
        if commands[len(commands) - 1] == command:
            # do not add same command
            return

    commands.append(command)


def is_emulator_running():
    for iprocess in psutil.process_iter(attrs=['exe']):
        if iprocess.info['exe'] == EMULATOR_EXE_PATHNAME:
            return True

    return False


def run_emulator():
    global floppies

    print('Running emulator')

    # assign floppies via command line
    str_floppies = ''
    str_drives = ''

    for index, ifloppy in enumerate(floppies):
        if ifloppy:
            str_floppies += r' -{index} "{pathname}"'.format(index=index, pathname=ifloppy['pathname'])

    drive_index = 0
    for index, idrive in enumerate(drives):
        if idrive:
            str_drives += ' -s uaehf{drive_index}=dir,rw,DH{drive_index}:{label}:{pathname},0 '.format(
                drive_index=drive_index,
                label=idrive['label'].replace('BM_', ''),
                pathname=idrive['pathname']
            )
            str_drives += ' -s filesystem2=rw,DH{drive_index}:{label}:{pathname},0 '.format(
                drive_index=drive_index,
                label=idrive['label'].replace('BM_', ''),
                pathname=idrive['pathname']
            )

            # -s uaehf0=dir,rw,DH0:DH0:/home/pi/projects.local/,0 -s uaehf1=dir,rw,DH1:BM_DH0:/media/pi/BM_DH0/,0 -s filesystem2=rw,DH0:DH0:/home/pi/projects.local/,0 -s filesystem2=rw,DH1:DH1:/media/pi/BM_DH0/,0
            drive_index += 1

    pattern = EMULATOR_RUN_PATTERN.format(
        executable=EMULATOR_EXE_PATHNAME,
        floppies=str_floppies.strip(),
        drives=str_drives.strip(),
        cdimage=''
    )

    print('Emulator command line: ' + pattern)

    subprocess.Popen(pattern, cwd=os.path.dirname(EMULATOR_EXE_PATHNAME), shell=True)

    time.sleep(0)


def on_key_press(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed

    if key == Key.ctrl:
        key_ctrl_pressed = True

    if key == Key.alt:
        key_alt_pressed = True

    if key == Key.delete:
        key_delete_pressed = True

    if key_ctrl_pressed and key_alt_pressed and key_delete_pressed:
        key_ctrl_pressed = False
        key_alt_pressed = False
        key_delete_pressed = False

        put_command('uae_reset 0,0')


def on_key_release(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed

    if key == Key.ctrl:
        key_ctrl_pressed = False

    if key == Key.alt:
        key_alt_pressed = False

    if key == Key.delete:
        key_delete_pressed = False


check_pre_requirements()

keyboard_listener = Listener(on_press=on_key_press, on_release=on_key_release)
keyboard_listener.start()

while True:
    unmounted = []
    new_mounted = []
    new_attached = []
    new_detached = []
    # commands = []

    partitions = get_partitions2()

    unmounted = unmount_partitions(partitions, old_partitions)

    if unmounted:
        print('Unmounted partitions')

        new_detached = process_unmounted(unmounted)

    # mount new BM partitions
    new_mounted = mount_partitions(partitions)

    if new_mounted:
        print('Mounted new partitions')

        new_attached = process_new_mounted(partitions, new_mounted)

    if unmounted or new_mounted or new_attached or new_detached:
        # print('unmounted', unmounted)
        # print('new_mounted', new_mounted)
        # print('new_attached', new_attached)
        # print('new_detached', new_detached)

        # something changed
        print_partitions(partitions)
        print_attached_floppies()
        print_attached_hard_disks()

        clear_system_cache()

    old_partitions = partitions

    print_commands()

    if commands:
        execute_commands()
        clear_system_cache()

    if AUTORUN_EMULATOR:
        if not is_emulator_running():
            run_emulator()

    os.system('sync')
    time.sleep(1)








































































# def check_pre_requirements():
#     check_emulator()
#     check_system_binaries()


# def check_emulator():
#     global EMULATOR_EXE_PATHNAME

#     emu_real_pathname = os.path.realpath(EMULATOR_EXE_PATHNAME)

#     if not os.path.exists(emu_real_pathname):
#         print('Emulator executable ' + EMULATOR_EXE_PATHNAME + ' does not exists')
#         sys.exit(1)

#     EMULATOR_EXE_PATHNAME = emu_real_pathname


# def check_system_binaries():
#     bins = [
#         'sync',
#         'echo',
#         'fsck',
#         'mount',
#         'umount',
#         'chmod',
#         'killall',
#         'lsblk',
#         'fincore'
#     ]

#     for ibin in bins:
#         if not sh.which(ibin):
#             print(ibin + ': command not found')
#             sys.exit(1)


# def is_emulator_running():
#     for iprocess in psutil.process_iter(attrs=['exe']):
#         if iprocess.info['exe'] == EMULATOR_EXE_PATHNAME:
#             return True

#     return False


# def run_emulator():
#     global floppies

#     print('Running emulator')

#     # assign floppies via command line
#     str_floppies = ''
#     str_drives = ''

#     for index, ifloppy in enumerate(floppies):
#         if ifloppy:
#             str_floppies += r' -{index} "{pathname}"'.format(index=index, pathname=ifloppy['pathname'])

#     drive_index = 0
#     for index, idrive in enumerate(drives):
#         if idrive:
#             str_drives += ' -s uaehf{drive_index}=dir,rw,DH{drive_index}:{label}:{pathname},0 '.format(
#                 drive_index=drive_index,
#                 label=idrive['label'].replace('BM_', ''),
#                 pathname=idrive['pathname']
#             )
#             str_drives += ' -s filesystem2=rw,DH{drive_index}:{label}:{pathname},0 '.format(
#                 drive_index=drive_index,
#                 label=idrive['label'].replace('BM_', ''),
#                 pathname=idrive['pathname']
#             )

#             # -s uaehf0=dir,rw,DH0:DH0:/home/pi/projects.local/,0 -s uaehf1=dir,rw,DH1:BM_DH0:/media/pi/BM_DH0/,0 -s filesystem2=rw,DH0:DH0:/home/pi/projects.local/,0 -s filesystem2=rw,DH1:DH1:/media/pi/BM_DH0/,0
#             drive_index += 1

#     pattern = EMULATOR_RUN_PATTERN.format(
#         executable=EMULATOR_EXE_PATHNAME,
#         floppies=str_floppies.strip(),
#         drives=str_drives.strip(),
#         cdimage=''
#     )

#     print('Emulator command line: ' + pattern)

#     subprocess.Popen(pattern, cwd=os.path.dirname(EMULATOR_EXE_PATHNAME), shell=True)

#     time.sleep(0)


# def get_relative_path(pathname: str) -> str:
#     if pathname[0] == os.path.sep:
#         return pathname[1:]

#     return pathname


# def get_partition_label(raw_partitions, device_pathname: str, default: str) ->  Optional[str]:
#     for ipartition in raw_partitions:
#         if ipartition.device_node == device_pathname:
#             return ipartition.get('ID_FS_LABEL', '')
    
#     return default


# def is_floppy_label(label: str) -> bool:
#     if len(label) != 6:
#         return False

#     if not label.startswith('BM_DF'):
#         return False

#     if not label[5].isdigit():
#         return False

#     return True


# def is_hard_drive_label(label: str) -> bool:
#     if len(label) != 6:
#         return False

#     if not label.startswith('BM_DH'):
#         return False

#     if not label[5].isdigit():
#         return False

#     return True


# def mount_partitions(partitions: dict) -> list:
#     # just mount new removable drives (as partitions)
#     mounted = []

#     for key, value in partitions.items():
#         if value['mountpoint']:
#             continue

#         if not is_floppy_label(value['label']) and not is_hard_drive_label(value['label']):
#             continue

#         print('Mounting ' + key + ' as ' + value['internal_mountpoint'])

#         os.makedirs(value['internal_mountpoint'], exist_ok=True)

#         try:
#            sh.fsck('-y', key)
#         except sh.ErrorReturnCode_1 as x1:
#             print(str(x1))
#         except sh.ErrorReturnCode_6 as x2:
#             print(str(x2))

#         sh.mount(key, '-ouser,umask=0000', value['internal_mountpoint'])

#         # partitions[key]['mountpoint'] = value['internal_mountpoint']

#         mounted.append(key)

#     return mounted


# def print_partitions(partitions: dict):
#     if not partitions:
#         return

#     print('Known partitions:')

#     for key, value in partitions.items():
#         print(key)

#         print('  mountpoint: ' + str(value['mountpoint']))
#         print('  internal_mountpoint: ' + value['internal_mountpoint'])
#         # print('  removable: ' + str(value['removable']))
#         print('  label: ' + str(value['label']))

#         print()


# def force_umount(pathname: str):
#     try:
#         sh.umount('-l', pathname)
#     except (sh.ErrorReturnCode_1, sh.ErrorReturnCode_32) as x:
#         print(str(x))
#         print('Failed to force-umount ' + pathname + ', maybe it is umounted already')


# def detach_unmounted(partitions: dict, old_partitions: dict) -> int:
#     # eject all ADFs that file-system is unmounted
#     # but was mounted before
#     count_ejected_floppies = 0
#     count_ejected_hard_drives = 0

#     if not old_partitions:
#         return 0

#     for key, value in old_partitions.items():
#         mounted = True

#         if key not in partitions:
#             mounted = False

#         if mounted:
#             for key2, value2 in partitions.items():
#                 if key2 == key and not value2['mountpoint'] and value['mountpoint']:
#                     mounted = False
#                     break

#         if not mounted:
#             print('Unmounted ' + key)

#             force_umount(key)

#             for index, ifloppy in enumerate(floppies):
#                 if not ifloppy:
#                     continue

#                 if ifloppy['mountpoint'] == value['mountpoint']:
#                     print('Ejecting DF' + str(index))

#                     try:
#                         os.rmdir(ifloppy['mountpoint'])
#                     except FileNotFoundError:
#                         pass

#                     floppies[index] = None

#                     count_ejected_floppies += 1

#             drive_index = 0
#             for index, idrive in enumerate(drives):
#                 if not idrive:
#                     continue

#                 if idrive['mountpoint'] == value['mountpoint']:
#                     print('Detaching DH' + str(drive_index))

#                     try:
#                         os.rmdir(idrive['mountpoint'])
#                     except FileNotFoundError:
#                         pass

#                     drives[index] = None

#                     count_ejected_hard_drives += 1
#                     drive_index += 1

#     if count_ejected_hard_drives:
#         generate_soft_reset()
#         send_SIGUSR1_signal()
#         clear_system_cache(True)

#     return count_ejected_floppies + count_ejected_hard_drives


# def detach_unmounted_drives(partitions: dict, old_partitions: dict) -> int:
#     # eject all ADFs that file-system is unmounted
#     # but was mounted before
#     count_ejected = 0

#     if not old_partitions:
#         return count_ejected

#     for key, value in old_partitions.items():
#         mounted = True

#         if key not in partitions:
#             mounted = False

#         if mounted:
#             for key2, value2 in partitions.items():
#                 if key2 == key and not value2['mountpoint'] and value['mountpoint']:
#                     mounted = False
#                     break

#         if not mounted:
#             print('Unmounted ' + key)

#             force_umount(key)

#             drive_index = 0
#             for index, idrive in enumerate(drives):
#                 if not idrive:
#                     continue

#                 if idrive['mountpoint'] == value['mountpoint']:
#                     print('Ejecting DH' + str(drive_index))

#                     drives[index] = None

#                     count_ejected += 1
#                     drive_index += 1

#     return count_ejected


# def insert_mounted_floppy(ipartition: str, ipartition_data, force: Optional[bool] = False):
#     new_mounted = False

#     if not old_partitions:
#         new_mounted = True

#     if not new_mounted:
#         if ipartition not in old_partitions:
#             new_mounted = True

#         if not new_mounted:
#             for key2, value2 in old_partitions.items():
#                 if key2 == ipartition and (not value2['mountpoint'] or not value2['label']):
#                     new_mounted = True
#                     break

#     if force:
#         new_mounted = True

#     if new_mounted:
#         print('New mounted ' + ipartition)

#         try:
#             sh.chmod('-R', 'a+rw', ipartition_data['mountpoint'])
#         except sh.ErrorReturnCode_1 as x1:
#             print(str(x1))

#         assign_floppy_from_mountpoint(ipartition_data['mountpoint'])

#         return True

#     return False


# def attach_mounted_hard_drive(ipartition: str, ipartition_data, force: Optional[bool] = False):
#     new_mounted = False

#     if not old_partitions:
#         new_mounted = True

#     if not new_mounted:
#         if ipartition not in old_partitions:
#             new_mounted = True

#         if not new_mounted:
#             for key2, value2 in old_partitions.items():
#                 if key2 == ipartition and (not value2['mountpoint'] or not value2['label']):
#                     new_mounted = True
#                     break

#     if force:
#         new_mounted = True

#     if new_mounted:
#         print('New mounted ' + ipartition)

#         try:
#             sh.chmod('-R', 'a+rw', ipartition_data['mountpoint'])
#         except sh.ErrorReturnCode_1 as x1:
#             print(str(x1))

#         hd_no = int(ipartition_data['label'][5])

#         if not drives[hd_no] or drives[hd_no]['pathname'] != ipartition:
#             print('Assigning "' + ipartition + '" to DH' + str(hd_no))

#             drives[hd_no] = {
#                 'pathname': ipartition_data['mountpoint'],
#                 'mountpoint': ipartition_data['mountpoint'],
#                 'label': ipartition_data['label']
#             }

#         return True

#     return False


# def attach_mounted(partitions: dict, old_partitions: dict, force: Optional[bool] = False) -> int:
#     # detect new mounted partition and insert ADF
#     # if it is present
#     count_mounted = 0

#     for key, value in partitions.items():
#         if not value['mountpoint']:
#             continue

#         if is_floppy_label(value['label']):
#             if insert_mounted_floppy(key, value, force):
#                 count_mounted += 1
#         elif is_hard_drive_label(value['label']):
#             if attach_mounted_hard_drive(key, value, force):
#                 count_mounted += 1

#     return count_mounted


# def insert_mounted_floppies(partitions: dict, old_partitions: dict, force: Optional[bool] = False) -> bool:
#     # detect new mounted partition and insert ADF
#     # if it is present
#     for key, value in partitions.items():
#         if not value['mountpoint']:
#             continue

#         if is_floppy_label(value['label']):
#             if insert_mounted_floppy(key, value, force):
#                 return True

#     return False


# def attach_mounted_drives(partitions: dict, old_partitions: dict, force: Optional[bool] = False) -> bool:
#     # detect new mounted partition and attach DHx
#     # if it is present

#     for key, value in partitions.items():
#         if not value['mountpoint']:
#             continue

#         if not is_hard_drive_label(value['label']):
#             continue

#         if attach_mounted_hard_drive(key, value, force):
#             return True

#     return False


# def assign_floppy_from_mountpoint(mountpoint: str):
#     roms = []

#     for file in os.listdir(mountpoint):
#         file_lower = file.lower()

#         if not fnmatch.fnmatch(file_lower, '*.adf'):
#             continue

#         roms.append(os.path.join(mountpoint, file))

#     roms = sorted(roms)

#     if roms:
#         if not floppies[0] or floppies[0]['pathname'] != roms[0]:
#             print('Assigning "' + roms[0] + '" to DF0')

#             floppies[0] = {
#                 'pathname': roms[0],
#                 'mountpoint': mountpoint,
#                 'file_size': os.path.getsize(roms[0]),
#                 'last_access_ts': 0,
#                 'last_cached_size': 0
#             }


# def generate_mount_table():
#     cmd_no = 0
#     contents = '[commands]\n'

#     for index, ifloppy in enumerate(floppies):
#         contents += 'cmd' + str(cmd_no) + '=ext_disk_eject ' + str(index) + '\n'
#         cmd_no += 1

#         if ifloppy:
#             contents += 'cmd' + str(cmd_no) + '=ext_disk_insert_force ' + str(index) + ',' + ifloppy['pathname'] + ',0\n'
#             cmd_no += 1

#     print(EMULATOR_TMP_INI_PATHNAME + ' contents:')
#     print(contents)

#     with open(EMULATOR_TMP_INI_PATHNAME, 'w+', newline=None) as f:
#         f.write(contents)


# def generate_soft_reset():
#     contents = '[commands]\n'
#     contents += 'cmd0=uae_reset 0,0\n'

#     print(EMULATOR_TMP_INI_PATHNAME + ' contents:')
#     print(contents)

#     with open(EMULATOR_TMP_INI_PATHNAME, 'w+', newline=None) as f:
#         f.write(contents)


# def generate_quit():
#     contents = '[commands]\n'
#     contents += 'cmd0=uae_quit\n'

#     print(EMULATOR_TMP_INI_PATHNAME + ' contents:')
#     print(contents)

#     with open(EMULATOR_TMP_INI_PATHNAME, 'w+', newline=None) as f:
#         f.write(contents)


# def send_SIGUSR1_signal():
#     print('Sending SIGUSR1 signal to Amiberry emulator')

#     try:
#         sh.killall('-USR1', 'amiberry')
#     except sh.ErrorReturnCode_1:
#         print('No process found')


# def get_partitions2() -> OrderedDict:
#     lsblk_buf = StringIO()
#     pattern = r'NAME="(\w*)" SIZE="(\d{0,}.\d{0,}[G|M|K])" TYPE="(\w*)" MOUNTPOINT="(.*)" LABEL="(.*)"'
#     ret = OrderedDict()

#     sh.lsblk('-P', '-o', 'name,size,type,mountpoint,label', '-n', _out=lsblk_buf)

#     for line in lsblk_buf.getvalue().splitlines():
#         line = line.strip()

#         if not line:
#             continue

#         found = re.search(pattern,line).groups()

#         full_path = os.path.join(os.path.sep, 'dev', found[0])
#         device_data = {
#             'mountpoint': found[3],
#             'internal_mountpoint': os.path.join(
#                 OWN_MOUNT_POINT_PREFIX,
#                 get_relative_path(full_path)
#             ),
#             'label': found[4]
#         }

#         ret[full_path] = device_data

#     return ret


# def clear_system_cache(force = False):
#     print('Clearing system cache')

#     os.system('sync')
#     #os.system('echo 3 > /proc/sys/vm/drop_caches')
#     os.system('echo 1 > /proc/sys/vm/drop_caches')
#     os.system('sync')


# def from_filesize(spec, si=True):
#     decade = 1000 if si else 1024
#     suffixes = tuple('BKMGTP')

#     num = float(spec[:-1])
#     s = spec[-1]
#     i = suffixes.index(s)

#     for n in range(i):
#         num *= decade

#     return int(num)


# def get_file_cached_size(pathname: str) -> int:
#     fincore_buf = StringIO()

#     try:
#         sh.fincore('-b', pathname, _out=fincore_buf)
#     except sh.ErrorReturnCode_1:
#         return 0

#     for line in fincore_buf.getvalue().splitlines():
#         line = line.strip()

#         if not line:
#             continue

#         line = line.replace('  ', ' ')
#         parts = [ipart.strip() for ipart in line.split(' ', 4) if ipart.strip()]

#         if len(parts) == 4 and parts[3] == pathname:
#             return int(parts[0])

#     return 0


# def check_need_clear_cache() -> bool:
#     ts = int(time.time())

#     for ifloppy in floppies:
#         if not ifloppy:
#             continue

#         file_size = ifloppy['file_size']

#         if not file_size:
#             continue

#         new_cached_size = get_file_cached_size(ifloppy['pathname'])

#         if new_cached_size > ifloppy['last_cached_size']:
#             ifloppy['last_cached_size'] = new_cached_size
#             ifloppy['last_access_ts'] = ts

#         if ifloppy['last_access_ts'] and ts - ifloppy['last_access_ts'] >= 60:
#             if ifloppy['last_cached_size'] >= 99 / 100 * file_size:
#                 print(str(ts - ifloppy['last_access_ts']))
#                 print(ifloppy)

#                 ifloppy['last_cached_size'] = 0
#                 ifloppy['last_access_ts'] = 0

#                 return True

#     return False


# def on_key_press(key):
#     global key_ctrl_pressed
#     global key_alt_pressed
#     global key_delete_pressed

#     if key == Key.ctrl:
#         key_ctrl_pressed = True

#     if key == Key.alt:
#         key_alt_pressed = True

#     if key == Key.delete:
#         key_delete_pressed = True

#     if key_ctrl_pressed and key_alt_pressed and key_delete_pressed:
#         key_ctrl_pressed = False
#         key_alt_pressed = False
#         key_delete_pressed = False

#         # generate_quit()
#         generate_soft_reset()
#         send_SIGUSR1_signal()
#         clear_system_cache()


# def on_key_release(key):
#     global key_ctrl_pressed
#     global key_alt_pressed
#     global key_delete_pressed

#     if key == Key.ctrl:
#         key_ctrl_pressed = False

#     if key == Key.alt:
#         key_alt_pressed = False

#     if key == Key.delete:
#         key_delete_pressed = False



# keyboard_listener = Listener(on_press=on_key_press, on_release=on_key_release)
# keyboard_listener.start()

# clear_system_cache(True)

# while True:
#     partitions = get_partitions2()

#     if str(old_partitions) != str(partitions):
#         print('Changed')

#         print_partitions(partitions)
#         mount_partitions(partitions)

#         detach_unmounted(partitions, old_partitions)
#         # eject_unmounted_floppies(partitions, old_partitions)
#         # detach_unmounted_drives(partitions, old_partitions)

#         attach_mounted(partitions, old_partitions)
#         # insert_mounted_floppies(partitions, old_partitions)
#         # attach_mounted_drives(partitions, old_partitions)

#         generate_mount_table()
#         send_SIGUSR1_signal()
#         clear_system_cache(True)

#         old_partitions = partitions

#     if not old_partitions:
#         old_partitions = partitions

#     if AUTORUN_EMULATOR:
#         if not is_emulator_running():
#             run_emulator()

#     # if check_need_clear_cache():
#     #     clear_system_cache(True)

#     os.system('sync')

#     time.sleep(1)
