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
    from configparser import ConfigParser
except ImportError as xie:
    print(xie)
    sys.exit(1)


APP_UNIXNAME = 'berrymiga'
OWN_MOUNT_POINT_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
EMULATOR_EXE_PATHNAME = 'amiberry'
EMULATOR_TMP_INI_PATHNAME = os.path.join(os.path.dirname(os.path.realpath(EMULATOR_EXE_PATHNAME)), 'amiberry.tmp.ini')
MAX_FLOPPIES = 4
MAX_DRIVES = 6
EMULATOR_RUN_PATTERN = '{executable} -m a1200 -G -s amiberry.gfx_correct_aspect=0 -s gfx_width=720 -s gfx_width_windowed=720 -s gfx_height=568 -s gfx_height_windowed=568 -s gfx_fullscreen_amiga=false -s gfx_fullscreen_picasso=false -s gfx_fullscreen_amiga=fullwindow -s gfx_fullscreen_picasso=fullwindow -c 2048 -s joyport1=none -s chipset=aga -s finegrain_cpu_speed=1024 -r kickstarts/Kickstart3.1.rom -s amiberry.open_gui=none -s magic_mouse=none {floppies} {drives} {cdimage}'
# EMULATOR_RUN_PATTERN = '{executable} -m a1200 -G -s amiberry.gfx_correct_aspect=0 -s gfx_width=720 -s gfx_width_windowed=720 -s gfx_fullscreen_amiga=false -s gfx_fullscreen_picasso=false -s gfx_fullscreen_amiga=fullwindow -s gfx_fullscreen_picasso=fullwindow -c 2048 -s joyport1=none -s chipset=aga -s finegrain_cpu_speed=1024 -r kickstarts/Kickstart3.1.rom -s amiberry.open_gui=none -s magic_mouse=none {floppies} {cdimage}'
# EMULATOR_RUN_PATTERN = '{executable} -m a1200 -G -c 8192 -F 8192 -s amiberry.gfx_correct_aspect=0 -s gfx_fullscreen_amiga=true -s gfx_fullscreen_picasso=true -s gfx_center_horizontal=smart -s gfx_center_vertical=smart -s amiberry.gfx_auto_height=true -s joyport1=none -s chipset=aga -s finegrain_cpu_speed=1024 -r kickstarts/Kickstart3.1.rom -s amiberry.open_gui=none {floppies} {cdimage}'
# EMULATOR_RUN_PATTERN = '-m a1200 -G -c 8192 -F 8192 -s amiberry.gfx_correct_aspect=0 -s gfx_fullscreen_amiga=true -s gfx_fullscreen_picasso=true -s gfx_center_horizontal=smart -s gfx_center_vertical=smart -s amiberry.gfx_auto_height=true -s joyport1=none -s chipset=aga -s finegrain_cpu_speed=1024 -r kickstarts/Kickstart3.1.rom -s amiberry.open_gui=none {floppies} {cdimage}'
CONFIG_INI_NAME = '.berrymiga.ini'
AUTORUN_EMULATOR = True
AUTOSEND_SIGNAL = True

floppies = [None for x in range(MAX_FLOPPIES)]
drives = [None for x in range(MAX_DRIVES)]
commands = []

partitions = None
old_partitions = None
key_ctrl_pressed = False
key_alt_pressed = False
key_delete_pressed = False
ctrl_alt_del_press_ts = 0

os.makedirs(OWN_MOUNT_POINT_PREFIX, exist_ok=True)


def check_pre_requirements():
    check_emulator()
    check_system_binaries()


