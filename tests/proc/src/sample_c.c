/* sample_c.c - mixed E2E fixture (plain C) */
#define MK_CODE "MIXVAL"

int check(char *code) {
    if (strcmp(code, MK_CODE) == 0) {
        return 1;
    }
    return 0;
}
