PACKAGE BODY other_pkg AS
    PROCEDURE process(p_input IN VARCHAR2) IS
    BEGIN
        IF p_input = sample_pkg.c_default_code THEN
            INSERT INTO log_table (code) VALUES (sample_pkg.c_default_code);
        END IF;
        RETURN sample_pkg.c_default_code;
    END;
END other_pkg;
