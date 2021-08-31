import sys
import os

assert sys.platform == 'linux', "This script must be run only on Linux"
assert sys.version_info.major >= 3 and sys.version_info.minor >= 5, "This script requires Python 3.5+"
assert os.geteuid() == 0, "This script must be run as root"

try:
    import pyudev
    import psutil
    import sh
    import time
    import tempfile
    import sys
    import fnmatch
    import re
    import psutil
    import subprocess
    import copy
    import logzero
    import string
    import glob

    from pprint import pprint
    from collections import OrderedDict
    from typing import Optional, List
    from io import StringIO
    from pynput.keyboard import Key, Listener
    from configparser import ConfigParser
    from array import array
except ImportError as xie:
    print(str(xie))
    sys.exit(1)


APP_UNIXNAME = 'araamiga'
APP_VERSION = '0.1'
TMP_PATH_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
DEVS_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'dev')
LOG_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'araamiga.log')
INTERNAL_DRIVE_LABEL = 'Internal'
INTERNAL_DRIVE_PERMISSION = 'ro'
INTERNAL_DRIVE_BOOT_PRIORITY = -128     # -128 means not bootable
FLOPPY_DISK_IN_DRIVE_SOUND_VOLUME = 20
FLOPPY_EMPTY_DRIVE_SOUND_VOLUME = 0
ENABLE_FLOPPY_DRIVE_SOUND = 'auto'
ENABLE_HARD_DRIVES = True
ENABLE_INTERNAL_DRIVE = False
ENABLE_LOGGER = False
ENABLE_TURN_OFF_MONITOR = False
ENABLE_CTRL_ALT_DEL_LONG_PRESS_KILL = True
ENABLE_AUDIO_LAG_FIX = True
ENABLE_FORCE_FSCK = 'auto'
ENABLE_FORCE_RW = False
ENABLE_CD_REPLACE_RESTART = False
ENABLE_CD_PERM_FIX = True
ENABLE_MOUSE_UNGRAB = False
ENABLE_F12_OPEN_GUI = False
AUDIO_LAG_STEP_0_SECS = 30
AUDIO_LAG_STEP_1_SECS = 6
SYNC_DISKS_SECS = 60 * 3
EMULATOR_EXE_PATHNAMES = [
    'amiberry',
    '../amiberry/amiberry'
]
EMULATOR_TMP_INI_NAME = 'amiberry.tmp.ini'
MAX_FLOPPIES = 1
MAX_DRIVES = 6
MAX_CD_DRIVES = 1
RE_SIMILAR_ROM = re.compile(r'\(Disk\ \d\ of\ \d\)')
SIMILAR_ROM = '(Disk {index} of {max_index})'
KICKSTART_PATHNAMES = [
    '/boot/araamiga/kickstarts/*.rom',
    '../amiberry/kickstarts/*.rom',
    'kickstarts/*.rom',
]
KICKSTART_EXTENDED_PATHNAMES = [
    '/boot/araamiga/kickstarts/extended/*.rom',
    '../amiberry/kickstarts/extended/*.rom',
    'kickstarts/extended/*.rom',
]
# stock Amiga 1200
# EMULATOR_RUN_PATTERN = '{executable} -G -m A1200 -s amiberry.gfx_correct_aspect=0 -s gfx_width=720 -s gfx_width_windowed=720 -s gfx_height=568 -s gfx_height_windowed=568 -s gfx_fullscreen_amiga=fullwindow -s gfx_fullscreen_picasso=fullwindow -s bsdsocket_emu=true -s nr_floppies={nr_floppies} {config_options} -r "{kickstart}" {extended_kickstart} {floppies} {drives} {cd_drives}'
# stock Amiga 1200 + 8 MB FAST RAM
EMULATOR_RUN_PATTERN = '{executable} -G -m A1200 -s cpu_memory_cycle_exact=false -s fastmem_size=8 -s amiberry.gfx_correct_aspect=0 -s gfx_width=720 -s gfx_width_windowed=720 -s gfx_height=568 -s gfx_height_windowed=568 -s gfx_fullscreen_amiga=fullwindow -s gfx_fullscreen_picasso=fullwindow -s bsdsocket_emu=true -s nr_floppies={nr_floppies} {config_options} -r "{kickstart}" {extended_kickstart} {floppies} {drives} {cd_drives}'
# fastest Amiga 1200
# EMULATOR_RUN_PATTERN = '{executable} -G -m A1200 -s cpu_speed=max -s cpu_type=68040 -s cpu_model=68040 -s fpu_model=68040 -s cpu_24bit_addressing=false -s cpu_memory_cycle_exact=false -s fpu_strict=true -s fastmem_size=8 -s amiberry.gfx_correct_aspect=0 -s gfx_width=720 -s gfx_width_windowed=720 -s gfx_height=568 -s gfx_height_windowed=568 -s gfx_fullscreen_amiga=fullwindow -s gfx_fullscreen_picasso=fullwindow -s bsdsocket_emu=true -s nr_floppies={nr_floppies} {config_options} -r "{kickstart}" {extended_kickstart} {floppies} {drives} {cd_drives}'
# stock Amiga CD32
# EMULATOR_RUN_PATTERN = '{executable} -G -m CD32 -s amiberry.gfx_correct_aspect=0 -s gfx_width=720 -s gfx_width_windowed=720 -s gfx_height=568 -s gfx_height_windowed=568 -s gfx_fullscreen_amiga=fullwindow -s gfx_fullscreen_picasso=fullwindow -s bsdsocket_emu=true -s nr_floppies={nr_floppies} {config_options} -r "{kickstart}" {extended_kickstart} {floppies} {drives} {cd_drives}'
CONFIG_INI_NAME = '.araamiga.ini'
DEFAULT_BOOT_PRIORITY = 0
AUTORUN_EMULATOR = True
AUTOSEND_SIGNAL = True
MONITOR_STATE_ON = 1
MONITOR_STATE_KEEP_OFF = 0
MONITOR_STATE_KEEP_OFF_TO_EMULATOR = 2
HDF_TYPE_HDFRDB = 8
HDF_TYPE_DISKIMAGE = 2
HDF_TYPE_HDF  = 5
FLOPPY_EXTENSIONS = ['*.adf']
CD_EXTENSIONS = ['*.cue', '*.iso', '*.nrg']
HARD_FILE_EXTENSIONS = ['*.hdf']
CD_PERM_FIX_PATHNAME = '/dev/zero'
FLOPPY_DRIVE_READ_A_HEAD_SECTORS = 0
DEFAULT_READ_A_HEAD_SECTORS = 256
WPA_SUPPLICANT_CONF_PATHNAME = 'wpa_supplicant.conf'

floppies = [None for x in range(MAX_FLOPPIES)]
drives = [None for x in range(MAX_DRIVES)]
cd_drives = [None for x in range(MAX_CD_DRIVES)]
drives_changed = False
commands = []

partitions = None
old_partitions = None
key_ctrl_pressed = False
key_alt_pressed = False
key_delete_pressed = False
ctrl_alt_del_press_ts = 0
tab_combo = []
tab_combo_recording = False
tab_pressed = False
emulator_exe_pathname = None
emulator_tmp_ini_pathname = None
kickstart_pathname = None
kickstart_extended_pathname = None
monitor_off_timestamp = 0
monitor_state = MONITOR_STATE_ON
monitor_off_seconds = 0
external_mounted_processed = False
floppy_disk_in_drive_volume = 0
floppy_empty_drive_volume = 0
audio_lag_fix_step = 0
audio_lag_fix_ts = 0
sync_disks_ts = 0
sync_process = None

os.makedirs(TMP_PATH_PREFIX, exist_ok=True)


def print_log(*args):
    if ENABLE_LOGGER:
        if args:
            logzero.logger.info(*args)
    else:
        print(*args)


