package demo;

/**
 * 別クラスでも定数定義パターンを混ぜる。
 */
public final class Status {

    public static final String SUCCESS = "777";
    public static final String FAILURE = "777";
    public static final String PENDING = "777";

    private Status() {
        // utility class
    }
}
