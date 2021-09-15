import sys
import os

assert sys.platform == 'linux', 'This script must be run only on Linux'
assert sys.version_info.major >= 3 and sys.version_info.minor >= 5, 'This script requires Python 3.5+'
assert os.geteuid() == 0, 'This script must be run as root'

try:
    import sh
    import time
    import tempfile
    import re
    import subprocess
    import logzero

    from collections import OrderedDict
    from io import StringIO
except ImportError as xie:
    print(str(xie))
    sys.exit(1)


APP_UNIXNAME = 'amiga_disk_devices'
APP_VERSION = '0.1'
TMP_PATH_PREFIX = os.path.join(tempfile.gettempdir(), APP_UNIXNAME)
LOG_PATHNAME = os.path.join(TMP_PATH_PREFIX, 'amiga_disk_devices.log')
ENABLE_LOGGER = False
SYNC_DISKS_SECS = 60 * 3
FLOPPY_EXTENSIONS = ['*.adf']

partitions = None
old_partitions = None
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
    print('{name} v{version}'. format(
        name=APP_UNIXNAME.upper(),
        version=APP_VERSION
    ))


def check_pre_requirements():
    check_system_binaries()


def configure_system():
    print_log('Configuring system')


def check_system_binaries():
    print_log('Checking system binaries')

    bins = [
        'lsblk',
        'clear'
    ]

    for ibin in bins:
        if not sh.which(ibin):
            print_log(ibin + ': command not found')
            sys.exit(1)


def other_actions():
    if ENABLE_LOGGER:
        # logger enabled so clear the console
        os.system('clear')


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
            'label': found[4],
            'config': None,
            'device': full_path,
            'is_floppy_drive': False
        }

        ret[full_path] = device_data

    return ret


def print_partitions(partitions: dict):
    if not partitions:
        return

    print_log('Known partitions:')

    for key, value in partitions.items():
        print_log(key)

        print_log('  mountpoint: ' + str(value['mountpoint']))
        print_log('  label: ' + str(value['label']))
        print_log('  is_floppy_drive: ' + str(value['is_floppy_drive']))

        print_log()


print_app_version()
init_logger()
check_pre_requirements()
configure_system()

while True:
    partitions = get_partitions2()

    if partitions != old_partitions:
        # something changed
        print_partitions(partitions)

    old_partitions = partitions

    other_actions()
    sync()

    time.sleep(1)
