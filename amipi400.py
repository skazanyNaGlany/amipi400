import sys
import os
import traceback

assert sys.platform == 'linux', 'This script must be run only on Linux'
assert sys.version_info.major >= 3 and sys.version_info.minor >= 5, 'This script requires Python 3.5+'
assert os.geteuid() == 0, 'This script must be run as root'

try:
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
    import glob
    import atexit
    import shutil

    from collections import OrderedDict
    from typing import Optional, List
    from io import StringIO
    from pynput.keyboard import Key, Listener, Controller, KeyCode
    from configparser import ConfigParser, ParsingError
    from array import array
    from utils import enable_numlock, disable_numlock, mute_system_sound, unmute_system_sound, blink_numlock, init_simple_mixer_control
except ImportError as xie:
    traceback.print_exc()
    sys.exit(1)


APP_UNIXNAME = 'amipi400'
APP_VERSION = '0.1'
TMP_PATH_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
AMIGA_DISK_DEVICES_MOUNTPOINT = os.path.join(tempfile.gettempdir(), 'amiga_disk_devices')
AMIGA_DISK_DEVICES_STATUS_LOG = os.path.join(AMIGA_DISK_DEVICES_MOUNTPOINT, 'status.log')
INTERNAL_MOUNTPOINTS_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'mountpoints')
KICKSTART_COPY_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'kickstart.rom')
KICKSTART_EXTENDED_COPY_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'kickstart_ext.rom')
TMP_ADF_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'tmp.adf')
LOG_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'amipi400.log')
FLOPPY_DISK_IN_DRIVE_SOUND_VOLUME = 20
FLOPPY_EMPTY_DRIVE_SOUND_VOLUME = 0
ENABLE_FLOPPY_DRIVE_SOUND = 'auto'
ENABLE_HARD_DRIVES = True
ENABLE_LOGGER = False
ENABLE_TURN_OFF_MONITOR = True
ENABLE_CTRL_ALT_ALT_GR_LONG_PRESS_KILL = True
ENABLE_AUDIO_LAG_FIX = False
ENABLE_FORCE_FSCK = 'auto'
ENABLE_FORCE_RW = False
ENABLE_CD_REPLACE_RESTART = False
ENABLE_CD_PERM_FIX = False
ENABLE_MOUSE_UNGRAB = False
ENABLE_F12_OPEN_GUI = True
# ENABLE_F12_OPEN_GUI = False
ENABLE_PHYSICAL_FLOPPY_DRIVES = True
ENABLE_AMIGA_DISK_DEVICES_SUPPORT = True
ENABLE_SET_CACHE_PRESSURE = False
ENABLE_INTERNAL_DRIVE = True
ENABLE_PHYSICAL_FLOPPY_READ_SPEED_HACK = False  # ~20 secs faster (can break compatibility in some games)
ENABLE_TAB_SHELL = True
ENABLE_KICKSTART_LONG_FILENAME_FIX = True
ENABLE_COPY_DF_MUTE_SOUNDS = True
ENABLE_COPY_HD_MUTE_SOUNDS = True
ENABLE_CMD_ENTER_KP_ENTER_MAPPING = True
DISABLE_SWAP = False
AUDIO_LAG_STEP_0_SECS = 30  # original
AUDIO_LAG_STEP_1_SECS = 6
SYNC_DISKS_SECS = 60 * 3
EMULATOR_EXE_PATHNAMES = [
    'amiberry',
    '../amiberry/amiberry'
]
EMULATOR_TMP_INI_NAME = 'amiberry.tmp.ini'
MAX_FLOPPIES = 4
MAX_DRIVES = 6
MAX_CD_DRIVES = 1
RE_SIMILAR_ROM = re.compile(r'\(Disk\ \d\ of\ \d\)')
SIMILAR_ROM = '(Disk {index} of {max_index})'
KICKSTART_PATHNAMES = [
    '/boot/amipi400/kickstart/*.rom',
    '../amiberry/kickstart/*.rom',
    'kickstart/*.rom',
]
KICKSTART_EXTENDED_PATHNAMES = [
    '/boot/amipi400/kickstart/extended/*.rom',
    '../amiberry/kickstart/extended/*.rom',
    'kickstart/extended/*.rom',
]
EMULATOR_RUN_PATTERN = '{executable} -G -m {amiga_model_id} -s bsdsocket_emu=true -s scsi=false -s nr_floppies={nr_floppies} {config_options} -r "{kickstart}" {extended_kickstart} {floppies} {floppy_types} {drives} {cd_drives} {additional_config_options}'
CONFIG_INI_NAME = '.amipi400.ini'
DEFAULT_BOOT_PRIORITY = 0
AUTORUN_EMULATOR = True
# AUTORUN_EMULATOR = False
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
WPA_SUPPLICANT_CONF_PATHNAME = 'wpa_supplicant.conf'
ALT_GR_KEYCODE = 65027
ALT_GR_UK_KEYCODE = 65406
KP_ENTER_KEYCODE = 65421
PYNPUT_KP_ENTER_KEY = KeyCode(KP_ENTER_KEYCODE)
DEFAULT_FLOPPY_TYPE=0       # 3,5'' DD
INTERNAL_DRIVE_BOOT_BRIORITY = -128     # -128 = not bootable
INTERNAL_DRIVE_LABEL = 'AmiPi400_Internal'
FLOPPY_ADF_EXTENSION = '.adf'
HD_HDF_EXTENSION = '.hdf'
CD_ISO_EXTENSION = '.iso'
KICKSTART_ROMS2MODEL_MAP = [
    # https://fs-uae.net/docs/kickstarts
    {
        'amiga_model_id': 'A500',
        'amiga_model_full_name': 'Amiga 500',
        'kickstart_version': '1.3',
        'need_extended_rom': False,
        'additional_config_options': [],
        'file_names': [
            'Kickstart v1.3 *(A500-A1000-A2000-CDTV)*.rom',
            'Kickstart1.3*.rom',
            'amiga-os-130*.rom'
        ]
    },
    {
        'amiga_model_id': 'A500P',
        'amiga_model_full_name': 'Amiga 500+',
        'kickstart_version': '2.04',
        'need_extended_rom': False,
        'additional_config_options': [],
        'file_names': [
            'Kickstart v2.04 *(A500*+)*.rom',
            'Kickstart v2.04 *(A500*PLUS)*.rom',
            'Kickstart2.04*.rom',
            'amiga-os-204*.rom'
        ]
    },
    {
        'amiga_model_id': 'A600',
        'amiga_model_full_name': 'Amiga 600',
        'kickstart_version': '2.05',
        'need_extended_rom': False,
        'additional_config_options': [],
        'file_names': [
            'Kickstart v2.05 *(A600)*.rom',
            'Kickstart v2.05 *(A600*HD)*.rom',
            'Kickstart2.05*.rom',
            'amiga-os-205*.rom'
        ]
    },
    {
        'amiga_model_id': 'A1200',
        'amiga_model_full_name': 'Amiga 1200',
        'kickstart_version': '3.1',
        'need_extended_rom': False,
        'additional_config_options': [],
        'file_names': [
            'Kickstart v3.1 *(A1200)*.rom',
            'Kickstart3.1*.rom',
            'amiga-os-310-a1200*.rom'
        ]
    },
    {
        'amiga_model_id': 'A3000',
        'amiga_model_full_name': 'Amiga 3000',
        'kickstart_version': '3.1',
        'need_extended_rom': False,
        'additional_config_options': [],
        'file_names': [
            'Kickstart v3.1 *(A3000)*.rom',
            # 'Kickstart3.1*.rom',
            'amiga-os-310-a3000*.rom'
        ]
    },
    {
        'amiga_model_id': 'A4000',
        'amiga_model_full_name': 'Amiga 4000',
        'kickstart_version': '3.1',
        'need_extended_rom': False,
        'additional_config_options': [],
        'file_names': [
            'Kickstart v3.1 *(A4000)*.rom',
            # 'Kickstart3.1*.rom',
            'amiga-os-310*.rom'
        ]
    },
    {
        'amiga_model_id': 'A1000',
        'amiga_model_full_name': 'Amiga 1000',
        'kickstart_version': '1.2',
        'need_extended_rom': False,
        'additional_config_options': [],
        'file_names': [
            'Kickstart v1.2 *(A500-A1000-A2000)*.rom',
            'Kickstart1.2*.rom',
            'amiga-os-120*.rom'
        ]
    },
    {
        'amiga_model_id': 'CD32',
        'amiga_model_full_name': 'Amiga CD32',
        'kickstart_version': '3.1',
        'need_extended_rom': True,
        'additional_config_options': [
            # HACK we need to add finegrain_cpu_speed=1024
            # HACK in order to emulate CD32
            # HACK maybe it is a bug in the emulator?
            'finegrain_cpu_speed=1024'
        ],
        'file_names': [
            'Kickstart v3.1 *(CD32)*.rom',
            'amiga-os-310-cd32*.rom'
        ]
    },
    {
        'amiga_model_id': 'CDTV',
        'amiga_model_full_name': 'Amiga CDTV',
        'kickstart_version': '1.3',
        'need_extended_rom': True,
        'additional_config_options': [],
        'file_names': [
            'Kickstart v1.3 *(CDTV)*.rom',
        ]
    }
]
AMIBERRY_AMIGA_MODEL_SUPPORT = [
    'A500',
    'A500P',
    'A1200',
    'A4000',
    'CD32'
]
AMIGA_DISK_DEVICE_TYPE_ADF = 1
AMIGA_DISK_DEVICE_TYPE_HDF_HDFRDB = 8
AMIGA_DISK_DEVICE_TYPE_HDF_DISKIMAGE = 2
AMIGA_DISK_DEVICE_TYPE_HDF = 5
AMIGA_DISK_DEVICE_TYPE_ISO = 10
COPY_DF_BLOCK_SIZE=32768
COPY_HD_BLOCK_SIZE='8M'
COPY_DF_MODE_DIRECT=1
COPY_DF_MODE_INDIRECT=2

