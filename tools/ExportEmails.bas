Attribute VB_Name = "ExportEmails"
' ============================================================================
'  ExportEmails.bas  —  Outlook VBA macro
'  Exports the e-mails you have SELECTED in Outlook to one .json file each,
'  into the project's  outlook_drop\  folder, so the Python pipeline can turn
'  them into the AWR dashboard knowledge base.
'
'  Install (one time):
'     Outlook -> Alt+F11 -> File -> Import File... -> pick this .bas -> Open.
'  Use:
'     Select the e-mails (Ctrl+click or Ctrl+A in a filtered view)
'     -> Alt+F8 -> ExportSelectedEmails -> Run.
'
'  Change DROP_FOLDER below if your workspace lives somewhere else.
' ============================================================================
Option Explicit

' Where the .json files are written. Must match the workspace the Python
' pipeline runs in (the build scripts read from <workspace>\outlook_drop\).
Private Const DROP_FOLDER As String = _
    "C:\Users\1039081\Downloads\cluade\awr-dashboard\outlook_drop\"

Public Sub ExportSelectedEmails()
    Dim sel As Outlook.Selection
    Dim itm As Object
    Dim mail As Outlook.MailItem
    Dim fso As Object
    Dim ts As Object
    Dim n As Long
    Dim path As String

    On Error GoTo Fail

    Set fso = CreateObject("Scripting.FileSystemObject")
    EnsureFolder fso, DROP_FOLDER

    Set sel = Application.ActiveExplorer.Selection
    If sel Is Nothing Or sel.Count = 0 Then
        MsgBox "No e-mails selected. Select one or more messages and run again.", vbExclamation
        Exit Sub
    End If

    n = 0
    For Each itm In sel
        If TypeOf itm Is Outlook.MailItem Then
            Set mail = itm
            path = DROP_FOLDER & SafeName(mail) & ".json"
            Set ts = fso.CreateTextFile(path, True, True) ' overwrite, Unicode
            ts.Write MailToJson(mail)
            ts.Close
            n = n + 1
        End If
    Next itm

    MsgBox "Exported " & n & " email(s) to:" & vbCrLf & DROP_FOLDER & vbCrLf & vbCrLf & _
           "Now run the Python build steps in VS Code.", vbInformation
    Exit Sub

Fail:
    MsgBox "Export failed: " & Err.Description, vbCritical
End Sub

' --- build a JSON object for one mail item ---------------------------------
Private Function MailToJson(ByVal mail As Outlook.MailItem) As String
    Dim sender As String, senderName As String, received As String
    senderName = NzStr(mail.SenderName)
    sender = SenderAddress(mail)
    received = Format(mail.ReceivedTime, "yyyy-mm-ddThh:nn:ss")

    MailToJson = "{" & _
        JKey("from_name") & JStr(senderName) & "," & _
        JKey("from_email") & JStr(sender) & "," & _
        JKey("subject") & JStr(NzStr(mail.Subject)) & "," & _
        JKey("received") & JStr(received) & "," & _
        JKey("body") & JStr(NzStr(mail.Body)) & _
        "}"
End Function

Private Function SenderAddress(ByVal mail As Outlook.MailItem) As String
    On Error Resume Next
    Dim addr As String
    addr = mail.SenderEmailAddress
    ' Resolve Exchange X.500 addresses to SMTP where possible.
    If InStr(1, addr, "/O=", vbTextCompare) > 0 Then
        Dim pa As Outlook.PropertyAccessor
        Set pa = mail.PropertyAccessor
        addr = pa.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x39FE001E")
    End If
    SenderAddress = NzStr(addr)
End Function

' --- helpers ---------------------------------------------------------------
Private Sub EnsureFolder(ByVal fso As Object, ByVal folderPath As String)
    Dim parent As String
    If fso.FolderExists(folderPath) Then Exit Sub
    parent = fso.GetParentFolderName(folderPath)
    If Len(parent) > 0 And Not fso.FolderExists(parent) Then EnsureFolder fso, parent
    fso.CreateFolder folderPath
End Sub

' Stable, filesystem-safe, de-duplicating file name: received + short subject.
Private Function SafeName(ByVal mail As Outlook.MailItem) As String
    Dim s As String
    s = Format(mail.ReceivedTime, "yyyymmdd_hhnnss") & "_" & NzStr(mail.SenderName) & "_" & NzStr(mail.Subject)
    Dim i As Integer, ch As String, out As String
    For i = 1 To Len(s)
        ch = Mid(s, i, 1)
        If ch Like "[A-Za-z0-9_]" Then
            out = out & ch
        ElseIf ch = " " Or ch = "-" Then
            out = out & "_"
        End If
    Next i
    If Len(out) > 120 Then out = Left(out, 120)
    SafeName = out
End Function

Private Function NzStr(ByVal v As Variant) As String
    If IsNull(v) Then NzStr = "" Else NzStr = CStr(v)
End Function

Private Function JKey(ByVal k As String) As String
    JKey = """" & k & """:"
End Function

' JSON string-escape, including control chars and unicode-safe newlines.
Private Function JStr(ByVal s As String) As String
    Dim i As Long, ch As String, code As Long, out As String
    out = ""
    For i = 1 To Len(s)
        ch = Mid(s, i, 1)
        code = AscW(ch)
        Select Case code
            Case 34: out = out & "\"""      ' "
            Case 92: out = out & "\\"        ' \
            Case 8:  out = out & "\b"
            Case 9:  out = out & "\t"
            Case 10: out = out & "\n"
            Case 12: out = out & "\f"
            Case 13: out = out & "\r"
            Case Is < 32: out = out & "\u" & Right("0000" & Hex(code), 4)
            Case Else: out = out & ch
        End Select
    Next i
    JStr = """" & out & """"
End Function
