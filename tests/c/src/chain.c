/* chain.c - multi-level #define test fixture */
#define ALIAS STATUS
#define DEEP ALIAS

int use_alias(char *code) {
    if (strcmp(code, ALIAS) == 0) {
        return 1;
    }
    return 0;
}

int use_deep(char *code) {
    return strcmp(code, DEEP);
}