floppies = [None for x in range(MAX_FLOPPIES)]
floppies_seq_numbers = [0 for x in range(MAX_FLOPPIES)]
drives = [None for x in range(MAX_DRIVES)]
cd_drives = [None for x in range(MAX_CD_DRIVES)]
drives_changed = False
commands = []
partitions = None
old_partitions = None
amiga_disk_devices = None
old_amiga_disk_devices = None
key_ctrl_pressed = False
key_alt_pressed = False
key_alt_gr_pressed = False
key_shift_r_pressed = False
key_cmd_pressed = False
key_enter_pressed = False
key_esc_pressed = False
ctrl_alt_alt_gr_press_ts = 0
tab_combo = []
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
physical_floppy_drives = OrderedDict()
amiberry_current_sound_mode = ''
sound_output_state = 'exact'
failing_devices_ignore = []
keyboard_listener = None
keyboard_controller = None
is_emulator_running = None
soft_resetting = False
hard_resetting = False
current_floppy_speed = 100
current_amiga_kickstart2model = None
printed_emulator_full_command_line = False
physical_cdrom_drives = OrderedDict()
copy_df_mode = None
copy_df_step = -1
copy_df_source_index = 0
copy_df_target_index = 0
copy_df_source_data = None
copy_df_target_data = None
copy_df_floppies_seq_numbers_copy = {}
is_emulator_paused = False
copy_hd_step = -1
copy_hd_source_index = 0
copy_hd_target_index = 0
copy_hd_source_data = None
copy_hd_target_data = None


def mount_tmpfs():
    print_log('Creating and monunting', TMP_PATH_PREFIX, 'as tmpfs')

    if not os.path.exists(TMP_PATH_PREFIX):
        os.makedirs(TMP_PATH_PREFIX, exist_ok=True)

    err_code = os.system('chmod 0777 ' + TMP_PATH_PREFIX)

    if err_code:
        print_log('Cannot chmod', TMP_PATH_PREFIX, 'got', err_code, 'error code')

    if os.path.ismount(TMP_PATH_PREFIX):
        print_log(TMP_PATH_PREFIX, 'is already mounted, skipping')
        return

    err_code = os.system('mount -t tmpfs tmpfs ' + TMP_PATH_PREFIX)

    if err_code:
        print_log('Cannot mount', TMP_PATH_PREFIX, 'as tmpfs, got', err_code, 'error code')


def umount_tmpfs():
    print_log('Unmounting and removing', TMP_PATH_PREFIX)

    err_code = os.system('umount -R ' + TMP_PATH_PREFIX)

    if err_code:
        print_log('Cannot umount', TMP_PATH_PREFIX, 'got', err_code, 'error code')


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
    check_system_binaries()
    check_emulator()


def configure_system():
    print_log('Configuring system')

    disable_swap()
    set_cache_pressure()


def disable_swap():
    if not DISABLE_SWAP:
        return

    print_log('Disable swap')
    os.system('swapoff -a')


def set_cache_pressure():
    if not ENABLE_SET_CACHE_PRESSURE:
        return

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


def setup_amiga_model():
    global kickstart_pathname
    global current_amiga_kickstart2model

    print_log('Checking kickstart and setting Amiga model')

    for ipathname in KICKSTART_PATHNAMES:
        pathnames = glob.glob(ipathname)

        for ireal_pathname in pathnames:
            ireal_pathname_lower_basename = os.path.basename(ireal_pathname.lower())

            for ikickstart2model in KICKSTART_ROMS2MODEL_MAP:
                k2m_file_names = ikickstart2model['file_names']

                for ik2m_filename_pattern in k2m_file_names:
                    ik2m_filename_pattern = ik2m_filename_pattern.lower()

                    if fnmatch.fnmatch(ireal_pathname_lower_basename, ik2m_filename_pattern):
                        kickstart_pathname = ireal_pathname
                        current_amiga_kickstart2model = ikickstart2model.copy()

                        break

                if kickstart_pathname:
                    break

            if kickstart_pathname:
                break

    if not kickstart_pathname:
        print_log('Kickstart ROM does not exists, checked:\n{paths}'.format(
            paths='\n'.join(KICKSTART_PATHNAMES)
        ))

        print_log('Make sure your kickstart ROM filename is Kickstart<version>.rom')
        print_log('For example: Kickstart3.1.rom')

        sys.exit(1)

    if current_amiga_kickstart2model['amiga_model_id'] not in AMIBERRY_AMIGA_MODEL_SUPPORT:
        print_log('Amiga model ' + current_amiga_kickstart2model['amiga_model_id'] + ' is not supported by AmiBerry emulator.')

        exit(1)


def setup_extended_kickstart():
    global kickstart_extended_pathname

    print_log('Checking and setting extended kickstart')

    for ipathname in KICKSTART_EXTENDED_PATHNAMES:
        paths = glob.glob(ipathname)

        if paths:
            kickstart_extended_pathname = paths[0]

            break

    if not kickstart_extended_pathname:
        print_log('Extended kickstart ROM does not exists, checked:\n{paths}'.format(
            paths='\n'.join(KICKSTART_EXTENDED_PATHNAMES)
        ))

        if current_amiga_kickstart2model['need_extended_rom']:
            exit(1)
    else:
        print_log('Extended kickstart: ' + kickstart_extended_pathname)


def overwrite_amiga_config_by_kickstart():
    global current_amiga_kickstart2model

    kickstart_basename = os.path.basename(kickstart_pathname)

    brackets = re.findall('\((.*?)\)', kickstart_basename)
    app_name_space = APP_UNIXNAME.lower() + ' '
    model_sign_space = '-m '
    setting_sign_space = '-s '
    thismodule = sys.modules[__name__]

    for istr in brackets:
        if not istr.startswith(app_name_space):
            continue

        istr_parts = istr.replace(app_name_space, '', 1).strip().split(',')

        for istr2 in istr_parts:
            istr2 = istr2.strip()

            if istr2.startswith(model_sign_space):
                current_amiga_kickstart2model['amiga_model_id'] = istr2.replace(model_sign_space, '', 1)
            elif istr2.startswith(setting_sign_space):
                current_amiga_kickstart2model['additional_config_options'].append(
                    istr2.replace(setting_sign_space, '', 1)
                )
            elif istr2.startswith('ENABLE_') or istr2.startswith('DISABLE_'):
                istr2_parts = istr2.split('=')

                if len(istr2_parts) != 2:
                    continue

                if not hasattr(thismodule, istr2_parts[0]):
                    continue

                istr2_parts[1] = istr2_parts[1].lower()

                if istr2_parts[1] == 'true':
                    setattr(thismodule, istr2_parts[0], True)
                elif istr2_parts[1] == 'false':
                    setattr(thismodule, istr2_parts[0], False)
                elif istr2_parts[1] == 'none':
                    setattr(thismodule, istr2_parts[0], None)
                elif istr2_parts[1].isdigit():
                    setattr(thismodule, istr2_parts[0], int(istr2_parts[1]))
                else:
                    # just string
                    setattr(thismodule, istr2_parts[0], istr2_parts[1])


def print_current_amiga_kickstart2model():
    print_log('Amiga model: ' + current_amiga_kickstart2model['amiga_model_full_name'])
    print_log('Amiga model ID: ' + current_amiga_kickstart2model['amiga_model_id'])
    print_log('Kickstart: ' + kickstart_pathname)
    print_log('Kickstart version: ' + current_amiga_kickstart2model['kickstart_version'])

    if current_amiga_kickstart2model['additional_config_options']:
        print_log('Additional config options:')

        print_log('\n'.join(
            current_amiga_kickstart2model['additional_config_options']
        ))


def copy_kickstart():
    global kickstart_pathname
    global kickstart_extended_pathname

    if not ENABLE_KICKSTART_LONG_FILENAME_FIX:
        return

    print_log('Copying kickstart and extended kickstart ROM:')

    print_log('{kick_str} -> {kick_dst}'.format(
        kick_str=kickstart_pathname,
        kick_dst=KICKSTART_COPY_PATHNAME
    ))
    shutil.copyfile(kickstart_pathname, KICKSTART_COPY_PATHNAME)

    kickstart_pathname = KICKSTART_COPY_PATHNAME

    if kickstart_extended_pathname:
        print_log('{kick_str} -> {kick_dst}'.format(
            kick_str=kickstart_extended_pathname,
            kick_dst=KICKSTART_EXTENDED_COPY_PATHNAME
        ))
        shutil.copyfile(kickstart_extended_pathname, KICKSTART_EXTENDED_COPY_PATHNAME)

        kickstart_extended_pathname = KICKSTART_EXTENDED_COPY_PATHNAME


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
        'ifconfig',
        'ufiformat',
        'iw',
        'tee',
        'sudo',
        'amixer',
        'hwinfo'
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
    # TODO execute once a second
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
        if not is_emulator_running:
            return

        keep_monitor_off(monitor_off_seconds)


