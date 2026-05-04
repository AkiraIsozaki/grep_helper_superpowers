package demo;

/**
 * private フィールド + getter / setter を持つエンティティ。
 * 同一クラス内で値が "777" になり、Handler / Mutator から getter / setter 経由で参照される。
 */
public class Entity {

    private String type = "777";

    public String getType() {
        return type;
    }

    public void setType(String value) {
        this.type = value;
    }
}
