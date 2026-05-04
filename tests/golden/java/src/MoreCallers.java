package demo;

/**
 * メソッド引数 (ClassCreator / nested call) のバリエーションを増やす。
 */
public class MoreCallers {

    public void a1() {
        new StringBuilder("777");
    }

    public void a2() {
        new StringBuilder("777");
    }

    public void a3() {
        new StringBuilder("777");
    }

    public void a4() {
        new StringBuilder("777");
    }

    public void a5() {
        new StringBuilder("777");
    }
}