def clear_reset_marks():
    global soft_resetting
    global hard_resetting

    soft_resetting = False
    hard_resetting = False


def soft_reset_emulator():
    global soft_resetting

    if soft_resetting:
        return

    # clear_system_cache()
    put_command('uae_reset 1,1')

    soft_resetting = True


def hard_reset_emulator():
    global hard_resetting

    if hard_resetting or not AUTORUN_EMULATOR:
        return

    turn_off_monitor()
    kill_emulator()
    keep_monitor_off_to_emulator(5)

    hard_resetting = True


def ctrl_alt_alt_gr_keyboard_action():
    global ctrl_alt_alt_gr_press_ts

    current_time = time.time()

    if key_ctrl_pressed and key_alt_pressed and key_alt_gr_pressed:
        if not ctrl_alt_alt_gr_press_ts:
            ctrl_alt_alt_gr_press_ts = current_time
    elif not key_ctrl_pressed and not key_alt_pressed and not key_alt_gr_pressed:
        ctrl_alt_alt_gr_press_ts = 0

        clear_reset_marks()

    if ctrl_alt_alt_gr_press_ts:
        if current_time - ctrl_alt_alt_gr_press_ts >= 0.100:
            soft_reset_emulator()

        if ENABLE_CTRL_ALT_ALT_GR_LONG_PRESS_KILL:
            if current_time - ctrl_alt_alt_gr_press_ts >= 8:
                hard_reset_emulator()


def numpad_kp_enter_press():
    global keyboard_controller

    if not ENABLE_CMD_ENTER_KP_ENTER_MAPPING:
        return

    if key_cmd_pressed and key_enter_pressed:
        keyboard_controller.press(PYNPUT_KP_ENTER_KEY)
        keyboard_controller.release(PYNPUT_KP_ENTER_KEY)


def numpad_keys_action():
    numpad_kp_enter_press()


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

        if get_proper_floppy_index(value['label'], value['device']) == floppy_index:
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
    target_idf_index = idf_index

    # remove df<number> from start
    action = action[3:]

    if idf_index + 1 > MAX_FLOPPIES:
        return

    if endswith_dfX(action):
        target_idf_index = int(action[-1])

        # remove df<number> from end
        action = action[:-3]

    detached_floppy_data = detach_floppy(target_idf_index)
    floppy_pattern_name = action.strip()

    update_floppy_drive_sound(target_idf_index)

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

    if attach_mountpoint_floppy(
        medium['device'],
        medium,
        pathname,
        target_idf_index=target_idf_index
    ):
        update_floppy_drive_sound(target_idf_index)


def process_floppy_attach_many_action(partitions: dict, action: str):
    idf_index = int(action[2])

    # remove df<number> from start
    action = action[3:]

    if idf_index + 1 > MAX_FLOPPIES:
        return

    # remove dfn from end
    action = action[:-3]

    floppy_pattern_name = action.strip()

    if not floppy_pattern_name:
        return

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

    similar_roms = find_similar_roms(pathname)
    target_idf_index = 0
    attached = False

    for value in similar_roms:
        if target_idf_index + 1 > MAX_FLOPPIES:
            break

        if floppies[target_idf_index] and floppies[target_idf_index]['pathname'] == value:
            return

        if attach_mountpoint_floppy(
            medium['device'],
            medium,
            value,
            target_idf_index=target_idf_index
        ):
            update_floppy_drive_sound(target_idf_index)

            target_idf_index += 1
            attached = True

    if attached:
        put_local_commit_command(1)


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


def print_wifi_action_commands():
    print_log('Valid WIFI action commands:')
    print_log('WIFI connect: wifi,two alpha country code ISO/IEC 3166-1 alpha2,ssid,password')
    print_log('WIFI disconnect: wifi')