def init_logger():
    if not ENABLE_LOGGER:
        return

    print('Logging to ' + LOG_PATHNAME)

    logzero.logfile(LOG_PATHNAME, maxBytes=1e6, backupCount=3, disableStderrLogger=True)


def print_app_version():
    print('{name} v{version} control script'. format(
        name=APP_UNIXNAME.upper(),
        version=APP_VERSION
    ))


def check_pre_requirements():
    check_emulator()
    check_kickstart()
    check_extended_kickstart()
    check_system_binaries()


def configure_system():
    print_log('Configuring system')

    disable_swap()
    set_cache_pressure()


def disable_swap():
    print_log('Disable swap')
    os.system('swapoff -a')


def set_cache_pressure():
    print_log('Set cache pressure')
    os.system('sysctl -q vm.vfs_cache_pressure=200')


def configure_tmp_ini():
    global emulator_tmp_ini_pathname

    emulator_tmp_ini_pathname = os.path.join(os.path.dirname(os.path.realpath(emulator_exe_pathname)), EMULATOR_TMP_INI_NAME)


def configure_volumes():
    global floppy_disk_in_drive_volume
    global floppy_empty_drive_volume

    floppy_disk_in_drive_volume = prepare_floppy_drive_volume(FLOPPY_DISK_IN_DRIVE_SOUND_VOLUME)
    floppy_empty_drive_volume = prepare_floppy_drive_volume(FLOPPY_EMPTY_DRIVE_SOUND_VOLUME)


def check_emulator():
    global emulator_exe_pathname

    print_log('Checking emulator')

    for ipathname in EMULATOR_EXE_PATHNAMES:
        irealpath = os.path.realpath(ipathname)

        if os.path.exists(irealpath):
            emulator_exe_pathname = irealpath

            break

    if not emulator_exe_pathname:
        print_log('Emulator executable does not exists, checked {paths}'.format(
            paths=', '.join(EMULATOR_EXE_PATHNAMES)
        ))

        sys.exit(1)

    print_log('Emulator executable: ' + emulator_exe_pathname)


def check_kickstart():
    global kickstart_pathname

    print_log('Checking kickstart')

    for ipathname in KICKSTART_PATHNAMES:
        paths = glob.glob(ipathname)

        if paths:
            kickstart_pathname = paths[0]

            break

    if not kickstart_pathname:
        print_log('Kickstart ROM does not exists, checked:\n{paths}'.format(
            paths='\n'.join(KICKSTART_PATHNAMES)
        ))

        sys.exit(1)

    print_log('Kickstart: ' + kickstart_pathname)


def check_extended_kickstart():
    global kickstart_extended_pathname

    print_log('Checking extended kickstart')

    for ipathname in KICKSTART_EXTENDED_PATHNAMES:
        paths = glob.glob(ipathname)

        if paths:
            kickstart_extended_pathname = paths[0]

            break

    if not kickstart_extended_pathname:
        print_log('Extended kickstart ROM does not exists, checked:\n{paths}'.format(
            paths='\n'.join(KICKSTART_EXTENDED_PATHNAMES)
        ))
    else:
        print_log('Extended kickstart: ' + kickstart_extended_pathname)


def check_system_binaries():
    print_log('Checking system binaries')

    bins = [
        'rmdir',
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
        'swapoff',
        'xset',
        'clear',
        'sh',
        'blockdev',
        'iwconfig',
        'rfkill',
        'wpa_supplicant',
        'rm',
        'ifconfig'
    ]

    for ibin in bins:
        if not sh.which(ibin):
            print_log(ibin + ': command not found')
            sys.exit(1)


def turn_off_monitor():
    if not ENABLE_TURN_OFF_MONITOR:
        return

    os.system('xset dpms force off')


def turn_on_monitor():
    os.system('xset dpms force on')


def keep_monitor_off(seconds: int):
    global monitor_off_timestamp
    global monitor_state
    global monitor_off_seconds
    
    if not ENABLE_TURN_OFF_MONITOR:
        return

    if monitor_state == MONITOR_STATE_KEEP_OFF:
        return

    monitor_off_timestamp = int(time.time())
    monitor_state = MONITOR_STATE_KEEP_OFF
    monitor_off_seconds = seconds


def keep_monitor_off_to_emulator(additional_seconds: int):
    global monitor_off_timestamp
    global monitor_state
    global monitor_off_seconds

    if not ENABLE_TURN_OFF_MONITOR:
        return

    if monitor_state == MONITOR_STATE_KEEP_OFF_TO_EMULATOR:
        return

    monitor_off_timestamp = int(time.time())
    monitor_state = MONITOR_STATE_KEEP_OFF_TO_EMULATOR
    monitor_off_seconds = additional_seconds


def update_monitor_state():
    global monitor_off_timestamp
    global monitor_state
    global monitor_off_seconds

    if monitor_state == MONITOR_STATE_KEEP_OFF:
        seconds = int(time.time()) - monitor_off_timestamp

        if seconds < monitor_off_seconds:
            turn_off_monitor()
        else:
            turn_on_monitor()
            monitor_state = MONITOR_STATE_ON
    elif monitor_state == MONITOR_STATE_KEEP_OFF_TO_EMULATOR:
        if not is_emulator_running():
            return

        keep_monitor_off(monitor_off_seconds)


def ctrl_alt_del_keyboard_action():
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed
    global ctrl_alt_del_press_ts

    if key_ctrl_pressed and key_alt_pressed and key_delete_pressed:
        key_ctrl_pressed = False
        key_alt_pressed = False
        key_delete_pressed = False

        ctrl_alt_del_press_ts = int(time.time())

        put_command('uae_reset 1,1')
        # put_command('uae_reset 0,0')
    elif not key_ctrl_pressed and not key_alt_pressed and not key_delete_pressed:
        ctrl_alt_del_press_ts = 0

    if ENABLE_CTRL_ALT_DEL_LONG_PRESS_KILL:
        if ctrl_alt_del_press_ts and int(time.time()) - ctrl_alt_del_press_ts >= 3:
            ctrl_alt_del_press_ts = 0

            kill_emulator()


def string_unify2(str_to_unify: str, exclude = None) -> str:
    """
    better version of string_unify(), using spaces to separate string parts
    """
    if not exclude:
        exclude = []

    unified = ''

    for ichar in str_to_unify:
        if ichar in exclude:
            unified += ichar
            continue

        ichar = ichar.lower()

        if ichar.isalnum():
            unified += ichar
        else:
            unified += ' '

    unified = unified.strip()
    spaces_pos = unified.find('  ')
    while spaces_pos != -1:
        unified = unified.replace('  ', ' ')
        spaces_pos = unified.find('  ')

    return unified.strip()


def find_similar_file_adf(directory, pattern):
    adfs = mountpoint_find_files(directory, FLOPPY_EXTENSIONS)

    if not adfs:
        return None

    for iadf in adfs:
        basename = os.path.basename(iadf)
        basename_unified = string_unify2(basename)

        if pattern in basename_unified:
            return iadf

        parts = basename_unified.split(' ')
        pattern_copy = copy.copy(pattern)

        for ipart in parts:
            if pattern_copy.find(ipart) == 0:
                pattern_copy = pattern_copy.replace(ipart, '')

                if not pattern_copy:
                    return iadf

    return None


def find_similar_file_cd_image(directory, pattern):
    cd_images = mountpoint_find_files(directory, CD_EXTENSIONS)

    if not cd_images:
        return None

    for icd in cd_images:
        basename = os.path.basename(icd)
        basename_unified = string_unify2(basename)

        if pattern in basename_unified:
            return icd

        parts = basename_unified.split(' ')
        pattern_copy = copy.copy(pattern)

        for ipart in parts:
            if pattern_copy.find(ipart) == 0:
                pattern_copy = pattern_copy.replace(ipart, '')

                if not pattern_copy:
                    return icd

    return None


def find_floppy_first_mountpoint(partitions: dict, floppy_index: int) -> dict:
    for key, value in partitions.items():
        if not is_floppy_label(value['label']):
            continue

        if get_label_floppy_index(value['label']) == floppy_index:
            return value

    return None


