package demo;

/**
 * Entity の getter 経由で値を取得するシナリオ（getter 経由の間接参照）。
 * 直接リテラルと getter 呼び出しは別行に分け、(file, line) の重複を避ける。
 */
public class Handler {

    private final Entity entity = new Entity();

    public boolean handle1() {
        String literal = "777";
        String fetched = entity.getType();
        return literal.equals(fetched);
    }

    public boolean handle2() {
        String literal = "777";
        String fetched = entity.getType();
        return literal.equals(fetched);
    }
}
