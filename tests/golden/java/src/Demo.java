package demo;

public class Demo {
    public static final String DEMO_CODE = "777";

    @Deprecated
    public String process(String input) {
        if (input.equals("777")) {
            return "777";
        }
        String local = "777";
        return local;
    }

    public void other() {
        System.out.println("777");
    }
}
