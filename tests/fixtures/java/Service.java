package com.example;

/**
 * 統合テスト用サンプル: 間接参照・getter呼び出し パターン
 */
public class Service {

    public void process(Entity entity) {
        // getter経由での使用
        if (entity.getType().equals("SAMPLE")) {
            System.out.println("matched");
        }
    }

    public boolean isValid(String code) {
        return Constants.SAMPLE_CODE.equals(code);
    }
}
