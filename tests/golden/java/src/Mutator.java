package demo;

/**
 * Entity の setter 経由で値を流し込むシナリオ（setter 経由の間接参照）。
 * 直接リテラルと setter 呼び出しは別行に分け、(file, line) の重複を避ける。
 */
public class Mutator {

    private final Entity entity = new Entity();

    public void apply1() {
        String value = "777";
        entity.setType(value);
    }

    public void apply2() {
        String value = "777";
        entity.setType(value);
    }
}
