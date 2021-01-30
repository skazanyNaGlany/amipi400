#include <cstdio>
#include <string>
#include <unistd.h>


#define BUFF_LEN 512


void read_all(FILE *f, size_t size) {
    char buff[BUFF_LEN];
    size_t off;

    printf("reading contents\n");

    fflush(f);
    fsync(fileno(f));

    while (fread(buff, 1, BUFF_LEN, f) == BUFF_LEN) {
        fflush(f);
        fsync(fileno(f));

        off = ftell(f);

        printf("offset %zu\n", off);

        fflush(f);
        fsync(fileno(f));
    }
}


int main() {
    size_t size;
    FILE *f = fopen("/media/sng/BM_DF0/Traps n Treasures (1993)(Starbyte)(En)[cr PSG](Disk 1 of 2).adf", "r");

    if (f) {
        printf("file open\n");

        fseek(f, 0, SEEK_END);
        size = ftell(f);
        rewind(f);

        printf("size %zu\n", size);

        read_all(f, size);

        fclose(f);
    }

    return 0;
}
