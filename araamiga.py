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

    from pprint import pprint
    from collections import OrderedDict
    from typing import Optional
    from io import StringIO
    from pynput.keyboard import Key, Listener
    from configparser import ConfigParser
except ImportError as xie:
    print_log(xie)
    sys.exit(1)


APP_UNIXNAME = 'araamiga'
TMP_PATH_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
CONFIG_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'default.uae')
LOG_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'araamiga.log')
ENABLE_LOGGER = False
ENABLE_MOUSE_UNGRAB = False
ENABLE_F12_GUI = True
ENABLE_TURN_OFF_MONITOR = True
EMULATOR_EXE_PATHNAME = 'amiberry'
EMULATOR_TMP_INI_PATHNAME = os.path.join(os.path.dirname(os.path.realpath(EMULATOR_EXE_PATHNAME)), 'amiberry.tmp.ini')
MAX_FLOPPIES = 4
MAX_DRIVES = 6
MODEL = 'A1200'
KICKSTART_PATHNAME = 'kickstarts/Kickstart3.1.rom'
EMULATOR_RUN_PATTERN = '{executable} -m {MODEL} -G --config {config_pathname} -r {KICKSTART_PATHNAME}'
CONFIG_INI_NAME = '.araamiga.ini'
DEFAULT_BOOT_PRIORITY = 0
AUTORUN_EMULATOR = True
AUTOSEND_SIGNAL = True
MONITOR_STATE_ON = 1
MONITOR_STATE_KEEP_OFF = 0
MONITOR_STATE_KEEP_OFF_TO_EMULATOR = 2
CUSTOM_CONFIG = {
    'cpu_type': '68ec020',
    'cpu_model': '68020',
    'cpu_multiplier': '2',
    'amiberry__gfx_correct_aspect': '0',
    'gfx_width': '720',
    'gfx_width_windowed': '720',
    'gfx_height': '568',
    'gfx_height_windowed': '568',
    # 'gfx_fullscreen_amiga': 'false',
    # 'gfx_fullscreen_picasso': 'false',
    'gfx_fullscreen_amiga': 'fullwindow',
    'gfx_fullscreen_picasso': 'fullwindow',
    'joyport1': 'none',
    'chipset': 'aga',
    'finegrain_cpu_speed': '1024',
    'bsdsocket_emu': 'true',
    'chipmem_size': '16',
    'show_leds': 'false',
    'amiberry__open_gui': 'none',
    'magic_mouse': 'none',
    'hard_drives': ''
}
CONFIG = """
config_description=UAE default configuration
config_hardware=true
config_host=true
config_version=4.4.0
config_hardware_path=
config_host_path=
config_all_path=
amiberry.rom_path=./
amiberry.floppy_path=./
amiberry.hardfile_path=./
amiberry.cd_path=./
; 
; *** Controller/Input Configuration
; 
joyport0=mouse
joyport0_autofire=none
joyport0_friendlyname=Mouse
joyport0_name=MOUSE0
; 
joyport1={joyport1}
joyport1_autofire=none
joyport1_friendlyname=ShanWan PS3/PC Adaptor
joyport1_name=JOY1
; 
; 
; 
input.joymouse_speed_analog=2
input.joymouse_speed_digital=10
input.joymouse_deadzone=33
input.joystick_deadzone=33
input.analog_joystick_multiplier=18
input.analog_joystick_offset=-5
input.mouse_speed=100
input.autofire_speed=600
input.autoswitch=1
kbd_lang=us
; 
; *** Host-Specific
; 
amiberry.gfx_auto_height=false
amiberry.gfx_correct_aspect={amiberry__gfx_correct_aspect}
amiberry.kbd_led_num=-1
amiberry.kbd_led_scr=-1
amiberry.scaling_method=-1
amiberry.allow_host_run=false
amiberry.use_analogue_remap=false
amiberry.use_retroarch_quit=true
amiberry.use_retroarch_menu=true
amiberry.use_retroarch_reset=false
amiberry.active_priority=1
amiberry.inactive_priority=0
amiberry.minimized_priority=0
amiberry.minimized_input=0
; 
; *** Common / Paths
; 
show_leds={show_leds}
use_gui=no
kickstart_rom_file=/home/pi/projects.local/amiberry/kickstarts/kick40068.A1200
kickstart_rom_file_id=1483A091,KS ROM v3.1 (A1200)
kickstart_ext_rom_file=
pcmcia_mb_rom_file=:ENABLED
ide_mb_rom_file=:ENABLED
flash_file=
cart_file=
rtc_file=
kickshifter=false
; 
; *** Floppy Drives
; 
floppy_volume=33
floppy0={floppy0}
floppy1={floppy1}
floppy1type=-1
floppy2={floppy2}
floppy3={floppy3}
nr_floppies=1
floppy_speed=100
; 
; *** Hard Drives
; 
{hard_drives}
scsi=false
; 
; *** CD / CD32
; 
cd_speed=100
; 
; *** Display / Screen Setup
; 
gfx_framerate=1
gfx_width={gfx_width}
gfx_height={gfx_height}
gfx_top_windowed=0
gfx_left_windowed=0
gfx_width_windowed={gfx_width_windowed}
gfx_height_windowed={gfx_height_windowed}
gfx_width_fullscreen=800
gfx_height_fullscreen=600
gfx_refreshrate=50
gfx_refreshrate_rtg=50
gfx_backbuffers=2
gfx_backbuffers_rtg=1
gfx_vsync=false
gfx_vsyncmode=normal
gfx_vsync_picasso=false
gfx_vsyncmode_picasso=normal
gfx_lores=false
gfx_resolution=hires
gfx_lores_mode=normal
gfx_flickerfixer=false
gfx_linemode=none
gfx_fullscreen_amiga={gfx_fullscreen_amiga}
gfx_fullscreen_picasso={gfx_fullscreen_picasso}
gfx_center_horizontal=none
gfx_center_vertical=none
gfx_colour_mode=32bit
gfx_blacker_than_black=false
gfx_api=directdraw
gfx_api_options=hardware
; 
; *** CPU options
; 
finegrain_cpu_speed={finegrain_cpu_speed}
cpu_throttle=0.0
cpu_type={cpu_type}
cpu_model={cpu_model}
; cpu_multiplier not exists in default config
cpu_multiplier={cpu_multiplier}
cpu_compatible=true
cpu_24bit_addressing=true
cpu_data_cache=false
cpu_cycle_exact=false
cpu_memory_cycle_exact=true
blitter_cycle_exact=false
cycle_exact=false
fpu_strict=false
comp_trustbyte=direct
comp_trustword=direct
comp_trustlong=direct
comp_trustnaddr=direct
comp_nf=true
comp_constjump=true
comp_flushmode=soft
compfpu=false
comp_catchfault=true
cachesize=0
; 
; *** Memory
; 
z3mapping=real
fastmem_size=0
a3000mem_size=0
mbresmem_size=0
z3mem_size=0
z3mem_start=0x40000000
bogomem_size=0
gfxcard_hardware_vblank=false
gfxcard_hardware_sprite=false
gfxcard_multithread=false
chipmem_size={chipmem_size}
rtg_modes=0x112
; 
; *** Chipset
; 
immediate_blits=false
fast_copper=false
ntsc=false
chipset={chipset}
chipset_refreshrate=49.920410
collision_level=playfields
chipset_compatible=A1200
rtc=none
ksmirror_a8=true
pcmcia=true
ide=a600/a1200
; 
; *** Sound Options
; 
sound_output=exact
sound_channels=stereo
sound_stereo_separation=7
sound_stereo_mixing_delay=0
sound_max_buff=16384
sound_frequency=44100
sound_interpol=anti
sound_filter=emulated
sound_filter_type=standard
sound_volume=0
sound_volume_paula=0
sound_volume_cd=20
sound_volume_ahi=0
sound_volume_midi=0
sound_volume_genlock=0
sound_auto=true
sound_cdaudio=false
sound_stereo_swap_paula=false
sound_stereo_swap_ahi=false
; 
; *** Misc. Options
; 
parallel_on_demand=false
serial_on_demand=false
serial_hardware_ctsrts=true
serial_direct=false
uaeserial=false
sana2=false
bsdsocket_emu={bsdsocket_emu}
synchronize_clock=false
maprom=0x0
parallel_postscript_emulation=false
parallel_postscript_detection=false
ghostscript_parameters=
parallel_autoflush=5
; 
; *** WHDLoad Booter. Options
; 
whdload_slave=
whdload_showsplash=false
whdload_buttonwait=false
whdload_custom1=0
whdload_custom2=0
whdload_custom3=0
whdload_custom4=0
whdload_custom5=0
whdload_custom=

; 
; *** ARA custom options
; 
amiberry.open_gui={amiberry__open_gui}
magic_mouse={magic_mouse}
"""

