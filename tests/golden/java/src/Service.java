package demo;

/**
 * Java 条件判定パターン（if / while / equals / 比較演算子）を集約。
 * 直接リテラル参照に加えて、定数経由の間接参照シナリオも含む。
 */
public class Service {

    public boolean check1(String input) {
        if (input.equals("777")) {
            return true;
        }
        return false;
    }

    public boolean check2(String input) {
        if ("777".equals(input)) {
            return true;
        }
        return false;
    }

    public boolean check3(String input) {
        while (input.equals("777")) {
            input = input.substring(1);
        }
        return input.isEmpty();
    }

    public boolean check4(String input) {
        if (input == "777") {
            return true;
        }
        return false;
    }

    public boolean check5(String input) {
        if (!input.equals("777")) {
            return true;
        }
        return false;
    }

    public boolean check6(String input) {
        if (input != null && input.equals("777")) {
            return true;
        }
        return false;
    }

    public boolean check7(String input) {
        if (input.equals(Constants.CODE)) {
            return true;
        }
        return false;
    }

    public boolean check8(String input) {
        if (Constants.CODE.equals(input)) {
            return true;
        }
        return false;
    }

    public boolean check9(String input) {
        while (!input.equals("777") && input.length() > 0) {
            input = input.substring(1);
        }
        return true;
    }

    public boolean check10(String input) {
        if (input.equalsIgnoreCase("777")) {
            return true;
        }
        return false;
    }

    public boolean check11(String input) {
        if (input.startsWith("777")) {
            return true;
        }
        return false;
    }

    public boolean check12(String input) {
        if ("777" == input) {
            return true;
        }
        return false;
    }
}
