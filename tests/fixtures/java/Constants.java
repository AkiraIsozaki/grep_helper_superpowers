package com.example;

/**
 * 統合テスト用サンプル: 直接参照・定数定義パターン
 */
public class Constants {

    /** 検索対象の定数 */
    public static final String SAMPLE_CODE = "SAMPLE";

    /** 条件判定での使用 */
    public static boolean isSample(String value) {
        if (value.equals(SAMPLE_CODE)) {
            return true;
        }
        return false;
    }

    /** return文での使用 */
    public static String getSampleCode() {
        return SAMPLE_CODE;
    }
}