def find_cd_first_mountpoint(partitions: dict, cd_index: int) -> dict:
    for key, value in partitions.items():
        if not is_cd_label(value['label']):
            continue

        if get_label_cd_index(value['label']) == cd_index:
            return value

    return None


def process_floppy_replace_action(partitions: dict, action: str):
    idf_index = int(action[2])

    if idf_index + 1 > MAX_FLOPPIES:
        return

    detached_floppy_data = detach_floppy(idf_index)
    floppy_pattern_name = action[3:].strip()

    update_floppy_drive_sound(idf_index)

    if not floppy_pattern_name:
        return

    if detached_floppy_data:
        medium = detached_floppy_data['medium']
    else:
        medium = find_floppy_first_mountpoint(partitions, idf_index)

        if not medium:
            # should not get here
            return

    pathname = find_similar_file_adf(
        medium['mountpoint'],
        floppy_pattern_name
    )

    if not pathname:
        return

    put_local_commit_command(1)

    if attach_mountpoint_floppy(medium['device'], medium, pathname):
        update_floppy_drive_sound(idf_index)


def process_cd_replace_action(partitions: dict, action: str):
    icd_index = int(action[2])

    if icd_index + 1 > MAX_CD_DRIVES:
        return

    detached_cd_data = detach_cd(icd_index)
    cd_pattern_name = action[3:].strip()

    if not cd_pattern_name:
        return

    if detached_cd_data:
        medium = detached_cd_data['medium']
    else:
        medium = find_cd_first_mountpoint(partitions, icd_index)

        if not medium:
            # should not get here
            return

    pathname = find_similar_file_cd_image(
        medium['mountpoint'],
        cd_pattern_name
    )

    if not pathname:
        return

    put_local_commit_command(1)

    attach_mountpoint_cd_image(medium['device'], medium, pathname)


def process_wifi_action(action: str):
    wifi_params = action[4:].strip()

    if not wifi_params:
        disconnect_wifi()

        return

    if not wifi_params.startswith(','):
        return

    parts = wifi_params[1:].split(',')

    if len(parts) != 2:
        return

    parts[0] = parts[0].strip()
    parts[1] = parts[1].strip()

    if not parts[0] or not parts[1]:
        return

    os.system('echo "{password}" | wpa_passphrase "{ssid}" > {config_pathname}'.format(
        password=parts[1],
        ssid=parts[0],
        config_pathname=WPA_SUPPLICANT_CONF_PATHNAME
    ))

    connect_wifi()


def find_similar_roms(rom_path: str) -> list:
    dirname = os.path.dirname(rom_path)
    basename = os.path.basename(rom_path)

    (filename, extension) = os.path.splitext(basename)

    match = RE_SIMILAR_ROM.findall(basename)
    len_match = len(match)

    if len_match != 1:
        return [rom_path]

    (no_disc_filename, count) = RE_SIMILAR_ROM.subn('', basename, 1)
    (clean_filename, extension) = os.path.splitext(no_disc_filename)

    files = glob.glob(os.path.join(dirname, '*' + extension))
    similar = []

    for ifile in files:
        ifile_basename = os.path.basename(ifile)

        if ifile_basename.startswith(clean_filename) and len(RE_SIMILAR_ROM.findall(ifile_basename)) == 1 and ifile_basename.endswith(extension):
            if ifile not in similar:
                similar.append(ifile)

    return sorted(similar)


def process_floppy_replace_by_index_action(action: str):
    global floppies

    idf_index = int(action[2])

    if idf_index + 1 > MAX_FLOPPIES:
        return

    if not floppies[idf_index]:
        return

    action_data = action[3:].strip()

    if not action_data:
        return

    rom_disk_no = int(action_data)
    similar_roms = find_similar_roms(floppies[idf_index]['pathname'])
    len_similar_roms = len(similar_roms)
    to_insert_pathname = None

    for value in similar_roms:
        rom_sign = SIMILAR_ROM.format(
            index=rom_disk_no,
            max_index=len_similar_roms
        )

        if rom_sign in value:
            to_insert_pathname = value

            break

    if to_insert_pathname:
        if floppies[idf_index]['pathname'] == to_insert_pathname:
            return

        detached_floppy_data = detach_floppy(idf_index, True)

        update_floppy_drive_sound(idf_index)

        device = detached_floppy_data['device']
        medium = detached_floppy_data['medium']

        if attach_mountpoint_floppy(device, medium, to_insert_pathname):
            update_floppy_drive_sound(idf_index)


def process_cd_replace_by_index_action(action: str):
    global cd_drives

    icd_index = int(action[2])

    if icd_index + 1 > MAX_CD_DRIVES:
        return

    if not cd_drives[icd_index]:
        return

    action_data = action[3:].strip()

    if not action_data:
        return

    rom_disk_no = int(action_data)
    similar_roms = find_similar_roms(cd_drives[icd_index]['pathname'])
    len_similar_roms = len(similar_roms)
    to_insert_pathname = None

    for value in similar_roms:
        rom_sign = SIMILAR_ROM.format(
            index=rom_disk_no,
            max_index=len_similar_roms
        )

        if rom_sign in value:
            to_insert_pathname = value

            break

    if to_insert_pathname:
        if cd_drives[icd_index]['pathname'] == to_insert_pathname:
            return

        detached_cd_data = detach_cd(icd_index, True)

        device = detached_cd_data['device']
        medium = detached_cd_data['medium']

        attach_mountpoint_cd_image(device, medium, to_insert_pathname)


def process_tab_combo_action(partitions: dict, action: str):
    len_action = len(action)

    # TODO replace df0, df1, ... with MAX_FLOPPIES
    # TODO replace cd0, ... with MAX_CD_DRIVES
    if action.startswith('df0') or action.startswith('df1') or action.startswith('df2') or action.startswith('df4'):
        if len_action >= 4 and len_action <= 5:
            process_floppy_replace_by_index_action(action)

            return

        process_floppy_replace_action(partitions, action)
    elif action.startswith('cd0'):
        if len_action >= 4 and len_action <= 5:
            process_cd_replace_by_index_action(action)

            return

        process_cd_replace_action(partitions, action)
    elif action.startswith('wifi'):
        process_wifi_action(action)


def action_to_str(action: list) -> str:
    action_str = ''

    for c in action:
        try:
            action_str += c.char
        except:
            pass

    return action_str


def tab_combo_actions(partitions: dict):
    global tab_combo

    if len(tab_combo) <= 4:
        return

    if tab_combo[-1] != Key.tab or tab_combo[-2] != Key.tab:
        return

    if tab_combo[0] != Key.tab or tab_combo[1] != Key.tab:
        return

    action_str = action_to_str(tab_combo)
    tab_combo = []

    process_tab_combo_action(partitions, action_str)


def keyboard_actions(partitions: dict):
    ctrl_alt_del_keyboard_action()
    tab_combo_actions(partitions)


def tab_shell():
    if not tab_pressed:
        return

    print_log('')
    print_log('Enter system shell')

    os.system('/bin/sh')
    sys.exit(1)


def other_actions():
    if ENABLE_LOGGER:
        # logger enabled so clear the console
        os.system('clear')


def reset_audio_lag_fix():
    global audio_lag_fix_step
    global audio_lag_fix_ts

    audio_lag_fix_step = 0
    audio_lag_fix_ts = 0


