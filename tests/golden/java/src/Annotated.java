package demo;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

/**
 * アノテーション (`@Annotation("777")`) パターンを多く含む。
 */
public class Annotated {

    @Retention(RetentionPolicy.RUNTIME)
    public @interface Tag {
        String value();
    }

    @Tag("777")
    public void m1() {
    }

    @Tag("777")
    public void m2() {
    }

    @Tag("777")
    public void m3() {
    }

    @Tag("777")
    public void m4() {
    }

    @Tag("777")
    public void m5() {
    }

    @Tag("777")
    public void m6() {
    }

    @Tag("777")
    public void m7() {
    }

    @Tag("777")
    public void m8() {
    }

    @Tag("777")
    public void m9() {
    }

    @Tag("777")
    public void m10() {
    }

    @Tag("777")
    public void m11() {
    }

    @Tag("777")
    public void m12() {
    }
}
