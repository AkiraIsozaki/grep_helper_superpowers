/* sample.c - C E2E test fixture */
#define STATUS "TARGET"

int check_status(char *code) {
    if (strcmp(code, STATUS) == 0) {
        return 1;
    }
    return 0;
}
