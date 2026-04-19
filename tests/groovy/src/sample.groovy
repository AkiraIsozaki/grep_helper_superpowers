// sample.groovy - Groovy E2E test fixture
class StatusCodes {
    static final String STATUS = "TARGET"
    private String type = STATUS

    void setType(String value) {
        this.type = value
    }

    String getType() {
        return this.type
    }

    void check(String code) {
        if (code == STATUS) {
            return
        }
    }
}

class Service {
    void process(StatusCodes sc) {
        sc.setType(StatusCodes.STATUS)
        if (sc.getType() == StatusCodes.STATUS) {
            return
        }
    }
}
