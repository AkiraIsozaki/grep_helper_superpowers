package sample

@Deprecated("777")
class Sample {
    static final String STATUS_CODE = "777"
    public String type = "777"

    String getType() {
        return this.type
    }

    void setType(String value) {
        this.type = value
    }

    int check(String input) {
        def localCode = "777"
        if (input == "777") {
            return 1
        }
        if (input == STATUS_CODE) {
            return 0
        }
        logValue("777")
        return -1
    }

    String getCode() {
        return "777"
    }

    // "777" のコメント — その他に分類されることを期待
}