def process_wifi_action(action: str):
    wifi_params = action[4:].strip()

    if not wifi_params:
        disconnect_wifi()

        return

    if not wifi_params.startswith(','):
        print_wifi_action_commands()
        return

    parts = wifi_params[1:].split(',')

    if len(parts) != 3:
        print_wifi_action_commands()
        return

    parts[0] = parts[0].strip().upper()         # country code in ISO/IEC 3166-1 alpha2
    parts[1] = parts[1].strip()                 # ssid
    parts[2] = parts[2].strip()                 # password

    if not parts[0] or not parts[1] or not parts[2]:
        print_wifi_action_commands()
        return

    if len(parts[0]) != 2 or not parts[0].isalpha():
        print_wifi_action_commands()
        return

    os.system('iw reg set {country}'.format(
        country=parts[0]
    ))

    os.system('echo "{password}" | wpa_passphrase "{ssid}" > {config_pathname}'.format(
        password=parts[2],
        ssid=parts[1],
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


def process_floppy_copy_direct_action(source_idf_index, target_idf_index):
    global copy_df_step
    global copy_df_source_index
    global copy_df_target_index
    global copy_df_mode

    if not floppies[source_idf_index] or not floppies[target_idf_index]:
        return

    copy_df_mode = COPY_DF_MODE_DIRECT
    copy_df_step = 0
    copy_df_source_index = source_idf_index
    copy_df_target_index = target_idf_index

    print_log('Low-level direct-copying {source_file} to {target_file} (DF)'.format(
        source_file=floppies[source_idf_index]['pathname'],
        target_file=floppies[target_idf_index]['pathname']
    ))


def process_floppy_copy_indirect_action(source_idf_index):
    global copy_df_step
    global copy_df_source_index
    global copy_df_mode

    if not floppies[source_idf_index]:
        return

    copy_df_mode = COPY_DF_MODE_INDIRECT
    copy_df_step = 0
    copy_df_source_index = source_idf_index

    print_log('Low-level indirect-copying {source_file} to ... (DF)'.format(
        source_file=floppies[source_idf_index]['pathname']
    ))


def process_floppy_copy_action(action: str):
    if is_copying_data():
        # copy operation already pending
        return

    action_data = action[4:].strip()

    if not startswith_dfX(action_data) or not endswith_dfX(action_data):
        return

    if len(action_data) != 6:
        return

    source_idf_index = int(action_data[2])
    target_idf_index = int(action_data[5])

    if source_idf_index == target_idf_index:
        process_floppy_copy_indirect_action(source_idf_index)
        return

    process_floppy_copy_direct_action(source_idf_index, target_idf_index)


def process_hd_copy_action(action: str):
    global copy_hd_step
    global copy_hd_source_index
    global copy_hd_target_index

    if is_copying_data():
        # copy operation already pending
        return

    action_data = action[4:].strip()

    if not startswith_dhX(action_data) or not endswith_dhX(action_data):
        return

    if len(action_data) != 6:
        return

    source_hd_index = int(action_data[2])
    target_hd_index = int(action_data[5])

    if source_hd_index == target_hd_index:
        return

    if not drives[source_hd_index] or not drives[target_hd_index]:
        return

    if not drives[source_hd_index]['is_hdf'] or not drives[target_hd_index]['is_hdf']:
        return

    copy_hd_step = 0
    copy_hd_source_index = source_hd_index
    copy_hd_target_index = target_hd_index

    print_log('Low-level copying {source_file} to {target_file} (HDD)'.format(
        source_file=drives[source_hd_index]['pathname'],
        target_file=drives[target_hd_index]['pathname']
    ))


def copy_df_direct():
    global copy_df_step
    global copy_df_source_data
    global copy_df_target_data
    global copy_df_mode

    if copy_df_step < 0:
        return

    if copy_df_step == 0:
        enable_numlock()

        # mute all sounds
        if ENABLE_COPY_DF_MUTE_SOUNDS:
            mute_system_sound()
            disable_emulator_sound()
            put_local_commit_command(1)
    elif copy_df_step == 1:
        # sync + clear caches
        clear_system_cache()
    elif copy_df_step == 2:
        # eject both floppies
        copy_df_source_data = detach_floppy(copy_df_source_index)
        copy_df_target_data = detach_floppy(copy_df_target_index)

        update_floppy_drive_sound(copy_df_source_index)
        update_floppy_drive_sound(copy_df_target_index)

        put_local_commit_command(1)
    elif copy_df_step == 3:
        # sync + clear caches
        clear_system_cache()
    elif copy_df_step == 4:
        # pause emulator
        pause_emulator(True)
    elif copy_df_step == 5:
        # copy using DD
        os.system('dd bs={block_size} if="{source_file}" of="{target_file}" status=progress'.format(
            block_size=COPY_DF_BLOCK_SIZE,
            source_file=copy_df_source_data['pathname'],
            target_file=copy_df_target_data['pathname']
        ))
    elif copy_df_step == 6:
        # sync + clear caches
        clear_system_cache()
    elif copy_df_step == 7:
        # unpause emulator
        pause_emulator(False)
    elif copy_df_step == 8:
        # unmute all sounds
        if ENABLE_COPY_DF_MUTE_SOUNDS:
            unmute_system_sound()
            enable_emulator_sound()
            put_local_commit_command(1)
    elif copy_df_step == 9:
        if attach_mountpoint_floppy(
            copy_df_source_data['device'],
            copy_df_source_data['medium'],
            copy_df_source_data['pathname'],
            target_idf_index=copy_df_source_index
        ):
            update_floppy_drive_sound(copy_df_source_index)

        if attach_mountpoint_floppy(
            copy_df_target_data['device'],
            copy_df_target_data['medium'],
            copy_df_target_data['pathname'],
            target_idf_index=copy_df_target_index
        ):
            update_floppy_drive_sound(copy_df_target_index)

        put_local_commit_command(1)
        disable_numlock()

        copy_df_step = -1
        copy_df_mode = None

    if copy_df_step != -1:
        copy_df_step += 1


def get_replaced_floppy_index(floppies_seq_numbers_copy):
    if floppies_seq_numbers == floppies_seq_numbers_copy:
        return None

    for index in floppies_seq_numbers:
        if floppies_seq_numbers[index] != floppies_seq_numbers_copy[index]:
            return index

    return None


def copy_df_indirect():
    global copy_df_step
    global copy_df_source_data
    global copy_df_target_data
    global copy_df_mode
    global copy_df_floppies_seq_numbers_copy

    if copy_df_step < 0:
        return

    if copy_df_step == 0:
        enable_numlock()

        # mute all sounds
        if ENABLE_COPY_DF_MUTE_SOUNDS:
            mute_system_sound()
            disable_emulator_sound()
            put_local_commit_command(1)
    elif copy_df_step == 1:
        # sync + clear caches
        clear_system_cache()
    elif copy_df_step == 2:
        # eject both floppies
        copy_df_source_data = detach_floppy(copy_df_source_index)

        update_floppy_drive_sound(copy_df_source_index)

        put_local_commit_command(1)
    elif copy_df_step == 3:
        # sync + clear caches
        clear_system_cache()
    elif copy_df_step == 4:
        # pause emulator
        pause_emulator(True)
    elif copy_df_step == 5:
        # copy using DD
        os.system('dd bs={block_size} if="{source_file}" of="{target_file}" status=progress'.format(
            block_size=COPY_DF_BLOCK_SIZE,
            source_file=copy_df_source_data['pathname'],
            target_file=TMP_ADF_PATHNAME
        ))

        copy_df_floppies_seq_numbers_copy = floppies_seq_numbers.copy()
    elif copy_df_step == 6:
        # sync + clear caches
        clear_system_cache()
    elif copy_df_step == 7:
        if key_esc_pressed:
            # user pressed escape key, just set last step
            # and return
            copy_df_step = 11

            disable_numlock()
            pause_emulator(False)

            if ENABLE_COPY_DF_MUTE_SOUNDS:
                unmute_system_sound()
                enable_emulator_sound()
                put_local_commit_command(1)

            return

        # replaced_index must be exactly the same as copy_df_source_index
        # I'm just checking if the user was replaced the
        # floppy manually
        replaced_index = get_replaced_floppy_index(copy_df_floppies_seq_numbers_copy)

        if replaced_index is None or replaced_index != copy_df_source_index:
            blink_numlock()
            return

        enable_numlock()

        copy_df_source_data = detach_floppy(copy_df_source_index)

        update_floppy_drive_sound(copy_df_source_index)

        os.system('dd bs={block_size} if="{source_file}" of="{target_file}" status=progress'.format(
            block_size=COPY_DF_BLOCK_SIZE,
            source_file=TMP_ADF_PATHNAME,
            target_file=copy_df_source_data['pathname']
        ))
    elif copy_df_step == 8:
        # unpause emulator
        pause_emulator(False)
    elif copy_df_step == 9:
        # unmute all sounds
        if ENABLE_COPY_DF_MUTE_SOUNDS:
            unmute_system_sound()
            enable_emulator_sound()
            put_local_commit_command(1)
    elif copy_df_step == 10:
        if attach_mountpoint_floppy(
            copy_df_source_data['device'],
            copy_df_source_data['medium'],
            copy_df_source_data['pathname'],
            target_idf_index=copy_df_source_index
        ):
            update_floppy_drive_sound(copy_df_source_index)

        put_local_commit_command(1)
        disable_numlock()
    elif copy_df_step == 11:
        copy_df_step = -1
        copy_df_mode = None

    if copy_df_step != -1:
        copy_df_step += 1


def copy_df():
    if copy_df_mode == COPY_DF_MODE_DIRECT:
        copy_df_direct()
    elif copy_df_mode == COPY_DF_MODE_INDIRECT:
        copy_df_indirect()


def copy_hd():
    global copy_hd_step
    global copy_hd_source_data
    global copy_hd_target_data

    if copy_hd_step < 0:
        return

    if copy_hd_step == 0:
        enable_numlock()

        # mute all sounds
        if ENABLE_COPY_HD_MUTE_SOUNDS:
            mute_system_sound()
            disable_emulator_sound()
            put_local_commit_command(1)
    elif copy_hd_step == 1:
        # sync + clear caches
        clear_system_cache()
    elif copy_hd_step == 2:
        # eject both hdds
        copy_hd_source_data = detach_hard_drive(copy_hd_source_index, False)
        copy_hd_target_data = detach_hard_drive(copy_hd_target_index, False)
    elif copy_hd_step == 3:
        # sync + clear caches
        clear_system_cache()
    elif copy_hd_step == 4:
        # pause emulator
        pause_emulator(True)
    elif copy_hd_step == 5:
        # copy using DD
        os.system('dd bs={block_size} if="{source_file}" of="{target_file}" status=progress'.format(
            block_size=COPY_HD_BLOCK_SIZE,
            source_file=copy_hd_source_data['pathname'],
            target_file=copy_hd_target_data['pathname']
        ))
    elif copy_hd_step == 6:
        # sync + clear caches
        clear_system_cache()
    elif copy_hd_step == 7:
        # unpause emulator
        pause_emulator(False)
    elif copy_hd_step == 8:
        # unmute all sounds
        if ENABLE_COPY_HD_MUTE_SOUNDS:
            unmute_system_sound()
            enable_emulator_sound()
            put_local_commit_command(1)
    elif copy_hd_step == 9:
        attach_mountpoint_hard_file(
            copy_hd_source_data['device'],
            copy_hd_source_data['medium'],
            copy_hd_source_data['pathname'],
            target_idh_index=copy_hd_source_index
        )
        attach_mountpoint_hard_file(
            copy_hd_target_data['device'],
            copy_hd_target_data['medium'],
            copy_hd_target_data['pathname'],
            target_idh_index=copy_hd_target_index
        )

        disable_numlock()

        copy_hd_step = -1

    if copy_hd_step != -1:
        copy_hd_step += 1


def process_floppy_replace_by_index_action(action: str):
    global floppies

    idf_index = int(action[2])
    target_idf_index = idf_index

    # remove df<number> from start
    action = action[3:]

    if idf_index + 1 > MAX_FLOPPIES:
        return

    if endswith_dfX(action):
        target_idf_index = int(action[-1])

        # remove df<number> from end
        action = action[:-3]

    if not floppies[idf_index]:
        return

    action_data = action.strip()

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
        if floppies[target_idf_index] and floppies[target_idf_index]['pathname'] == to_insert_pathname:
            return

        detached_floppy_data = detach_floppy(target_idf_index, True)

        if not detached_floppy_data:
            detached_floppy_data = floppies[idf_index]

        update_floppy_drive_sound(target_idf_index)

        device = detached_floppy_data['device']
        medium = detached_floppy_data['medium']

        if attach_mountpoint_floppy(
            device,
            medium,
            to_insert_pathname,
            target_idf_index=target_idf_index
        ):
            update_floppy_drive_sound(target_idf_index)


def process_floppy_detach_all_action() -> List[dict]:
    detached = []

    for idf_index, ifloppy_data in enumerate(floppies):
        if not ifloppy_data:
            continue

        detached_floppy_data = detach_floppy(idf_index)

        if detached_floppy_data:
            update_floppy_drive_sound(idf_index)

            detached.append(detached_floppy_data)

    if detached:
        put_local_commit_command(1)

    return detached


def process_floppy_reverse_all_action():
    detached = process_floppy_detach_all_action()

    if not detached:
        return

    detached.reverse()

    target_idf_index = 0
    attached = False

    for detached_floppy_data in detached:
        device = detached_floppy_data['device']
        medium = detached_floppy_data['medium']

        if attach_mountpoint_floppy(
            device,
            medium,
            detached_floppy_data['pathname'],
            target_idf_index=target_idf_index
        ):
            update_floppy_drive_sound(target_idf_index)

            target_idf_index += 1
            attached = True

    if attached:
        put_local_commit_command(1)


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


def startswith_dfX(s: str) -> bool:
    for idf_index in range(MAX_FLOPPIES):
        if s.startswith('df' + str(idf_index)):
            return True

    return False


def endswith_dfX(s: str) -> bool:
    for idf_index in range(MAX_FLOPPIES):
        if s.endswith('df' + str(idf_index)):
            return True

    return False


def startswith_dhX(s: str) -> bool:
    for dh_index in range(MAX_DRIVES):
        if s.startswith('dh' + str(dh_index)):
            return True

    return False


def endswith_dhX(s: str) -> bool:
    for dh_index in range(MAX_DRIVES):
        if s.endswith('dh' + str(dh_index)):
            return True

    return False


def startswith_cdX(s: str) -> bool:
    for icd_index in range(MAX_CD_DRIVES):
        if s.startswith('cd' + str(icd_index)):
            return True

    return False


def process_tab_combo_action(partitions: dict, action: str):
    len_action = len(action)

    if startswith_dfX(action):
        if len_action == 4 or \
        (len_action == 7 and endswith_dfX(action)):
            # df<source index><disk no>
            # example: df01
            #
            # or
            #
            # df<source index><disk no>df<target index>
            # example: df01df1
            process_floppy_replace_by_index_action(action)

            return
        elif action.endswith('dfn'):
            # df<source index><ADF part file name>dfn
            process_floppy_attach_many_action(partitions, action)

            return

        # df<source index><ADF part file name>
        #
        # or
        #
        # df<source index><ADF part file name>df<target index>
        process_floppy_replace_action(partitions, action)
    elif action == 'dfn':
        # dfn
        process_floppy_detach_all_action()
    elif action == 'dfndfn':
        # dfndfn
        process_floppy_reverse_all_action()
    elif startswith_cdX(action):
        if len_action == 4:
            # cd<source index><disk no>
            # example: cd01
            process_cd_replace_by_index_action(action)

            return

        # cd<source index><ISO part file name>
        process_cd_replace_action(partitions, action)
    elif action.startswith('wifi'):
        # wifi
        #
        # or
        #
        # wifi,<country code in ISO/IEC 3166-1 alpha2>,<ssid>,<password>
        process_wifi_action(action)
    elif action.startswith('copy') and len_action == 10:
        if endswith_dfX(action):
            # copydf<source index>df<target index>
            # direct or indirect floppy copy
            # direct: copydf0df1
            #   both floppies must be attached
            # indirect: copydf0df0
            #   floppy will be dumped then user need
            #   to replace df0 floppy when numlock blinks
            process_floppy_copy_action(action)
        elif endswith_dhX(action):
            # copydh<source index>dh<target index>
            process_hd_copy_action(action)
    # elif action == 'test':
    #     toggle_pause()


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
    ctrl_alt_alt_gr_keyboard_action()
    numpad_keys_action()
    tab_combo_actions(partitions)


def tab_shell():
    # give the user one second so he can press
    # TAB key to enter system shell
    time.sleep(1)

    if not tab_pressed or not ENABLE_TAB_SHELL:
        return

    print_log('')
    print_log('Enter system shell')

    os.system('/bin/sh')


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

    if not ENABLE_AUDIO_LAG_FIX or \
        audio_lag_fix_step == 2 or \
        not is_emulator_running:
        # audio lag fix not enabled, already applied
        # or emulator is not running
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

        run_audio_lag_fix_step_0()

        audio_lag_fix_step += 1
        audio_lag_fix_ts = current_ts
        applied = True
    elif audio_lag_fix_step == 1:
        if current_ts - audio_lag_fix_ts <= AUDIO_LAG_STEP_1_SECS:
            return

        run_audio_lag_fix_step_1()

        audio_lag_fix_step += 1
        audio_lag_fix_ts = current_ts
        applied = True

    if applied:
        print_log('Apply audio lag fix, step={step}'.format(
            step=audio_lag_fix_step - 1
        ))


def set_amiberry_sound_mode(sound_pullmode: int, sound_max_buff: int):
    global amiberry_current_sound_mode

    sign = str(sound_pullmode) + ',' + str(sound_max_buff)

    if sign == amiberry_current_sound_mode:
        return

    amiberry_current_sound_mode = sign

    if sound_pullmode is None and sound_max_buff is None:
        return

    if sound_pullmode is not None:
        put_command('cfgfile_parse_line_type_all amiberry.sound_pullmode=' + str(sound_pullmode))

    if sound_max_buff is not None:
        put_command('cfgfile_parse_line_type_all sound_max_buff=' + str(sound_max_buff))

    put_command('config_changed 1')


def run_audio_lag_fix_step_0():
    # original, working
    set_amiberry_sound_mode(1, 8192)


def run_audio_lag_fix_step_1():
    # original, working
    set_amiberry_sound_mode(None, 16384)


def is_copying_data() -> bool:
    return copy_df_step != -1 or copy_hd_step != -1


def get_partitions2() -> OrderedDict:
    lsblk_buf = StringIO()
    pattern = r'NAME="(\w*)" SIZE="(\d{0,}.\d{0,}[G|M|K])" TYPE="(\w*)" MOUNTPOINT="(.*)" LABEL="(.*)" PATH="(.*)"'
    ret = OrderedDict()

    # lsblk -P -o name,size,type,mountpoint,label,path -n
    sh.lsblk('-P', '-o', 'name,size,type,mountpoint,label,path', '-n', _out=lsblk_buf)

    for line in lsblk_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        search_result = re.search(pattern, line)

        if not search_result:
            continue

        found = search_result.groups()

        full_path = found[5]
        device_data = {
            'mountpoint': found[3],
            'internal_mountpoint': os.path.join(
                INTERNAL_MOUNTPOINTS_PATHNAME,
                found[0]
            ),
            'label': found[4],
            'config': None,
            'device': full_path,
            'is_floppy_drive': False
        }

        if device_data['mountpoint']:
            device_data['config'] = get_mountpoint_config(device_data['mountpoint'])

        device_data['is_floppy_drive'] = is_device_physical_floppy(full_path)

        ret[full_path] = device_data

    return ret


def public_name_to_system_pathname(public_name: str) -> str:
    (name, ext) = os.path.splitext(public_name)

    return name.replace('__', os.path.sep)


def get_amiga_disk_devices() -> OrderedDict:
    result = OrderedDict()

    if not ENABLE_AMIGA_DISK_DEVICES_SUPPORT:
        return result

    try:
        with os.scandir(AMIGA_DISK_DEVICES_MOUNTPOINT) as it:
            for entry in it:
                if entry.name.startswith('.') or not entry.is_file():
                    continue

                if entry.name.endswith(FLOPPY_ADF_EXTENSION):
                    disk_device_type = AMIGA_DISK_DEVICE_TYPE_ADF
                elif entry.name.endswith(HD_HDF_EXTENSION):
                    disk_device_type = AMIGA_DISK_DEVICE_TYPE_HDF
                elif entry.name.endswith(CD_ISO_EXTENSION):
                    disk_device_type = AMIGA_DISK_DEVICE_TYPE_ISO
                else:
                    continue

                full_path = public_name_to_system_pathname(entry.name)

                device_data = {
                    'mountpoint': AMIGA_DISK_DEVICES_MOUNTPOINT,
                    'internal_mountpoint': os.path.join(
                        INTERNAL_MOUNTPOINTS_PATHNAME,
                        entry.name
                    ),
                    'label': entry.name,
                    'config': None,
                    'device': full_path,
                    'is_floppy_drive': False,
                    'drive_index': get_physical_floppy_drive_index(full_path),
                    'public_pathname': os.path.join(AMIGA_DISK_DEVICES_MOUNTPOINT, entry.name),
                    'disk_device_type': disk_device_type
                }

                if device_data['mountpoint']:
                    device_data['config'] = get_mountpoint_config(device_data['mountpoint'])

                device_data['is_floppy_drive'] = is_device_physical_floppy(full_path)

                result[full_path] = device_data
    except OSError:
        pass

    return result


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


def print_physical_floppy_drives():
    if not physical_floppy_drives:
        return

    print_log('Physical floppy drives:')

    for key, drive_data in physical_floppy_drives.items():
        print_log(key)

        print_log('  index: ' + str(drive_data['index']))
        print_log('  device: ' + drive_data['device'])

        print_log()


def init_keyboard_listener():
    global keyboard_listener

    keyboard_listener = Listener(on_press=on_key_press, on_release=on_key_release)
    keyboard_listener.start()


def init_keyboard_controller():
    global keyboard_controller

    keyboard_controller = Controller()


def process_changed_drives():
    global drives_changed

    if not drives_changed:
        return

    drives_changed = False

    hard_reset_emulator()


# following two functions are useful for debugging
def turn_numlock_on():
    os.system('echo 1 | sudo tee /sys/class/leds/input?::numlock/brightness > /dev/null')


def turn_numlock_off():
    os.system('echo 0 | sudo tee /sys/class/leds/input?::numlock/brightness > /dev/null')


def set_sound_output_state(state: str):
    global sound_output_state

    if sound_output_state == state:
        return

    put_command('cfgfile_parse_line_type_all sound_output=' + state)
    put_command('config_changed 1')

    sound_output_state = state


def disable_emulator_sound():
    set_sound_output_state('interrupts')


def enable_emulator_sound():
    set_sound_output_state('exact')


def is_caching_physical_floppy2(additional_seconds: int, include_add = False) -> bool:
    current_time = time.time()

    for drive_index, floppy_data in enumerate(floppies):
        if not floppy_data or not floppy_data['medium']['is_floppy_drive']:
            continue

        if floppy_data['using_amiga_disk_devices'] and not include_add:
            continue

        if not floppy_data['diskstats_change_ts']:
            continue

        if current_time - floppy_data['diskstats_change_ts'] <= additional_seconds:
            if floppy_data['using_amiga_disk_devices'] and include_add:
                if floppy_data['add_status_fully_cached']:
                    continue

            return True

    return False


def refresh_floppies_times() -> False:
    global floppies

    for drive_index, floppy_data in enumerate(floppies):
        if not floppy_data or not floppy_data['medium']['is_floppy_drive']:
            continue

        try:
            file_time = os.stat(floppy_data['pathname'])
        except FileNotFoundError as x:
            print_log(str(x))
            continue

        floppy_data['prev_atime'] = floppy_data['atime']
        floppy_data['atime'] = file_time.st_atime

        floppy_data['prev_mtime'] = floppy_data['mtime']
        floppy_data['mtime'] = file_time.st_mtime

    return True


def is_accessing_physical_floppy3():
    current_time = time.time()
    last_floppy_access_time_mode_1 = 0

    for drive_index, floppy_data in enumerate(floppies):
        if not floppy_data or not floppy_data['medium']['is_floppy_drive']:
            continue

        if floppy_data['using_amiga_disk_devices']:
            continue

        if not floppy_data['diskstats_change_ts']:
            continue

        if floppy_data['diskstats_change_ts'] > last_floppy_access_time_mode_1:
            last_floppy_access_time_mode_1 = floppy_data['diskstats_change_ts']

    if last_floppy_access_time_mode_1:
        if current_time - last_floppy_access_time_mode_1 <= 4:     # 3 better ?
            return True

    return False


def get_floppy_basename_devices() -> list:
    devices = []

    for drive_index, floppy_data in enumerate(floppies):
        if not floppy_data or not floppy_data['medium']['is_floppy_drive']:
            continue

        devices.append(floppy_data['device_basename'])

    return devices


def get_devices_diskstats(basenames: list) -> dict:
    diskstats = {}

    with open('/proc/diskstats', 'r') as file:
        lines = file.read().splitlines()

        for iline in lines:
            iline = iline.strip()

            if not iline:
                continue

            parts = iline.split()

            if len(parts) != 20:
                continue

            device_basename = parts[2]

            if device_basename not in basenames:
                continue

            diskstats[device_basename] = iline

    return diskstats


def refresh_floppies_diskstats():
    global floppies

    basenames = get_floppy_basename_devices()

    if not basenames:
        return False

    diskstats = get_devices_diskstats(basenames)
    current_time = time.time()

    for drive_index, floppy_data in enumerate(floppies):
        if not floppy_data or not floppy_data['medium']['is_floppy_drive']:
            continue

        device_basename = floppy_data['device_basename']

        if device_basename not in diskstats:
            continue

        floppy_data['prev_diskstats'] = floppy_data['diskstats']
        floppy_data['diskstats'] = diskstats[device_basename]

        if floppy_data['prev_diskstats'] != floppy_data['diskstats']:
            floppy_data['diskstats_change_ts'] = current_time

    return True


def get_add_status():
    if not os.path.exists(AMIGA_DISK_DEVICES_STATUS_LOG):
        return {}

    status = {}

    with open(AMIGA_DISK_DEVICES_STATUS_LOG, 'r') as file:
        lines = file.read().splitlines()

        for iline in lines:
            iline = iline.strip()

            if not iline:
                continue

            parts = iline.split(',', 2)
            _map = {}

            for iitem in parts:
                iitem_parts = iitem.strip().split(':', 1)

                _key = iitem_parts[0]
                _value = iitem_parts[1]

                if _key == 'fully_cached':
                    _value = bool(int(_value))

                _map[_key] = _value

            status[_map['device']] = _map

    return status


def refresh_floppies_add_status():
    global floppies

    status = get_add_status()

    for drive_index, floppy_data in enumerate(floppies):
        if not floppy_data or not floppy_data['using_amiga_disk_devices']:
            continue

        device = floppy_data['device']

        if device not in status:
            continue

        floppy_data['add_status_fully_cached'] = status[device]['fully_cached']


def is_writing_physical_floppy() -> bool:
    current_time = time.time()
    last_floppy_write_time = 0

    for drive_index, floppy_data in enumerate(floppies):
        if not floppy_data or not floppy_data['medium']['is_floppy_drive']:
            continue

        if floppy_data['using_amiga_disk_devices']:
            continue

        if not floppy_data['mtime']:
            continue

        if floppy_data['mtime'] != floppy_data['prev_mtime']:
            return True

        if floppy_data['mtime'] > last_floppy_write_time:
            last_floppy_write_time = floppy_data['mtime']

    if last_floppy_write_time:
        if current_time - last_floppy_write_time <= 4:
            return True

    return False


def set_floppy_speed(speed: int):
    global current_floppy_speed

    if current_floppy_speed == speed:
        return

    put_command('cfgfile_parse_line_type_all floppy_speed=' + str(speed))
    put_command('config_changed 1')

    current_floppy_speed = speed


def affect_floppy_speed():
    if not ENABLE_PHYSICAL_FLOPPY_READ_SPEED_HACK:
        return

    is_caching = is_caching_physical_floppy2(1, True)

    if is_caching:
        # turbo
        set_floppy_speed(0)
    else:
        # 100% compatible
        set_floppy_speed(100)


def affect_paula_volume2():
    if is_copying_data():
        # low-level copying in progress, skip
        return

    is_accessing = is_accessing_physical_floppy3()

    if is_accessing:
        is_caching = is_caching_physical_floppy2(4)

        if is_caching:
            mute_system_sound()
            disable_emulator_sound()
    else:
        is_writing = is_writing_physical_floppy()

        if is_writing:
            mute_system_sound()
            disable_emulator_sound()
        else:
            unmute_system_sound()
            enable_emulator_sound()


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
    while os.path.exists(emulator_tmp_ini_pathname) and \
        check_emulator_running():
        time.sleep(0)


def execute_commands():
    # TODO limit execution once every second
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


def get_physical_cdrom_drive_index(device_pathname: str) -> Optional[int]:
    if device_pathname not in physical_cdrom_drives:
        return None

    return physical_cdrom_drives[device_pathname]['index']


def get_physical_floppy_drive_index(device_pathname: str) -> Optional[int]:
    if device_pathname not in physical_floppy_drives:
        return None

    return physical_floppy_drives[device_pathname]['index']


def get_proper_floppy_index(filesystem_label: str, device_pathname: str) -> int:
    '''
    Return floppy drive index that will be used in the emulator (0, 1, 2, 3)
    if user will insert floppy into real floppy drive. In other words
    index from filesystem label will not ne used, it will use floppy drive index
    seen by the system (/dev/sda is 0, /dev/sdb is 1, etc.)
    '''

    if not ENABLE_PHYSICAL_FLOPPY_DRIVES or device_pathname not in physical_floppy_drives:
        return get_label_floppy_index(filesystem_label)

    return get_physical_floppy_drive_index(device_pathname)


def is_device_physical_floppy(device_pathname: str) -> bool:
    return device_pathname in physical_floppy_drives


def is_floppy_label(label: str) -> bool:
    if len(label) != 7:
        return False

    if not label.startswith('AP4_DF'):
        return False

    if not label[6].isdigit():
        return False

    return True


def is_hard_drive_simple_label(label: str) -> bool:
    if len(label) != 7:
        return False

    if not label.startswith('AP4_DH'):
        return False

    if not label[6].isdigit():
        return False

    return True


def is_hard_drive_extended_label(label: str) -> bool:
    if len(label) != 9:
        return False

    if not label.startswith('AP4_DH'):
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

    if not label.startswith('AP4_HDF'):
        return False

    if not label[7].isdigit():
        return False

    return True


def is_hard_file_extended_label(label: str) -> bool:
    if len(label) != 10:
        return False

    if not label.startswith('AP4_HDF'):
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

    if not label.startswith('AP4_CD'):
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


def get_free_dh_index() -> int:
    for idh_no, ihd_data in enumerate(drives):
        if not ihd_data:
            return idh_no

    return None


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
                    get_proper_floppy_index(ipart_data['label'], ipart_data['device'])
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
            drive_index = get_proper_floppy_index(ipart_data['label'], ipart_data['device'])

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
                # attach only one cd per index
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


def cleanup_disk_devices(old_amiga_disk_devices: dict, amiga_disk_devices: dict):
    if not old_amiga_disk_devices:
        return

    for device_pathname in list(old_amiga_disk_devices.keys()):
        if device_pathname not in amiga_disk_devices:
            old_device_data = old_amiga_disk_devices[device_pathname]

            if old_device_data['disk_device_type'] == AMIGA_DISK_DEVICE_TYPE_ADF:
                drive_index = old_device_data['drive_index']

                detach_floppy(drive_index)
                update_floppy_drive_sound(drive_index)
            elif old_device_data['disk_device_type'] == AMIGA_DISK_DEVICE_TYPE_HDF:
                detach_hard_file_by_pathname(old_device_data['public_pathname'])
            elif old_device_data['disk_device_type'] == AMIGA_DISK_DEVICE_TYPE_ISO:
                detach_iso_file_by_pathname(old_device_data['public_pathname'])


def attach_amiga_adf_disk_device(device_pathname: str, device_data: dict, drive_index: int):
    if attach_mountpoint_floppy(
        device_pathname,
        device_data,
        device_data['public_pathname'],
        True
    ):
        update_floppy_drive_sound(
            drive_index
        )

        return True

    return False


def attach_amiga_hdf_disk_device(device_pathname: str, device_data: dict):
    attach_mountpoint_hard_file(
        device_pathname,
        device_data,
        device_data['public_pathname'],
        True
    )


def attach_amiga_iso_disk_device(device_pathname: str, device_data: dict):
    attach_mountpoint_cd_image(
        device_pathname,
        device_data,
        device_data['public_pathname'],
        True
    )


def attach_amiga_disk_devices(amiga_disk_devices: dict):
    attached_floppy_indexes = []

    for device_pathname, device_data in amiga_disk_devices.items():
        if device_data['disk_device_type'] == AMIGA_DISK_DEVICE_TYPE_ADF:
            drive_index = device_data['drive_index']

            if drive_index in attached_floppy_indexes:
                # attach only one floppy per index
                continue

            if attach_amiga_adf_disk_device(
                device_pathname,
                device_data,
                drive_index
            ):
                attached_floppy_indexes.append(drive_index)
        elif device_data['disk_device_type'] == AMIGA_DISK_DEVICE_TYPE_HDF:
            attach_amiga_hdf_disk_device(device_pathname, device_data)
        elif device_data['disk_device_type'] == AMIGA_DISK_DEVICE_TYPE_ISO:
            attach_amiga_iso_disk_device(device_pathname, device_data)


def process_amiga_disk_devices(old_amiga_disk_devices: dict, amiga_disk_devices: OrderedDict):
    cleanup_disk_devices(old_amiga_disk_devices, amiga_disk_devices)
    attach_amiga_disk_devices(amiga_disk_devices)


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

    if not is_medium_auto_insert_file(ipart_data):
        return None

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
            'medium': ipart_data,
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


def attach_mountpoint_hard_file(
    ipart_dev,
    ipart_data,
    force_file_pathname = None,
    auto_hd_no = False,
    target_idh_index = None
):
    global drives
    global drives_changed

    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    ihdf = get_medium_file(
        ipart_dev,
        ipart_data,
        HARD_FILE_EXTENSIONS,
        force_file_pathname
    )

    if not ihdf:
        return False

    if is_hdf_attached(ihdf):
        return False

    if auto_hd_no:
        hd_no = get_free_dh_index()

        if hd_no is None:
            return False
    else:
        if target_idh_index is None:
            hd_no = get_label_hard_file_index(ipart_data['label'])
        else:
            hd_no = target_idh_index

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
            'medium': ipart_data,
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

                detach_hard_drive(idh_no)
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


def toggle_pause():
    pause_emulator(not is_emulator_paused)


def pause_emulator(pause: bool):
    global is_emulator_paused

    is_emulator_paused = pause
    pause_str = '1' if pause else '0'

    put_command('pause_emulation ' + pause_str, False, True)
    put_command('config_changed 1', False, True)


def update_floppy_drive_sound(drive_index: int):
    if ENABLE_FLOPPY_DRIVE_SOUND != 'auto':
        return

    for ioption in get_floppy_drive_sound_config_options():
        put_command('cfgfile_parse_line_type_all ' + ioption)

    put_command('config_changed 1')


def detach_hard_drive(idh_no: int, toggle_drives_changed: bool = True) -> dict:
    global drives
    global drives_changed

    ientry = drives[idh_no]

    drives[idh_no] = None

    if toggle_drives_changed:
        drives_changed = True

    return ientry


def detach_hard_file_by_pathname(pathname: str) -> dict:
    for index, idrive in enumerate(drives.copy()):
        if not idrive:
            continue

        if idrive['pathname'] == pathname:
            return detach_hard_drive(index)

    return None


def detach_iso_file_by_pathname(pathname: str) -> dict:
    for icd_index, icd_data in enumerate(cd_drives.copy()):
        if not icd_data:
            continue

        if icd_data['pathname'] == pathname:
            return detach_cd(icd_index)

    return None


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

    put_command('cfgfile_parse_line_type_all cdimage{index}={pathname},image'.format(
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


def is_adf_attached(pathname: str) -> bool:
    for idf_index, ifloppy_data in enumerate(floppies):
        if not ifloppy_data:
            continue

        if ifloppy_data['pathname'] == pathname:
            return True

    return False


def is_hdf_attached(pathname: str) -> bool:
    for drive_index, drive_data in enumerate(drives):
        if not drive_data:
            continue

        if drive_data['pathname'] == pathname:
            return True

    return False


def is_iso_attached(pathname: str) -> bool:
    for icd_index, icd_data in enumerate(cd_drives):
        if not icd_data:
            continue

        if icd_data['pathname'] == pathname:
            return True

    return False


def attach_mountpoint_floppy(
    ipart_dev,
    ipart_data,
    force_file_pathname = None,
    using_amiga_disk_devices = False,
    target_idf_index = None
):
    global floppies
    global floppies_seq_numbers

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

    if target_idf_index is None:
        index = get_proper_floppy_index(
            ipart_data['label'],
            ipart_data['device']
        )
    else:
        index = target_idf_index

    if index >= MAX_FLOPPIES:
        return False

    if is_adf_attached(iadf):
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
            'device_basename': os.path.basename(ipart_dev),
            'file_size': os.path.getsize(iadf),
            'config': ipart_data['config'],
            'medium': ipart_data,
            'prev_atime': 0,
            'atime': 0,
            'prev_mtime': 0,
            'mtime': 0,
            'diskstats': '',
            'prev_diskstats': '',
            'diskstats_change_ts': 0,
            'using_amiga_disk_devices': using_amiga_disk_devices,
            'add_status_fully_cached': False
        }

        put_command('cfgfile_parse_line_type_all floppy{index}={pathname}'.format(
            index=index,
            pathname=iadf
        ))

        put_command('config_changed 1')

        floppies_seq_numbers[index] += 1

        return True
    else:
        print_log('Floppy already attached to DF{index}, eject it first'.format(
            index=index
        ))

    return False


def attach_mountpoint_cd_image(
    ipart_dev: str,
    ipart_data: dict,
    force_file_pathname: str = None,
    using_amiga_disk_devices = False
):
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

    if using_amiga_disk_devices:
        index = get_physical_cdrom_drive_index(ipart_data['device'])
    else:
        index = get_label_cd_index(ipart_data['label'])

    if index >= MAX_CD_DRIVES:
        return False

    if is_iso_attached(icdimage):
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
            'config': ipart_data['config'],
            'medium': ipart_data
        }

        if ENABLE_CD_REPLACE_RESTART:
            drives_changed = True

        put_command('cfgfile_parse_line_type_all cdimage{index}={pathname},image'.format(
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


def put_command(command: str, reset: bool = False, force = False):
    global commands

    if reset:
        commands = []

    if is_emulator_paused and not force:
        return

    if command:
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

    try:
        config.read(config_pathname)
    except ParsingError:
        return None

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


def check_emulator_running():
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


def get_dir_drive_config_command_line(
    drive_index: int,
    drive_data: dict,
    force_label: str = None,
    force_pathname: str = None,
    force_boot_priority: int = None
):
    config = []

    if force_label is not None:
        label = force_label
    else:
        label = get_medium_partition_label(drive_data)

    if force_boot_priority is not None:
        boot_priority = force_boot_priority
    else:
        boot_priority = get_label_hard_disk_boot_priority(drive_data['label'])

    if not label:
        label = drive_data['label']

    if force_pathname is not None:
        pathname = force_pathname
    else:
        pathname = drive_data['pathname']

    config.append(
        format_filesystem2_string(
            'rw',
            drive_index,
            label,
            pathname,
            boot_priority
        )
    )
    config.append(
        format_uaehf_dir_string(
            drive_index,
            'rw',
            label,
            pathname,
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

    config.append('hardfile2=rw,DH{drive_index}:{pathname},{sectors},{surfaces},{reserved},{blocksize},{boot_priority},,ide{controller_index}_mainboard,0'.format(
        drive_index=drive_index,
        pathname=idrive['pathname'],
        sectors=sectors,
        surfaces=surfaces,
        reserved=reserved,
        blocksize=blocksize,
        boot_priority=boot_priority,
        controller_index=drive_index
    ))
    config.append('uaehf{drive_index}=hdf,rw,DH{drive_index}:{pathname},{sectors},{surfaces},{reserved},{blocksize},{boot_priority},,ide{controller_index}_mainboard,0'.format(
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
    attached_count = 0

    # CD support must be enabled via command line
    # in order to work
    str_cd_drives += ' cd32cd=1 '

    for index, icd in enumerate(cd_drives):
        pathname = ''

        if icd:
            pathname = icd['pathname']
        else:
            pathname = get_empty_cd_pathname()

        if not pathname:
            continue

        str_cd_drives += ' -s cdimage{index}="{pathname},image" '.format(
            index=index,
            pathname=pathname
        )
        attached_count += 1

    if not attached_count:
        # always set at least one CD setting at command line
        # in order to work
        str_cd_drives += ' -s cdimage0=",image" '

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

    # floppy_types
    str_floppy_types = ''

    for index in range(MAX_FLOPPIES):
        str_floppy_types += ' -s floppy{index}type={_type} '.format(
            index=index,
            _type=DEFAULT_FLOPPY_TYPE
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

    # internal drive
    if ENABLE_INTERNAL_DRIVE and \
        key_shift_r_pressed and \
        drive_index < MAX_DRIVES:
        drive_config = get_dir_drive_config_command_line(
            drive_index,
            None,
            INTERNAL_DRIVE_LABEL,
            INTERNAL_MOUNTPOINTS_PATHNAME,
            INTERNAL_DRIVE_BOOT_BRIORITY
        )

        str_drives += ' -s {config0} -s {config1} '.format(
            config0=drive_config[0],
            config1=drive_config[1]
        )

        drive_index += 1

    # cd drives
    str_cd_drives = get_cd_drives_command_line_config()

    return {
        'floppies': str_floppies,
        'floppy_types': str_floppy_types,
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

    return config_str


def get_emulator_additional_command_line_config():
    config_str = ''

    for ioption in current_amiga_kickstart2model['additional_config_options']:
        config_str += ' -s ' + ioption + ' '

    return config_str


def get_ext_kickstart_command_line_config():
    extended_kickstart = ''

    if kickstart_extended_pathname:
        extended_kickstart = '-K "{pathname}"'.format(
            pathname=kickstart_extended_pathname
        )

    return extended_kickstart


def get_emulator_full_command_line():
    media_config = get_media_command_line_config()
    config_options = get_emulator_command_line_config()
    additional_config_options = get_emulator_additional_command_line_config()
    extended_kickstart = get_ext_kickstart_command_line_config()

    return EMULATOR_RUN_PATTERN.format(
        executable=emulator_exe_pathname,
        amiga_model_id=current_amiga_kickstart2model['amiga_model_id'],
        nr_floppies=MAX_FLOPPIES,
        config_options=config_options,
        kickstart=kickstart_pathname,
        extended_kickstart=extended_kickstart,
        floppies=media_config['floppies'],
        floppy_types=media_config['floppy_types'],
        drives=media_config['drives'],
        cd_drives=media_config['cd_drives'],
        additional_config_options=additional_config_options
    )


def print_emulator_full_command_line():
    global printed_emulator_full_command_line

    if printed_emulator_full_command_line:
        return

    pattern = get_emulator_full_command_line()

    print_log('Emulator command line: ' + pattern)

    printed_emulator_full_command_line = True


def run_emulator():
    global floppies

    print_log('Running emulator')

    pattern = get_emulator_full_command_line()

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

    pathname = os.path.join(INTERNAL_MOUNTPOINTS_PATHNAME, '*')

    os.system('rmdir ' + pathname)


def clear_system_cache():
    print_log('Clearing system cache')

    os.system('sync')
    os.system('echo 1 > /proc/sys/vm/drop_caches')
    os.system('sync')


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


def find_physical_floppy_drives():
    ufiformat_buf = StringIO()
    ret = []

    # ufiformat --inquire --quiet
    sh.ufiformat('--inquire', '--quiet', _out=ufiformat_buf)

    for line in ufiformat_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        parts = line.split()

        if len(parts) != 2:
            continue

        device = parts[0]

        if not os.path.exists(device) or not os.path.isfile(device):
            ret.append(device)

    return ret


def update_physical_floppy_drives():
    # HACK do not use MAX_FLOPPIES here, just collect all physical drives
    # HACK MAX_FLOPPIES will be used elsewhere
    global physical_floppy_drives

    print_log('Getting information about physical floppy drives')

    physical_floppy_drives = OrderedDict()
    index = 0

    for device in sorted(find_physical_floppy_drives()):
        physical_floppy_drives[device] = {
            'index': index,
            'device': device
        }

        index += 1


def find_physical_cdrom_drives():
    hwinfo_buf = StringIO()
    cdrom_data_started = False
    ret = []

    # hwinfo --cdrom --short
    sh.hwinfo('--cdrom', '--short', _out=hwinfo_buf)

    for line in hwinfo_buf.getvalue().splitlines():
        line = line.strip()

        if not line:
            continue

        if line == 'cdrom:':
            cdrom_data_started = True
            continue

        if not cdrom_data_started:
            continue

        if not line.startswith('/dev/'):
            continue

        parts = line.split(maxsplit=1)

        if len(parts) != 2:
            continue

        device = parts[0]

        if not os.path.exists(device) or not os.path.isfile(device):
            ret.append(device)

    return ret


def update_physical_cdrom_drives(physical_cdrom_drives):
    print_log('Getting information about physical cd-rom drives')

    index = 0

    for device in sorted(find_physical_cdrom_drives()):
        physical_cdrom_drives[device] = {
            'index': index,
            'device': device
        }

        index += 1


def print_physical_cdrom_drives(physical_cdrom_drives):
    print_log('Physical cd-rom drives:')

    for key, drive_data in physical_cdrom_drives.items():
        print_log(key)

        print_log('  index: ' + str(drive_data['index']))
        print_log('  device: ' + drive_data['device'])

        print_log()


def is_alt_gr_key(key) -> bool:
    if key == Key.alt_gr:
        return True

    if hasattr(key, 'vk'):
        if key.vk == ALT_GR_KEYCODE:
            return True
        elif key.vk == ALT_GR_UK_KEYCODE:
            return True

    return False


def on_key_press(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_alt_gr_pressed
    global key_shift_r_pressed
    global tab_pressed
    global key_cmd_pressed
    global key_enter_pressed
    global key_esc_pressed
    global ctrl_alt_alt_gr_press_ts
    global tab_combo

    if key == Key.ctrl:
        key_ctrl_pressed = True

    if key == Key.alt:
        key_alt_pressed = True

    if is_alt_gr_key(key):
        key_alt_gr_pressed = True

    if key == Key.shift_r:
        key_shift_r_pressed = True

    if key == Key.tab:
        tab_pressed = True

    if key == Key.cmd:
        key_cmd_pressed = True

    if key == Key.enter:
        key_enter_pressed = True

    if key == Key.esc:
        key_esc_pressed = True

    if key == Key.esc:
        tab_combo = []
    else:
        tab_combo.append(key)

    if len(tab_combo) >= 255:
        tab_combo = []


def on_key_release(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_alt_gr_pressed
    global key_shift_r_pressed
    global tab_pressed
    global key_cmd_pressed
    global key_enter_pressed
    global key_esc_pressed
    global ctrl_alt_alt_gr_press_ts

    if key == Key.ctrl:
        key_ctrl_pressed = False

    if key == Key.alt:
        key_alt_pressed = False

    if is_alt_gr_key(key):
        key_alt_gr_pressed = False

    if key == Key.shift_r:
        key_shift_r_pressed = False

    if key == Key.tab:
        tab_pressed = False

    if key == Key.cmd:
        key_cmd_pressed = False

    if key == Key.enter:
        key_enter_pressed = False

    if key == Key.esc:
        key_esc_pressed = False


def atexit_handler():
    unmute_system_sound()
    umount_tmpfs()


print_app_version()
check_pre_requirements()
init_logger()
setup_amiga_model()
setup_extended_kickstart()
overwrite_amiga_config_by_kickstart()
print_current_amiga_kickstart2model()
mount_tmpfs()
copy_kickstart()
atexit.register(atexit_handler)
configure_tmp_ini()
configure_system()
init_simple_mixer_control()
configure_volumes()
clear_system_cache()
delete_unused_mountpoints()
connect_wifi()
update_physical_floppy_drives()
print_physical_floppy_drives()
update_physical_cdrom_drives(physical_cdrom_drives)
print_physical_cdrom_drives(physical_cdrom_drives)
init_keyboard_listener()
init_keyboard_controller()
tab_shell()

while True:
    unmounted = []
    new_mounted = []
    new_attached = []
    new_detached = []
    other_attached = []

    partitions = get_partitions2()
    is_emulator_running = check_emulator_running()

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

    amiga_disk_devices = get_amiga_disk_devices()

    if amiga_disk_devices != old_amiga_disk_devices:
        process_amiga_disk_devices(old_amiga_disk_devices, amiga_disk_devices)

    if unmounted or new_mounted or new_attached or new_detached or other_attached:
        # something changed
        print_partitions(partitions)
        print_attached_floppies()
        print_attached_hard_disks()
        print_attached_cd_images()

    if new_mounted or unmounted:
        delete_unused_mountpoints()

    old_partitions = partitions
    old_amiga_disk_devices = amiga_disk_devices

    process_changed_drives()

    refresh_floppies_times()
    refresh_floppies_diskstats()
    refresh_floppies_add_status()

    affect_floppy_speed()
    affect_paula_volume2()

    if commands:
        print_commands()
        execute_commands()

    if is_emulator_running == False:
        run_emulator()
        reset_audio_lag_fix()
    elif is_emulator_running == None:
        print_emulator_full_command_line()

    keyboard_actions(partitions)
    update_monitor_state()
    other_actions()
    audio_lag_fix()
    copy_df()
    copy_hd()

    time.sleep(100 / 1000)
    time.sleep(0)
