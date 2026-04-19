// sample.cs - .NET E2E test fixture
public class StatusCodes {
    public const string STATUS = "TARGET";
    public static readonly string ALIAS = STATUS;
}
public class Service {
    public void Check(string code) {
        if (code == StatusCodes.STATUS) {
            return;
        }
    }
}