def audio_lag_fix():
    global audio_lag_fix_step
    global audio_lag_fix_ts

    if not ENABLE_AUDIO_LAG_FIX or audio_lag_fix_step == 2:
        # audio lag fix not enabled or already applied
        return

    current_ts = int(time.time())

    if not audio_lag_fix_ts:
        # timestamp not set, use current
        # and return, so we will process it again
        # after 1 second
        audio_lag_fix_ts = current_ts

        return

    applied = False

    if audio_lag_fix_step == 0:
        if current_ts - audio_lag_fix_ts <= AUDIO_LAG_STEP_0_SECS:
            return

        put_command('cfgfile_parse_line_type_all amiberry.sound_pullmode=1')
        put_command('cfgfile_parse_line_type_all sound_max_buff=8192')
        put_command('config_changed 1')

        audio_lag_fix_step += 1
        audio_lag_fix_ts = current_ts
        applied = True
    elif audio_lag_fix_step == 1:
        if current_ts - audio_lag_fix_ts <= AUDIO_LAG_STEP_1_SECS:
            return

        put_command('cfgfile_parse_line_type_all sound_max_buff=16384')
        put_command('config_changed 1')

        audio_lag_fix_step += 1
        audio_lag_fix_ts = current_ts
        applied = True

    if applied:
        print_log('Apply audio lag fix, step={step}'.format(
            step=audio_lag_fix_step - 1
        ))


def is_sync_running() -> bool:
    global sync_process

    if not sync_process:
        return False

    if sync_process.poll() is None:
        return True

    sync_process = None

    return False


def sync():
    global sync_disks_ts
    global sync_process

    if is_sync_running():
        return

    current_ts = int(time.time())

    if not sync_disks_ts:
        sync_disks_ts = current_ts

    if current_ts - sync_disks_ts < SYNC_DISKS_SECS:
        return

    print_log('Syncing disks')

    sync_process = subprocess.Popen('sync')
    sync_disks_ts = current_ts


def get_partitions2() -> OrderedDict:
    lsblk_buf = StringIO()
    pattern = r'NAME="(\w*)" SIZE="(\d{0,}.\d{0,}[G|M|K])" TYPE="(\w*)" MOUNTPOINT="(.*)" LABEL="(.*)"'
    ret = OrderedDict()

    # lsblk -P -o name,size,type,mountpoint,label -n
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
                TMP_PATH_PREFIX,
                get_relative_path(full_path)
            ),
            'label': found[4],
            'config': None,
            'device': full_path,
            'is_floppy_drive': False
        }

        if device_data['mountpoint']:
            device_data['config'] = get_mountpoint_config(device_data['mountpoint'])

        device_data['is_floppy_drive'] = len(found[0]) == 3 and found[0].isalpha() and found[1] == '1.4M' and found[2] == 'disk'

        ret[full_path] = device_data

    return ret


def get_relative_path(pathname: str) -> str:
    if pathname[0] == os.path.sep:
        return pathname[1:]

    return pathname


def print_partitions(partitions: dict):
    if not partitions:
        return

    print_log('Known partitions:')

    for key, value in partitions.items():
        print_log(key)

        print_log('  mountpoint: ' + str(value['mountpoint']))
        print_log('  internal_mountpoint: ' + value['internal_mountpoint'])
        print_log('  label: ' + str(value['label']))
        print_log('  is_floppy_drive: ' + str(value['is_floppy_drive']))

        print_log()


def print_attached_floppies():
    print_log('Attached floppies:')

    for idf_index, ifloppy_data in enumerate(floppies):
        if not ifloppy_data:
            continue

        print_log('DF{index}: {pathname}'.format(
            index=idf_index,
            pathname=ifloppy_data['pathname']
        ))


def print_attached_cd_images():
    print_log('Attached CD images:')

    for icd_index, icd_data in enumerate(cd_drives):
        if not icd_data:
            continue

        print_log('CD{index}: {pathname}'.format(
            index=icd_index,
            pathname=icd_data['pathname']
        ))


def print_attached_hard_disks():
    print_log('Attached hard disks:')

    for ihd_no, ihd_data in enumerate(drives):
        if not ihd_data:
            continue

        print_log('DH{index}: {pathname}'.format(
            index=ihd_no,
            pathname=ihd_data['pathname']
        ))


def print_commands():
    if not commands:
        return

    print_log('Commands:')

    for index, icmd in enumerate(commands):
        print_log('cmd{index}={cmd}'.format(
            index=index,
            cmd=icmd
        ))


def process_changed_drives():
    global drives_changed

    if not drives_changed:
        return

    drives_changed = False

    if AUTORUN_EMULATOR:
        turn_off_monitor()
        kill_emulator()
        keep_monitor_off_to_emulator(5)


def send_SIGUSR1_signal():
    if not AUTOSEND_SIGNAL:
        return False

    print_log('Sending SIGUSR1 signal to Amiberry emulator')

    try:
        sh.killall('-USR1', 'amiberry')

        return True
    except sh.ErrorReturnCode_1:
        print_log('No process found')

        return False


def process_local_command(command: str, str_commands: str):
    if command == 'local-commit':
        if not str_commands:
            return False

        print_log('Committing')

        write_tmp_ini(str_commands)

        if send_SIGUSR1_signal():
            block_till_tmp_ini_exists()

            return True

        return False
    elif command.startswith('local-sleep '):
        parts = command.split(' ')

        if len(parts) != 2:
            return False

        seconds = int(parts[1])

        print_log('Sleeping for {seconds} seconds'.format(
            seconds=seconds
        ))

        time.sleep(seconds)

    return False


def write_tmp_ini(str_commands: str):
    with open(emulator_tmp_ini_pathname, 'w+', newline=None) as f:
        f.write('[commands]' + os.linesep)
        f.write(str_commands)


def block_till_tmp_ini_exists():
    while os.path.exists(emulator_tmp_ini_pathname) and is_emulator_running():
        time.sleep(0)


def execute_commands():
    global commands

    str_commands = ''
    index = 0

    while commands:
        icommand = commands.pop(0).strip()

        if icommand.startswith('local-'):
            if process_local_command(icommand, str_commands):
                str_commands = ''
                index = 0

            continue

        str_commands += 'cmd{index}={cmd}\n'.format(
            index=index,
            cmd=icommand
        )
        index += 1

    if str_commands:
        write_tmp_ini(str_commands)

        if send_SIGUSR1_signal():
            block_till_tmp_ini_exists()


def mount_partitions(partitions: dict, failing_devices_ignore: List[str]) -> list:
    mounted = []

    for key, value in partitions.items():
        if value['mountpoint']:
            continue

        if not is_floppy_label(value['label']) and \
            not is_hard_drive_label(value['label']) and \
            not is_hard_file_label(value['label']) and \
            not is_cd_label(value['label']):
            continue

        if key in failing_devices_ignore:
            continue

        os.makedirs(value['internal_mountpoint'], exist_ok=True)

        force_fsck(key)

        if not force_mount(key, value['internal_mountpoint']):
            failing_devices_ignore.append(key)

            continue

        force_all_rw(value['internal_mountpoint'])

        partitions[key]['mountpoint'] = value['internal_mountpoint']
        partitions[key]['config'] = get_mountpoint_config(value['internal_mountpoint'])

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
    if len(label) != 7:
        return False

    if not label.startswith('ARA_DF'):
        return False

    if not label[6].isdigit():
        return False

    return True


def is_hard_drive_simple_label(label: str) -> bool:
    if len(label) != 7:
        return False

    if not label.startswith('ARA_DH'):
        return False

    if not label[6].isdigit():
        return False

    return True


def is_hard_drive_extended_label(label: str) -> bool:
    if len(label) != 9:
        return False

    if not label.startswith('ARA_DH'):
        return False

    if not label[6].isdigit():
        return False

    if label[7] != '_':
        return False

    if not label[8].isdigit():
        return False

    return True


def is_hard_drive_label(label: str) -> bool:
    if is_hard_drive_simple_label(label):
        return True
    elif is_hard_drive_extended_label(label):
        return True

    return False


def is_hard_file_simple_label(label: str) -> bool:
    if len(label) != 8:
        return False

    if not label.startswith('ARA_HDF'):
        return False

    if not label[7].isdigit():
        return False

    return True


