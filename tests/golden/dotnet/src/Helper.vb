Public Class Helper
    Public Const VB_STATUS_CODE As String = "777"

    Public Function Check(input As String) As Integer
        If input = "777" Then
            Return 1
        End If
        Return 0
    End Function
End Class

' "777" のコメント — その他に分類されることを期待
