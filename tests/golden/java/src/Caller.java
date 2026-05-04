package demo;

/**
 * メソッド引数 (MethodInvocation / ClassCreator) を多く含む。
 */
public class Caller {

    public void invoke1() {
        System.out.println("777");
    }

    public void invoke2() {
        System.out.println("777");
    }

    public void invoke3() {
        System.out.println("777");
    }

    public void invoke4() {
        System.err.println("777");
    }

    public void invoke5() {
        System.err.println("777");
    }

    public void invoke6() {
        log("777");
    }

    public void invoke7() {
        log("777");
    }

    public void invoke8() {
        log("777");
    }

    public void invoke9() {
        log("777");
    }

    public void invoke10() {
        log("777");
    }

    public void invoke11() {
        log("777");
    }

    public void invoke12() {
        log("777");
    }

    private void log(String s) {
        System.out.println(s);
    }
}