def is_hard_file_extended_label(label: str) -> bool:
    if len(label) != 10:
        return False

    if not label.startswith('ARA_HDF'):
        return False

    if not label[7].isdigit():
        return False

    if label[8] != '_':
        return False

    if not label[9].isdigit():
        return False

    return True


def is_hard_file_label(label: str) -> bool:
    if is_hard_file_simple_label(label):
        return True
    elif is_hard_file_extended_label(label):
        return True

    return False


def is_cd_label(label: str) -> bool:
    if len(label) != 7:
        return False

    if not label.startswith('ARA_CD'):
        return False

    if not label[6].isdigit():
        return False

    return True


def get_label_floppy_index(label: str) -> int:
    return int(label[6])


def get_label_cd_index(label: str) -> int:
    return int(label[6])


def get_label_hard_disk_index(label: str):
    return int(label[6])


def get_label_hard_file_index(label: str):
    return int(label[7])


def get_label_hard_disk_boot_priority(label: str):
    if not is_hard_drive_extended_label(label):
        return DEFAULT_BOOT_PRIORITY
    
    return int(label[8])


def get_label_hard_file_boot_priority(label: str):
    if not is_hard_file_extended_label(label):
        return DEFAULT_BOOT_PRIORITY

    return int(label[9])


def force_umount(pathname: str):
    try:
        sh.umount('-l', pathname)
    except (sh.ErrorReturnCode_1, sh.ErrorReturnCode_32) as x:
        print_log(str(x))
        print_log('Failed to force-umount ' + pathname + ', maybe it is umounted already')


def force_mount(device: str, pathname: str) -> bool:
    options = '-ouser,umask=0000,sync,noatime'

    print_log('Mounting ' + device + ' as ' + pathname)

    try:
        sh.mount(device, options, pathname)

        return True
    except Exception as x:
        print_log(str(x))
        print_log('Unable to mount ' + device)

        if ENABLE_FORCE_FSCK == 'auto':
            force_fsck(device, True)

            try:
                sh.mount(device, options, pathname)

                return True
            except Exception as x2:
                print_log(str(x2))
                print_log('Unable to mount ' + device)

        return False


def force_fsck(pathname: str, force: bool = False):
    if (not ENABLE_FORCE_FSCK or ENABLE_FORCE_FSCK == 'auto') and not force:
        return

    try:
        print_log('Checking ' + pathname + ' for errors (fsck)')

        sh.fsck('-y', pathname)
    except (sh.ErrorReturnCode_1, sh.ErrorReturnCode_6) as x:
        print_log(str(x))
        print_log('Failed to force-fsck ' + pathname)


def force_all_rw(pathname: str):
    if not ENABLE_FORCE_RW:
        return

    try:
        sh.chmod('-R', 'a+rw', pathname)
    except sh.ErrorReturnCode_1 as x1:
        print_log(str(x1))
        print_log('Failed to chmod a+rw ' + pathname)


def process_new_mounted(partitions: dict, new_mounted: list) -> List[str]:
    attached = []

    for idevice in new_mounted:
        ipart_data = partitions[idevice]

        if not ipart_data['mountpoint']:
            continue

        if is_floppy_label(ipart_data['label']):
            if attach_mountpoint_floppy(idevice, ipart_data):
                update_floppy_drive_sound(
                    get_label_floppy_index(ipart_data['label'])
                )

                attached.append(idevice)
        elif is_hard_drive_label(ipart_data['label']):
            if attach_mountpoint_hard_disk(idevice, ipart_data):
                attached.append(idevice)
        elif is_hard_file_label(ipart_data['label']):
            if attach_mountpoint_hard_file(idevice, ipart_data):
                attached.append(idevice)
        elif is_cd_label(ipart_data['label']):
            if attach_mountpoint_cd_image(idevice, ipart_data):
                attached.append(idevice)

    return attached


def is_mountpoint_attached(mountpoint: str) -> bool:
    for imedium in floppies + drives + cd_drives:
        if not imedium:
            continue

        if imedium['mountpoint'] == mountpoint:
            return True

    return False


def process_other_mounted_floppy(partitions: dict):
    attached = []
    attached_indexes = []

    for ipart_dev, ipart_data in partitions.items():
        if not ipart_data['mountpoint']:
            continue

        if is_mountpoint_attached(ipart_data['mountpoint']):
            continue

        if is_floppy_label(ipart_data['label']):
            drive_index = get_label_floppy_index(ipart_data['label'])

            if drive_index in attached_indexes:
                # attach only one floppy per index
                continue

            if attach_mountpoint_floppy(ipart_dev, ipart_data):
                update_floppy_drive_sound(
                    drive_index
                )

                attached.append(ipart_dev)
                attached_indexes.append(drive_index)

    return attached


def process_other_mounted_cd(partitions: dict) -> List[str]:
    attached = []
    attached_indexes = []

    for ipart_dev, ipart_data in partitions.items():
        if not ipart_data['mountpoint']:
            continue

        if is_mountpoint_attached(ipart_data['mountpoint']):
            continue

        if is_cd_label(ipart_data['label']):
            drive_index = get_label_cd_index(ipart_data['label'])

            if drive_index in attached_indexes:
                # attach only one floppy per index
                continue

            if attach_mountpoint_cd_image(ipart_dev, ipart_data):
                attached.append(ipart_dev)
                attached_indexes.append(drive_index)

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
    global external_mounted_processed

    if external_mounted_processed:
        return []

    external_mounted_processed = True
    attached = []

    attached += process_other_mounted_floppy(partitions)
    attached += process_other_mounted_hard_disk(partitions)
    attached += process_other_mounted_hard_file(partitions)
    attached += process_other_mounted_cd(partitions)

    return attached


def set_devices_read_a_head(devices: List[str], partitions: dict):
    devices = list(set(devices))

    for ipart_dev in devices:
        if ipart_dev not in partitions:
            continue

        ipart_data = partitions[ipart_dev]

        if not ipart_data['mountpoint']:
            continue

        if not is_mountpoint_attached(ipart_data['mountpoint']):
            continue

        if ipart_data['is_floppy_drive']:
            set_device_read_a_head_sectors(ipart_dev, FLOPPY_DRIVE_READ_A_HEAD_SECTORS)
        else:
            set_device_read_a_head_sectors(ipart_dev, DEFAULT_READ_A_HEAD_SECTORS)


def set_device_read_a_head_sectors(device: str, sectors: int):
    os.system('blockdev --setra {sectors} {device}'.format(
        sectors=sectors,
        device=device
    ))