def configure_system():
    os.system('swapoff -a')
    os.system('sysctl vm.swappiness=0')
    os.system('sysctl vm.vfs_cache_pressure=200')


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
        'fincore',
        'sysctl',
        'swapoff'
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

        search_result = re.search(pattern, line)

        if not search_result:
            continue

        found = search_result.groups()

        full_path = os.path.join(os.path.sep, 'dev', found[0])
        device_data = {
            'mountpoint': found[3],
            'internal_mountpoint': os.path.join(
                OWN_MOUNT_POINT_PREFIX,
                get_relative_path(full_path)
            ),
            'label': found[4],
            'config': get_mountpoint_config(found[3])
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
    if not AUTOSEND_SIGNAL:
        return

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

        if not is_floppy_label(value['label']) and \
            not is_hard_drive_label(value['label']) and \
            not is_hard_file_label(value['label']):
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


def is_hard_file_label(label: str) -> bool:
    if len(label) != 7:
        return False

    if not label.startswith('BM_HDF'):
        return False

    if not label[6].isdigit():
        return False

    return True


def get_label_floppy_index(label: str):
    return int(label[5])


def get_label_hard_disk_index(label: str):
    return int(label[5])


def get_label_hard_file_index(label: str):
    return int(label[6])


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
        elif is_hard_file_label(ipart_data['label']):
            if attach_mountpoint_hard_file(idevice, ipart_data):
                attached.append(idevice)

    return attached


def has_attached_df0():
    return floppies[0] is not None


def has_attached_dh0():
    return drives[0] is not None


def is_mountpoint_attached(mountpoint: str) -> bool:
    for imedium in floppies + drives:
        if not imedium:
            continue

        if imedium['mountpoint'] == mountpoint:
            return True

    return False


def process_other_mounted_floppy(partitions: dict):
    attached = []

    for ipart_dev, ipart_data in partitions.items():
        if not ipart_data['mountpoint']:
            continue

        if is_mountpoint_attached(ipart_data['mountpoint']):
            continue

        if is_floppy_label(ipart_data['label']):
            if attach_mountpoint_floppy(ipart_dev, ipart_data):
                attached.append(ipart_dev)

    return attached


def process_other_mounted_hard_disk(partitions: dict):
    attached = []

    for ipart_dev, ipart_data in partitions.items():
        if not ipart_data['mountpoint']:
            continue

        if is_mountpoint_attached(ipart_data['mountpoint']):
            continue

        if is_hard_drive_label(ipart_data['label']):
            if attach_mountpoint_hard_disk(ipart_dev, ipart_data):
                attached.append(ipart_dev)

    return attached


def process_other_mounted_hard_file(partitions: dict):
    attached = []

    for ipart_dev, ipart_data in partitions.items():
        if not ipart_data['mountpoint']:
            continue

        if is_mountpoint_attached(ipart_data['mountpoint']):
            continue

        if is_hard_file_label(ipart_data['label']):
            if attach_mountpoint_hard_file(ipart_dev, ipart_data):
                attached.append(ipart_dev)

    return attached


def process_other_mounted(partitions: dict):
    attached = []

    attached += process_other_mounted_floppy(partitions)
    attached += process_other_mounted_hard_disk(partitions)
    attached += process_other_mounted_hard_file(partitions)

    return attached


def attach_mountpoint_hard_disk(ipart_dev, ipart_data):
    global drives

    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    hd_no = get_label_hard_disk_index(ipart_data['label'])

    if hd_no >= MAX_DRIVES:
        return False

    if not drives[hd_no] or drives[hd_no]['pathname'] != mountpoint:
        print('Attaching "{mountpoint}" to DH{index}'.format(
            mountpoint=mountpoint,
            index=hd_no
        ))

        drives[hd_no] = {
            'pathname': mountpoint,
            'mountpoint': ipart_data['mountpoint'],
            'label': ipart_data['label'],
            'device': ipart_dev,
            'config': ipart_data['config'],
            'is_dir': True,
            'is_hdf': False
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


def attach_mountpoint_hard_file(ipart_dev, ipart_data):
    global drives

    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    hdfs = mountpoint_find_files(mountpoint, '*.hdf')

    if not hdfs:
        return False

    first_hdf = hdfs[0]
    hd_no = get_label_hard_file_index(ipart_data['label'])

    if hd_no >= MAX_DRIVES:
        return False

    if not drives[hd_no] or drives[hd_no]['pathname'] != first_hdf:
        print('Attaching "{pathname}" to DH{index} (HDF)'.format(
            pathname=first_hdf,
            index=hd_no
        ))

        drives[hd_no] = {
            'pathname': first_hdf,
            'mountpoint': ipart_data['mountpoint'],
            'label': ipart_data['label'],
            'device': ipart_dev,
            'config': ipart_data['config'],
            'is_dir': False,
            'is_hdf': True
        }

        put_command('ext_hd_disk_file_attach DH{index},{pathname},1'.format(
            index=hd_no,
            pathname=first_hdf
        ))

        return True
    else:
        print('DH{index} (HDF) already attached'.format(
            index=hd_no
        ))

    return False


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

                is_dir = ihd_data['is_dir']

                drives[idh_no] = None

                if is_dir:
                    put_command('ext_hd_disk_dir_detach {index}'.format(
                        index=idh_no
                    ))
                    put_command('uae_reset 0,0')
                else:
                    put_command('ext_hd_disk_file_detach {index}'.format(
                        index=idh_no
                    ))
                    put_command('uae_reset 0,0')

                detached.append(idevice)

    return detached


def mountpoint_find_files(mountpoint: str, pattern: str) -> list:
    files = []

    for ifile in os.listdir(mountpoint):
        file_lower = ifile.lower()

        if not fnmatch.fnmatch(file_lower, pattern):
            continue

        files.append(os.path.join(mountpoint, ifile))

    return sorted(files)


def attach_mountpoint_floppy(ipart_dev, ipart_data):
    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    adfs = mountpoint_find_files(mountpoint, '*.adf')

    if not adfs:
        return False

    first_adf = adfs[0]
    index = get_label_floppy_index(ipart_data['label'])

    if index >= MAX_FLOPPIES:
        return False

    if not floppies[index] or floppies[index]['pathname'] != first_adf:
        print('Attaching "{pathname}" to DF{index}'.format(
            pathname=first_adf,
            index=index
        ))

        floppies[index] = {
            'pathname': first_adf,
            'mountpoint': mountpoint,
            'device': ipart_dev,
            'file_size': os.path.getsize(first_adf),
            'last_access_ts': 0,
            'last_cached_size': 0,
            'config': ipart_data['config']
        }

        put_command('ext_disk_insert_force {df_no},{pathname},0'.format(
            df_no=index,
            pathname=first_adf
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
    Available commands:
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


def get_mountpoint_config(mountpoint: str):
    config_pathname = os.path.join(mountpoint, CONFIG_INI_NAME)

    if not os.path.exists(config_pathname):
        return None

    config = ConfigParser()
    config.read(config_pathname)

    return config


def get_medium_label(medium_data):
    if not medium_data['config']:
        return None

    if 'partition' not in medium_data['config']:
        return None

    if 'label' not in medium_data['config']['partition']:
        return None

    return medium_data['config']['partition']['label']


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
    drive_index = 0

    for index, ifloppy in enumerate(floppies):
        if ifloppy:
            str_floppies += r' -{index} "{pathname}"'.format(index=index, pathname=ifloppy['pathname'])

    for index, idrive in enumerate(drives):
        if idrive:
            if idrive['is_dir']:
                label = get_medium_label(idrive)

                if not label:
                    label = idrive['label'].replace('BM_', '')

                str_drives += ' -s filesystem2=rw,DH{drive_index}:{label}:{pathname},0 '.format(
                    drive_index=drive_index,
                    label=label,
                    pathname=idrive['pathname']
                )
                str_drives += ' -s uaehf{drive_index}=dir,rw,DH{drive_index}:{label}:{pathname},0 '.format(
                    drive_index=drive_index,
                    label=label,
                    pathname=idrive['pathname']
                )

                drive_index += 1
            elif idrive['is_hdf']:
                str_drives += ' -s hardfile2=rw,DH{drive_index}:{pathname},0,0,0,512,0,,uae1,0 '.format(
                    drive_index=drive_index,
                    pathname=idrive['pathname']
                )
                str_drives += ' -s uaehf{drive_index}=hdf,rw,DH{drive_index}:{pathname},0,0,0,512,0,,uae1,0 '.format(
                    drive_index=drive_index,
                    pathname=idrive['pathname']
                )

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


def kill_emulator():
    print('Sending SIGKILL signal to Amiberry emulator')

    try:
        sh.killall('-9', 'amiberry')
    except sh.ErrorReturnCode_1:
        print('No process found')


def on_key_press(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed
    global ctrl_alt_del_press_ts

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

        ctrl_alt_del_press_ts = int(time.time())

        put_command('uae_reset 0,0')
        clear_system_cache()


def on_key_release(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed
    global ctrl_alt_del_press_ts

    if key == Key.ctrl:
        key_ctrl_pressed = False

    if key == Key.alt:
        key_alt_pressed = False

    if key == Key.delete:
        key_delete_pressed = False

    if not key_ctrl_pressed and not key_alt_pressed and not key_delete_pressed:
        ctrl_alt_del_press_ts = 0


check_pre_requirements()
configure_system()

keyboard_listener = Listener(on_press=on_key_press, on_release=on_key_release)
keyboard_listener.start()

clear_system_cache(True)

while True:
    unmounted = []
    new_mounted = []
    new_attached = []
    new_detached = []
    other_attached = []

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

    other_attached = process_other_mounted(partitions)

    if unmounted or new_mounted or new_attached or new_detached or other_attached:
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

    if ctrl_alt_del_press_ts and int(time.time()) - ctrl_alt_del_press_ts >= 3:
        ctrl_alt_del_press_ts = 0

        kill_emulator()

    os.system('sync')
    time.sleep(1)
