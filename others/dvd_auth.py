import fcntl


# Authentication
DVD_AUTH = 0x5392
DVD_AUTH_ESTABLISHED = 5
DVD_AUTH_FAILURE = 6

dvd_auth_buff = bytearray(1024)

with open('/dev/sr0') as fobj:
    print('ok')

    fd = fobj.fileno()

    print('fd ' + str(fd))

    err = fcntl.ioctl(fd, DVD_AUTH, dvd_auth_buff)

    print('err ' + str(err))