def attach_mountpoint_hard_disk(ipart_dev, ipart_data):
    global drives
    global drives_changed

    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    hd_no = get_label_hard_disk_index(ipart_data['label'])

    if hd_no >= MAX_DRIVES:
        return False

    if not drives[hd_no] or drives[hd_no]['pathname'] != mountpoint:
        print_log('Attaching "{mountpoint}" to DH{index}'.format(
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

        drives_changed = True

        return True
    else:
        print_log('DH{index} already attached'.format(
            index=hd_no
        ))

    return False


def attach_mountpoint_hard_file(ipart_dev, ipart_data):
    global drives
    global drives_changed

    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    ihdf = get_medium_file(
        ipart_dev,
        ipart_data,
        HARD_FILE_EXTENSIONS
    )

    if not ihdf:
        return False

    hd_no = get_label_hard_file_index(ipart_data['label'])

    if hd_no >= MAX_DRIVES:
        return False

    if not drives[hd_no] or drives[hd_no]['pathname'] != ihdf:
        print_log('Attaching "{pathname}" to DH{index} (HDF)'.format(
            pathname=ihdf,
            index=hd_no
        ))

        drives[hd_no] = {
            'pathname': ihdf,
            'mountpoint': ipart_data['mountpoint'],
            'label': ipart_data['label'],
            'device': ipart_dev,
            'config': ipart_data['config'],
            'is_dir': False,
            'is_hdf': True
        }

        drives_changed = True

        return True
    else:
        print_log('DH{index} (HDF) already attached'.format(
            index=hd_no
        ))

    return False


def process_unmounted(unmounted: list):
    global floppies
    global drives
    global cd_drives
    global drives_changed

    detached = []

    for idevice in unmounted:
        for idf_index, ifloppy_data in enumerate(floppies):
            if not ifloppy_data:
                continue

            if ifloppy_data['device'] == idevice:
                detach_floppy(idf_index)
                update_floppy_drive_sound(idf_index)

                detached.append(idevice)

        for idh_no, ihd_data in enumerate(drives):
            if not ihd_data:
                continue

            if ihd_data['device'] == idevice:
                print_log('Detaching "{pathname}" from DH{index}'.format(
                    pathname=ihd_data['pathname'],
                    index=idh_no
                ))

                is_dir = ihd_data['is_dir']

                drives[idh_no] = None
                drives_changed = True

                detached.append(idevice)

        for icd_index, icd_data in enumerate(cd_drives):
            if not icd_data:
                continue

            if icd_data['device'] == idevice:
                detach_cd(icd_index)

                detached.append(idevice)

    return detached


def mountpoint_find_files(mountpoint: str, patterns: List[str]) -> list:
    files = []

    for ifile in os.listdir(mountpoint):
        file_lower = ifile.lower()
        match = False

        for ipattern in patterns:
            if fnmatch.fnmatch(file_lower, ipattern):
                match = True

                break
        
        if not match:
            continue

        files.append(os.path.join(mountpoint, ifile))

    # TODO change sorting to sort like linux "find | sort"
    # TODO so by file extension then name
    return sorted(files, key=lambda x: os.path.splitext(x)[-1])


def update_floppy_drive_sound(drive_index: int):
    if ENABLE_FLOPPY_DRIVE_SOUND != 'auto':
        return

    for ioption in get_floppy_drive_sound_config_options():
        put_command('cfgfile_parse_line_type_all ' + ioption)

    put_command('config_changed 1')


def detach_floppy(index: int, auto_commit: bool = False) -> dict:
    global floppies

    floppy_data = floppies[index]

    if not floppy_data:
        return None

    print_log('Detaching "{pathname}" from DF{index}'.format(
        pathname=floppy_data['pathname'],
        index=index
    ))

    floppies[index] = None

    put_command('cfgfile_parse_line_type_all floppy{index}='.format(
        index=index
    ))
    put_command('config_changed 1')

    # put_command('disk_eject {index}'.format(
    #     index=index
    # ))

    if auto_commit:
        # some games like Dreamweb will fail to detect
        # new floppy when we change it too fast
        # so split eject and insert into two parts
        # using "commit" local command:
        # eject, sleep 1 second, insert
        put_local_commit_command(1)

    return floppy_data


def detach_cd(index: int, auto_commit: bool = False) -> dict:
    global cd_drives
    global drives_changed

    cd_data = cd_drives[index]

    if not cd_data:
        return None

    print_log('Detaching "{pathname}" from CD{index}'.format(
        pathname=cd_data['pathname'],
        index=index
    ))

    cd_drives[index] = None
    cd_empty_pathname = get_empty_cd_pathname()

    put_command('cfgfile_parse_line_type_all cdimage{index}={pathname}'.format(
        index=index,
        pathname=cd_empty_pathname
    ))
    put_command('config_changed 1')

    if auto_commit:
        # some games like Dreamweb will fail to detect
        # new floppy when we change it too fast
        # so split eject and insert into two parts
        # using "commit" local command:
        # eject, sleep 1 second, insert
        put_local_commit_command(1)

    if ENABLE_CD_REPLACE_RESTART:
        drives_changed = True

    return cd_data


def get_medium_file(
    ipart_dev: str,
    ipart_data: dict,
    patterns: List[str],
    force_file_pathname: str = None
) -> str:
    medium_files = mountpoint_find_files(ipart_data['mountpoint'], patterns)

    if not medium_files:
        return None

    if force_file_pathname and force_file_pathname in medium_files:
        return force_file_pathname
    else:
        if not is_medium_auto_insert_file(ipart_data):
            return None

        default_file = get_medium_default_file(ipart_data)

        if default_file:
            return default_file

        return medium_files[0]


def attach_mountpoint_floppy(ipart_dev, ipart_data, force_file_pathname = None):
    global floppies

    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    iadf = get_medium_file(
        ipart_dev,
        ipart_data,
        FLOPPY_EXTENSIONS,
        force_file_pathname
    )

    if not iadf:
        return False

    index = get_label_floppy_index(ipart_data['label'])

    if index >= MAX_FLOPPIES:
        return False

    if not floppies[index] or floppies[index]['pathname'] != iadf:
        print_log('Attaching "{pathname}" to DF{index}'.format(
            pathname=iadf,
            index=index
        ))

        floppies[index] = {
            'pathname': iadf,
            'mountpoint': mountpoint,
            'device': ipart_dev,
            'file_size': os.path.getsize(iadf),
            'last_access_ts': 0,
            'last_cached_size': 0,
            'config': ipart_data['config'],
            'medium': ipart_data
        }

        put_command('cfgfile_parse_line_type_all floppy{index}={pathname}'.format(
            index=index,
            pathname=iadf
        ))

        put_command('config_changed 1')

        # put_command('disk_insert_force {df_no},{pathname},0'.format(
        #     df_no=index,
        #     pathname=iadf
        # ))

        return True
    else:
        print_log('Floppy already attached to DF{index}, eject it first'.format(
            index=index
        ))

    return False


def attach_mountpoint_cd_image(ipart_dev: str, ipart_data: dict, force_file_pathname: str = None):
    global cd_drives
    global drives_changed

    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    icdimage = get_medium_file(
        ipart_dev,
        ipart_data,
        CD_EXTENSIONS,
        force_file_pathname
    )

    if not icdimage:
        return False

    index = get_label_cd_index(ipart_data['label'])

    if index >= MAX_CD_DRIVES:
        return False

    if not cd_drives[index] or cd_drives[index]['pathname'] != icdimage:
        print_log('Attaching "{pathname}" to CD{index}'.format(
            pathname=icdimage,
            index=index
        ))

        cd_drives[index] = {
            'pathname': icdimage,
            'mountpoint': mountpoint,
            'device': ipart_dev,
            'file_size': os.path.getsize(icdimage),
            'last_access_ts': 0,
            'last_cached_size': 0,
            'config': ipart_data['config'],
            'medium': ipart_data
        }

        if ENABLE_CD_REPLACE_RESTART:
            drives_changed = True

        put_command('cfgfile_parse_line_type_all cdimage{index}={pathname}'.format(
            index=index,
            pathname=icdimage
        ))

        put_command('config_changed 1')

        return True
    else:
        print_log('CD already attached to CD{index}, eject it first'.format(
            index=index
        ))

    return False


def put_local_commit_command(sleep_seconds: int = 0):
    put_command('local-commit')

    if sleep_seconds:
        put_command('local-sleep 1')


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

    if reset:
        commands = []

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


def get_medium_partition_label(medium_data):
    if not medium_data['config']:
        return None

    if 'config' not in medium_data['config']:
        return None

    if 'label' not in medium_data['config']['config']:
        return None

    return medium_data['config']['config']['label']


def is_medium_auto_insert_file(medium_data):
    if not medium_data['config']:
        return True

    if 'config' not in medium_data['config']:
        return True

    if 'auto_insert_file' not in medium_data['config']['config']:
        return True

    return medium_data['config']['config'].getboolean('auto_insert_file')


def get_medium_default_file(medium_data):
    if not medium_data['config']:
        return None

    if 'config' not in medium_data['config']:
        return None

    if 'default_file' not in medium_data['config']['config']:
        return None

    return os.path.realpath(os.path.join(
        medium_data['mountpoint'],
        medium_data['config']['config']['default_file']
    ))


def is_emulator_running():
    if not AUTORUN_EMULATOR:
        return None

    for iprocess in psutil.process_iter(attrs=['exe']):
        if iprocess.info['exe'] == emulator_exe_pathname:
            return True

    return False


def format_filesystem2_string(permissions: str, drive_index: int, label: str, pathname: str, boot_priority: int):
    return 'filesystem2={permissions},DH{drive_index}:{label}:{pathname},{boot_priority}'.format(
        permissions=permissions,
        drive_index=drive_index,
        label=label,
        pathname=pathname,
        boot_priority=boot_priority
    )


def format_uaehf_dir_string(drive_index: int, permissions: str, label: str, pathname: str, boot_priority: int):
    return 'uaehf{drive_index}=dir,{permissions},DH{drive_index}:{label}:{pathname},{boot_priority}'.format(
        drive_index=drive_index,
        permissions=permissions,
        label=label,
        pathname=pathname,
        boot_priority=boot_priority
    )


def get_dir_drive_config_command_line(drive_index: int, drive_data: dict):
    config = []

    label = get_medium_partition_label(drive_data)
    boot_priority = get_label_hard_disk_boot_priority(drive_data['label'])

    if not label:
        label = drive_data['label']

    config.append(
        format_filesystem2_string(
            'rw',
            drive_index,
            label,
            drive_data['pathname'],
            boot_priority
        )
    )
    config.append(
        format_uaehf_dir_string(
            drive_index,
            'rw',
            label,
            drive_data['pathname'],
            boot_priority
        )
    )

    return config


def get_hdf_type(pathname: str) -> int:
    file_stat = os.stat(pathname)

    with open(pathname, 'rb') as file:
        data = array('B', file.read(512))

        char_0 = chr(data[0])
        char_1 = chr(data[1])
        char_2 = chr(data[2])
        char_3 = chr(data[3])

        first_4_chars = ''.join([char_0, char_1, char_2, char_3])

        if first_4_chars == 'RDSK':
            return HDF_TYPE_HDFRDB
        elif first_4_chars.startswith('DOS'):
            if file_stat.st_size < 4 * 1024 * 1024:
                return HDF_TYPE_DISKIMAGE
            else:
                return HDF_TYPE_HDF

    return None


def get_hdf_drive_config_command_line(drive_index: int, idrive: dict):
    config = []

    boot_priority = get_label_hard_file_boot_priority(idrive['label'])
    hdf_type = get_hdf_type(idrive['pathname'])

    sectors = 0
    surfaces = 0
    reserved = 0
    blocksize = 512

    if hdf_type == HDF_TYPE_HDF:
        sectors = 32
        surfaces = 1
        reserved = 2
        blocksize = 512

    config.append('hardfile2=rw,DH{drive_index}:{pathname},{sectors},{surfaces},{reserved},{blocksize},{boot_priority},,uae{controller_index},0'.format(
        drive_index=drive_index,
        pathname=idrive['pathname'],
        sectors=sectors,
        surfaces=surfaces,
        reserved=reserved,
        blocksize=blocksize,
        boot_priority=boot_priority,
        controller_index=drive_index
    ))
    config.append('uaehf{drive_index}=hdf,rw,DH{drive_index}:{pathname},{sectors},{surfaces},{reserved},{blocksize},{boot_priority},,uae{controller_index},0'.format(
        drive_index=drive_index,
        pathname=idrive['pathname'],
        sectors=sectors,
        surfaces=surfaces,
        reserved=reserved,
        blocksize=blocksize,
        boot_priority=boot_priority,
        controller_index=drive_index
    ))

    return config


def get_empty_cd_pathname():
    if not ENABLE_CD_PERM_FIX:
        return ''

    return CD_PERM_FIX_PATHNAME


def get_cd_drives_command_line_config() -> str:
    str_cd_drives = ''

    for index, icd in enumerate(cd_drives):
        pathname = ''

        if icd:
            pathname = icd['pathname']
        else:
            pathname = get_empty_cd_pathname()

        if not pathname:
            continue

        str_cd_drives += ' -s cdimage{index}="{pathname}" '.format(
            index=index,
            pathname=pathname
        )

    return str_cd_drives


def get_media_command_line_config():
    # floppies
    str_floppies = ''

    for index, ifloppy in enumerate(floppies):
        if ifloppy:
            str_floppies += ' -{index} "{pathname}" '.format(
                index=index,
                pathname=ifloppy['pathname']
            )

    # hard drives
    drive_index = 0
    str_drives = ''

    if ENABLE_HARD_DRIVES:
        for index, idrive in enumerate(drives):
            if idrive:
                if idrive['is_dir']:
                    drive_config = get_dir_drive_config_command_line(drive_index, idrive)

                    str_drives += ' -s {config0} -s {config1} '.format(
                        config0=drive_config[0],
                        config1=drive_config[1]
                    )

                    drive_index += 1
                elif idrive['is_hdf']:
                    drive_config = get_hdf_drive_config_command_line(drive_index, idrive)

                    str_drives += ' -s {config0} -s {config1} '.format(
                        config0=drive_config[0],
                        config1=drive_config[1]
                    )

                    drive_index += 1

    # cd drives
    str_cd_drives = get_cd_drives_command_line_config()

    if ENABLE_INTERNAL_DRIVE and drive_index < MAX_DRIVES:
        # add read-only internal drive
        str_drives += '-s ' + format_filesystem2_string(
            INTERNAL_DRIVE_PERMISSION,
            drive_index,
            INTERNAL_DRIVE_LABEL,
            DEVS_PATHNAME,
            INTERNAL_DRIVE_BOOT_PRIORITY
        ) + ' '

        str_drives += ' -s ' + format_uaehf_dir_string(
            drive_index,
            INTERNAL_DRIVE_PERMISSION,
            INTERNAL_DRIVE_LABEL,
            DEVS_PATHNAME,
            INTERNAL_DRIVE_BOOT_PRIORITY
        ) + ' '

    return {
        'floppies': str_floppies,
        'drives': str_drives,
        'cd_drives': str_cd_drives
    }


def format_floppy_sound_option(index: int, enabled: bool, disk_in_drive_volume: int = None, empty_drive_volume: int = None) -> list:
    enabled_str = '1' if enabled else '0'
    options = []
    floppy_soundvolume_disk_option = ''
    floppy_soundvolume_empty_option = ''

    floppy_sound_option = 'floppy{index}sound={enabled}'.format(
        index=index,
        enabled=enabled_str
    )
    options.append(floppy_sound_option)

    if disk_in_drive_volume is not None and enabled:
        floppy_soundvolume_disk_option = 'floppy{index}soundvolume_disk={volume}'.format(
            index=index,
            volume=disk_in_drive_volume
        )
        options.append(floppy_soundvolume_disk_option)

    if empty_drive_volume is not None and enabled:
        floppy_soundvolume_empty_option = 'floppy{index}soundvolume_empty={volume}'.format(
            index=index,
            volume=empty_drive_volume
        )
        options.append(floppy_soundvolume_empty_option)

    return options


def prepare_floppy_drive_volume(volume: int) -> int:
    return 100 - volume


def get_floppy_drive_sound_enabled_config_options(enabled: bool = True):
    options = []

    options.append('floppy_volume=' + str(floppy_disk_in_drive_volume))

    for drive_index in range(MAX_DRIVES):
        options.extend(
            format_floppy_sound_option(
                drive_index,
                enabled,
                floppy_disk_in_drive_volume,
                floppy_empty_drive_volume
            )
        )

    return options


def get_floppy_drive_sound_config_options():
    if ENABLE_FLOPPY_DRIVE_SOUND is False:
        return get_floppy_drive_sound_enabled_config_options(False)

    if ENABLE_FLOPPY_DRIVE_SOUND is True:
        return get_floppy_drive_sound_enabled_config_options()

    if ENABLE_FLOPPY_DRIVE_SOUND != 'auto':
        return []

    config_options = []
    config_options.append('floppy_volume=' + str(floppy_disk_in_drive_volume))

    for drive_index, floppy_data in enumerate(floppies):
        floppy_drive_sound_enabled = True

        if not floppy_data or floppy_data['medium']['is_floppy_drive']:
            floppy_drive_sound_enabled = False

        add_options = format_floppy_sound_option(
            drive_index,
            floppy_drive_sound_enabled,
            floppy_disk_in_drive_volume,
            floppy_empty_drive_volume
        )

        config_options.extend(add_options)

    return config_options


def get_gui_config_options() -> List[str]:
    config_options = []

    if not ENABLE_MOUSE_UNGRAB:
        config_options.append('magic_mouse=none')

    if not ENABLE_F12_OPEN_GUI:
        config_options.append('amiberry.open_gui=none')

    return config_options


def get_emulator_command_line_config():
    config_str = ''

    for ioption in get_floppy_drive_sound_config_options():
        config_str += ' -s ' + ioption + ' '

    for ioption in get_gui_config_options():
        config_str += ' -s ' + ioption + ' '

    if ' -m CD32 ' in EMULATOR_RUN_PATTERN:
        # HACK we need to add finegrain_cpu_speed=1024
        # in order to emulate CD32
        # maybe it is a bug in the emulator?
        config_str += ' -s finegrain_cpu_speed=1024 '

    return config_str


def get_ext_kickstart_command_line_config():
    extended_kickstart = ''

    if kickstart_extended_pathname:
        extended_kickstart = '-K "{pathname}"'.format(
            pathname=kickstart_extended_pathname
        )

    return extended_kickstart


def run_emulator():
    global floppies

    print_log('Running emulator')

    media_config = get_media_command_line_config()
    config_options = get_emulator_command_line_config()
    extended_kickstart = get_ext_kickstart_command_line_config()

    pattern = EMULATOR_RUN_PATTERN.format(
        executable=emulator_exe_pathname,
        nr_floppies=MAX_FLOPPIES,
        config_options=config_options,
        kickstart=kickstart_pathname,
        extended_kickstart=extended_kickstart,
        floppies=media_config['floppies'],
        drives=media_config['drives'],
        cd_drives=media_config['cd_drives']
    )

    print_log('Emulator command line: ' + pattern)

    subprocess.Popen(pattern, cwd=os.path.dirname(emulator_exe_pathname), shell=True)

    time.sleep(0)


def kill_emulator():
    print_log('Sending SIGKILL signal to Amiberry emulator')

    try:
        sh.killall('-9', 'amiberry')
    except sh.ErrorReturnCode_1:
        print_log('No process found')

def delete_unused_mountpoints():
    print_log('Delete unused mountpoints')

    pathname = os.path.join(DEVS_PATHNAME, '*')

    os.system('rmdir ' + pathname)


def line_parts_to_dict(line_parts: List[str], maxsplit: int) -> dict:
    ret = {}

    for ipart in line_parts:
        parts = ipart.split(':', 1)

        if len(parts) < 2:
            continue

        ret[parts[0].strip()] = parts[1].strip()

    return ret


def iwconfig():
    iwconfig_buf = StringIO()
    ret = {}
    last_ifname = None

    sh.iwconfig(_out=iwconfig_buf)

    for line in iwconfig_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        parts = line.split('  ')
        len_parts = len(parts)

        if not len_parts:
            continue

        if ' IEEE 802.11  ESSID:' in line:
            last_ifname = parts[0]

            ret[last_ifname] = line_parts_to_dict(parts, 1)
        else:
            if not last_ifname:
                continue

            ret[last_ifname].update(
                line_parts_to_dict(parts, 1)
            )

    return ret


def connect_wifi():
    if not os.path.exists(WPA_SUPPLICANT_CONF_PATHNAME):
        return

    print_log(WPA_SUPPLICANT_CONF_PATHNAME + ' exists, connecting to WIFI')

    wifi_interfaces = iwconfig()

    if not wifi_interfaces:
        print_log('No WIFI interfaces')

    if_name = list(wifi_interfaces.keys())[0]
    if_data = wifi_interfaces[if_name]

    if if_data['Access Point'] != 'Not-Associated':
        print_log(if_name + ' is already connected to ' + if_data['ESSID'] + ' network, skipping')

        return

    os.system('killall -9 wpa_supplicant')
    os.system('rfkill unblock wifi')
    os.system('wpa_supplicant -B -c {config_pathname} -i {interface}'.format(
        config_pathname=WPA_SUPPLICANT_CONF_PATHNAME,
        interface=if_name
    ))


def disconnect_wifi():
    print_log('Disconnecting from WIFI')

    os.system('rm {config_pathname}'.format(
        config_pathname=WPA_SUPPLICANT_CONF_PATHNAME
    ))

    wifi_interfaces = iwconfig()

    if not wifi_interfaces:
        print_log('No WIFI interfaces')

    if_name = list(wifi_interfaces.keys())[0]
    if_data = wifi_interfaces[if_name]

    if if_data['Access Point'] == 'Not-Associated':
        print_log(if_name + ' is not connected to any network, skipping')

        return

    os.system('killall -9 wpa_supplicant')
    os.system('ifconfig {interface} down'.format(
        interface=if_name
    ))
    os.system('ifconfig {interface} up'.format(
        interface=if_name
    ))


def on_key_press(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed
    global tab_pressed
    global ctrl_alt_del_press_ts
    global tab_combo
    global tab_combo_recording

    if key == Key.ctrl:
        key_ctrl_pressed = True

    if key == Key.alt:
        key_alt_pressed = True

    if key == Key.delete:
        key_delete_pressed = True

    if key == Key.tab:
        tab_pressed = True

    if key == Key.esc:
        tab_combo = []
    else:
        tab_combo.append(key)

    if len(tab_combo) >= 255:
        tab_combo = []


def on_key_release(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed
    global tab_pressed
    global ctrl_alt_del_press_ts

    if key == Key.ctrl:
        key_ctrl_pressed = False

    if key == Key.alt:
        key_alt_pressed = False

    if key == Key.delete:
        key_delete_pressed = False

    if key == Key.tab:
        tab_pressed = False


print_app_version()
init_logger()
check_pre_requirements()
configure_tmp_ini()
configure_system()
configure_volumes()
delete_unused_mountpoints()
connect_wifi()
# disconnect_wifi()

keyboard_listener = Listener(on_press=on_key_press, on_release=on_key_release)
failing_devices_ignore = []

keyboard_listener.start()

# give the user one second so he can press
# TAB key to enter system shell
time.sleep(1)
tab_shell()

while True:
    unmounted = []
    new_mounted = []
    new_attached = []
    new_detached = []
    other_attached = []

    partitions = get_partitions2()

    if partitions != old_partitions:
        failing_devices_ignore = []

    unmounted = unmount_partitions(partitions, old_partitions)

    if unmounted:
        print_log('Unmounted partitions')

        new_detached = process_unmounted(unmounted)

    # mount new partitions
    new_mounted = mount_partitions(partitions, failing_devices_ignore)

    if new_mounted:
        print_log('Mounted new partitions')

        new_attached = process_new_mounted(partitions, new_mounted)

    other_attached = process_other_mounted(partitions)

    if new_attached or other_attached:
        set_devices_read_a_head(new_attached + other_attached, partitions)

    if unmounted or new_mounted or new_attached or new_detached or other_attached:
        # something changed
        print_partitions(partitions)
        print_attached_floppies()
        print_attached_hard_disks()
        print_attached_cd_images()

    if new_mounted or unmounted:
        delete_unused_mountpoints()

    old_partitions = partitions

    process_changed_drives()

    if commands:
        print_commands()
        execute_commands()

    if is_emulator_running() == False:
        run_emulator()
        reset_audio_lag_fix()

    keyboard_actions(partitions)
    update_monitor_state()
    other_actions()
    audio_lag_fix()
    sync()

    time.sleep(1)