floppies = [None for x in range(MAX_FLOPPIES)]
drives = [None for x in range(MAX_DRIVES)]
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


def check_pre_requirements():
    check_emulator()
    check_system_binaries()


def configure_system():
    print_log('Configuring system')

    os.system('swapoff -a')
    os.system('sysctl -q vm.swappiness=0')
    os.system('sysctl -q vm.vfs_cache_pressure=200')


def check_emulator():
    global EMULATOR_EXE_PATHNAME

    print_log('Checking emulator')

    emu_real_pathname = os.path.realpath(EMULATOR_EXE_PATHNAME)

    if not os.path.exists(emu_real_pathname):
        print_log('Emulator executable ' + EMULATOR_EXE_PATHNAME + ' does not exists')
        sys.exit(1)

    EMULATOR_EXE_PATHNAME = emu_real_pathname


def check_system_binaries():
    print_log('Checking system binaries')

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
        'swapoff',
        'xset',
        'clear'
    ]

    for ibin in bins:
        if not sh.which(ibin):
            print_log(ibin + ': command not found')
            sys.exit(1)


monitor_off_timestamp = 0
monitor_state = MONITOR_STATE_ON
monitor_off_seconds = 0


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

        put_command('uae_reset 0,0')
        clear_system_cache()
    elif not key_ctrl_pressed and not key_alt_pressed and not key_delete_pressed:
        ctrl_alt_del_press_ts = 0

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


