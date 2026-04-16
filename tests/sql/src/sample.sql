-- sample.sql - Oracle SQL E2E test fixture
CREATE OR REPLACE PROCEDURE test_proc AS
  v_code VARCHAR2(10) := 'TARGET';
BEGIN
  IF v_code = 'check' THEN
    DBMS_OUTPUT.PUT_LINE(v_code);
  END IF;
END;
/
