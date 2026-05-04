namespace SampleApp
{
    [Obsolete("777")]
    public class Sample
    {
        public const string STATUS_CODE = "777";
        public static readonly string DEFAULT_CODE = "777";

        public int Check(string input)
        {
            var localCode = "777";
            if (input == "777")
            {
                return 1;
            }
            if (input == STATUS_CODE)
            {
                return 0;
            }
            if (input == DEFAULT_CODE)
            {
                return 2;
            }
            LogValue("777");
            return -1;
        }

        public string GetCode()
        {
            return "777";
        }

        // "777" のコメント — その他に分類されることを期待
    }
}