def find_similar_file(directory, pattern):
    adfs = mountpoint_find_files(directory, '*.adf')

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


def process_floppy_replace_action(action: str):
    idf_index = int(action[2])

    if idf_index + 1 > MAX_FLOPPIES:
        return

    put_command('ext_disk_eject {index}'.format(
        index=idf_index
    ))

    action_data = action[3:].strip()

    if not action_data:
        return

    pathname = find_similar_file(
        floppies[idf_index]['mountpoint'],
        action_data
    )

    if not pathname:
        return

    device = floppies[idf_index]['device']
    medium = floppies[idf_index]['medium']

    floppies[idf_index] = None

    attach_mountpoint_floppy(device, medium, pathname)


def process_tab_combo_action(action: str):
    if action.startswith('df0') or action.startswith('df1') or action.startswith('df2') or action.startswith('df4'):
        process_floppy_replace_action(action)


def action_to_str(action: list) -> str:
    action_str = ''

    for c in action:
        try:
            action_str += c.char
        except:
            pass

    return action_str


def tab_combo_actions():
    global tab_combo

    if len(tab_combo) <= 4:
        return

    if tab_combo[-1] != Key.tab or tab_combo[-2] != Key.tab:
        return
    
    if tab_combo[0] != Key.tab or tab_combo[1] != Key.tab:
        return

    action_str = action_to_str(tab_combo)
    tab_combo = []

    process_tab_combo_action(action_str)


def keyboard_actions():
    ctrl_alt_del_keyboard_action()
    tab_combo_actions()


def other_actions():
    if ENABLE_LOGGER:
        # logger enabled so clear the console
        os.system('clear')

    os.system('sync')


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
                TMP_PATH_PREFIX,
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

    print_log('Known partitions:')

    for key, value in partitions.items():
        print_log(key)

        print_log('  mountpoint: ' + str(value['mountpoint']))
        print_log('  internal_mountpoint: ' + value['internal_mountpoint'])
        print_log('  label: ' + str(value['label']))

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

    generate_config()

    if AUTORUN_EMULATOR:
        turn_off_monitor()
        kill_emulator()
        keep_monitor_off_to_emulator(5)


def send_SIGUSR1_signal():
    if not AUTOSEND_SIGNAL:
        return

    print_log('Sending SIGUSR1 signal to Amiberry emulator')

    try:
        sh.killall('-USR1', 'amiberry')
    except sh.ErrorReturnCode_1:
        print_log('No process found')


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

    print_log(EMULATOR_TMP_INI_PATHNAME + ' contents:')
    print_log(contents)

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

        print_log('Mounting ' + key + ' as ' + value['internal_mountpoint'])

        os.makedirs(value['internal_mountpoint'], exist_ok=True)

        force_fsck(key)
        force_all_rw(key)

        sh.mount(key, '-ouser,umask=0000,sync', value['internal_mountpoint'])

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


def get_label_floppy_index(label: str):
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


def force_fsck(pathname: str):
    try:
        sh.fsck('-y', pathname)
    except (sh.ErrorReturnCode_1, sh.ErrorReturnCode_6) as x:
        print_log(str(x))
        print_log('Failed to force-fsck ' + pathname)


def force_all_rw(pathname: str):
    try:
        sh.chmod('-R', 'a+rw', pathname)
    except sh.ErrorReturnCode_1 as x1:
        print_log(str(x1))
        print_log('Failed to chmod a+rw ' + pathname)


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

    hdfs = mountpoint_find_files(mountpoint, '*.hdf')

    if not hdfs:
        return False

    first_hdf = hdfs[0]
    hd_no = get_label_hard_file_index(ipart_data['label'])

    if hd_no >= MAX_DRIVES:
        return False

    if not drives[hd_no] or drives[hd_no]['pathname'] != first_hdf:
        print_log('Attaching "{pathname}" to DH{index} (HDF)'.format(
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
    global drives_changed

    detached = []

    for idevice in unmounted:
        for idf_index, ifloppy_data in enumerate(floppies):
            if not ifloppy_data:
                continue

            if ifloppy_data['device'] == idevice:
                print_log('Detaching "{pathname}" from DF{index}'.format(
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
                print_log('Detaching "{pathname}" from DH{index}'.format(
                    pathname=ihd_data['pathname'],
                    index=idh_no
                ))

                is_dir = ihd_data['is_dir']

                drives[idh_no] = None
                drives_changed = True

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


def attach_mountpoint_floppy(ipart_dev, ipart_data, force_file_pathname = None):
    mountpoint = ipart_data['mountpoint']

    force_all_rw(mountpoint)

    adfs = mountpoint_find_files(mountpoint, '*.adf')

    if not adfs:
        return False

    if force_file_pathname and force_file_pathname in adfs:
        iadf = force_file_pathname
    else:
        iadf = adfs[0]

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

        put_command('ext_disk_insert_force {df_no},{pathname},0'.format(
            df_no=index,
            pathname=iadf
        ))

        return True
    else:
        print_log('Floppy already attached to DF{index}, eject it first'.format(
            index=index
        ))

    return False


def clear_system_cache(force = False):
    print_log('Clearing system cache')

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


def get_medium_label(medium_data):
    if not medium_data['config']:
        return None

    if 'partition' not in medium_data['config']:
        return None

    if 'label' not in medium_data['config']['partition']:
        return None

    return medium_data['config']['partition']['label']


def is_emulator_running():
    if not AUTORUN_EMULATOR:
        return None

    for iprocess in psutil.process_iter(attrs=['exe']):
        if iprocess.info['exe'] == EMULATOR_EXE_PATHNAME:
            return True

    return False


def get_dir_drive_config_command_line(drive_index: int, drive_data: dict):
    config = []

    label = get_medium_label(drive_data)
    boot_priority = get_label_hard_disk_boot_priority(drive_data['label'])

    if not label:
        label = drive_data['label']

    config.append('filesystem2=rw,DH{drive_index}:{label}:{pathname},{boot_priority}'.format(
        drive_index=drive_index,
        label=label,
        pathname=drive_data['pathname'],
        boot_priority=boot_priority
    ))
    config.append('uaehf{drive_index}=dir,rw,DH{drive_index}:{label}:{pathname},{boot_priority}'.format(
        drive_index=drive_index,
        label=label,
        pathname=drive_data['pathname'],
        boot_priority=boot_priority
    ))

    return config


def get_hdf_drive_config_command_line(drive_index: int, idrive: dict):
    config = []

    boot_priority = get_label_hard_file_boot_priority(idrive['label'])

    config.append('hardfile2=rw,DH{drive_index}:{pathname},0,0,0,512,{boot_priority},,uae1,0'.format(
        drive_index=drive_index,
        pathname=idrive['pathname'],
        boot_priority=boot_priority
    ))
    config.append('uaehf{drive_index}=hdf,rw,DH{drive_index}:{pathname},0,0,0,512,{boot_priority},,uae1,0'.format(
        drive_index=drive_index,
        pathname=idrive['pathname'],
        boot_priority=boot_priority
    ))

    return config


def generate_config(with_hard_drives = True):
    # make config copy from default config
    config_copy = copy.deepcopy(CONFIG)
    config_data_copy = CUSTOM_CONFIG.copy()

    # floppies
    for index, ifloppy in enumerate(floppies):
        index_str = str(index)

        config_data_copy['floppy' + index_str] = ''

        if ifloppy:
            config_data_copy['floppy' + index_str] = ifloppy['pathname']

    # hard drives
    drive_index = 0
    hard_drives = ''

    if with_hard_drives:
        for index, idrive in enumerate(drives):
            if idrive:
                if idrive['is_dir']:
                    drive_config = get_dir_drive_config_command_line(drive_index, idrive)

                    hard_drives += drive_config[0] + '\n'
                    hard_drives += drive_config[1] + '\n'

                    drive_index += 1
                elif idrive['is_hdf']:
                    drive_config = get_hdf_drive_config_command_line(drive_index, idrive)

                    hard_drives += drive_config[0] + '\n'
                    hard_drives += drive_config[1] + '\n'

                    drive_index += 1

    config_data_copy['hard_drives'] = hard_drives

    if ENABLE_F12_GUI:
        config_data_copy['amiberry__open_gui'] = ''
    
    if ENABLE_MOUSE_UNGRAB:
        config_data_copy['magic_mouse'] = '1'

    # fill config
    config_copy = config_copy.format_map(config_data_copy)

    with open(CONFIG_PATHNAME, 'w+', newline=None) as f:
        f.write(config_copy)


def run_emulator():
    global floppies

    print_log('Running emulator')

    generate_config()

    pattern = EMULATOR_RUN_PATTERN.format(
        executable=EMULATOR_EXE_PATHNAME,
        MODEL=MODEL,
        config_pathname=CONFIG_PATHNAME,
        KICKSTART_PATHNAME=KICKSTART_PATHNAME
    )

    print_log('Emulator command line: ' + pattern)

    subprocess.Popen(pattern, cwd=os.path.dirname(EMULATOR_EXE_PATHNAME), shell=True)

    time.sleep(0)


def kill_emulator():
    print_log('Sending SIGKILL signal to Amiberry emulator')

    try:
        sh.killall('-9', 'amiberry')
    except sh.ErrorReturnCode_1:
        print_log('No process found')


def on_key_press(key):
    global key_ctrl_pressed
    global key_alt_pressed
    global key_delete_pressed
    global ctrl_alt_del_press_ts
    global tab_combo
    global tab_combo_recording

    if key == Key.ctrl:
        key_ctrl_pressed = True

    if key == Key.alt:
        key_alt_pressed = True

    if key == Key.delete:
        key_delete_pressed = True

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
    global ctrl_alt_del_press_ts

    if key == Key.ctrl:
        key_ctrl_pressed = False

    if key == Key.alt:
        key_alt_pressed = False

    if key == Key.delete:
        key_delete_pressed = False


init_logger()
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
        print_log('Unmounted partitions')

        new_detached = process_unmounted(unmounted)

    # mount new partitions
    new_mounted = mount_partitions(partitions)

    if new_mounted:
        print_log('Mounted new partitions')

        new_attached = process_new_mounted(partitions, new_mounted)

    other_attached = process_other_mounted(partitions)

    if unmounted or new_mounted or new_attached or new_detached or other_attached:
        # something changed
        print_partitions(partitions)
        print_attached_floppies()
        print_attached_hard_disks()

        clear_system_cache()

    old_partitions = partitions

    process_changed_drives()
    print_commands()

    if commands:
        execute_commands()
        clear_system_cache()

    if is_emulator_running() == False:
        run_emulator()

    keyboard_actions()
    update_monitor_state()
    other_actions()

    time.sleep(1)
