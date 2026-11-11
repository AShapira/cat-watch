# Runs in the signed-in Windows session; no idle-time or lock-screen heuristic.
[CmdletBinding()]
param([string]$StateDirectory='C:\Alex\data\tapo-cat-monitor\display-state', [switch]$CompileOnly)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$source = @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

public sealed class CatWatchDisplay : Form {
    [DllImport("user32.dll", SetLastError=true)]
    static extern IntPtr RegisterPowerSettingNotification(IntPtr recipient, ref Guid setting, uint flags);
    [DllImport("user32.dll")]
    static extern bool UnregisterPowerSettingNotification(IntPtr handle);
    static readonly Guid ConsoleDisplay = new Guid("6FE69556-704A-47A0-8F24-C28D936FDA47");
    readonly string directory;
    readonly Timer timer = new Timer();
    IntPtr registration;
    string display = "unknown";
    long sequence = 0;
    readonly string instance = Guid.NewGuid().ToString("N");

    public CatWatchDisplay(string path) {
        directory = path;
        Directory.CreateDirectory(directory);
        ShowInTaskbar = false;
        Guid setting = ConsoleDisplay;
        registration = RegisterPowerSettingNotification(Handle, ref setting, 0);
        if (registration == IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
        WriteState();
        timer.Interval = 5000;
        timer.Tick += delegate { WriteState(); };
        timer.Start();
    }
    protected override void SetVisibleCore(bool value) { base.SetVisibleCore(false); }
    void WriteState() {
        double stamp = (DateTime.UtcNow - new DateTime(1970,1,1,0,0,0,DateTimeKind.Utc)).TotalSeconds;
        string json = "{\"schema\":1,\"display\":\"" + display + "\",\"updated_unix\":" +
            stamp.ToString("F3",System.Globalization.CultureInfo.InvariantCulture) +
            ",\"sequence\":" + (++sequence) + ",\"instance\":\"" + instance + "\"}";
        string target = Path.Combine(directory,"state.json");
        string temporary = Path.Combine(directory,"state."+instance+".tmp");
        try {
            File.WriteAllText(temporary,json,new UTF8Encoding(false));
            if (File.Exists(target)) File.Replace(temporary,target,null);
            else File.Move(temporary,target);
        } catch (IOException) {
            // A transient sharing conflict must not open an exception dialog.
            // Readers fail quiet if successful heartbeats stop for 20 seconds.
        } catch (UnauthorizedAccessException) { }
    }
    protected override void WndProc(ref Message m) {
        if (m.Msg == 0x218 && m.WParam.ToInt32() == 0x8013 && m.LParam != IntPtr.Zero) {
            Guid setting = (Guid)Marshal.PtrToStructure(m.LParam,typeof(Guid));
            if (setting == ConsoleDisplay && Marshal.ReadInt32(m.LParam,16) == 4) {
                int value = Marshal.ReadInt32(m.LParam,20);
                display = value == 0 ? "off" : value == 1 ? "on" : value == 2 ? "dimmed" : "unknown";
                WriteState();
            }
        }
        // Never preserve an old off signal across suspend/resume.
        if (m.Msg == 0x218 && (m.WParam.ToInt32() == 4 || m.WParam.ToInt32() == 18)) {
            display = "unknown";
            WriteState();
        }
        base.WndProc(ref m);
    }
    protected override void Dispose(bool disposing) {
        timer.Stop();
        display = "unknown";
        WriteState();
        if (registration != IntPtr.Zero) UnregisterPowerSettingNotification(registration);
        if (disposing) timer.Dispose();
        base.Dispose(disposing);
    }
    [STAThread]
    public static void Run(string path) {
        bool created;
        using (var mutex = new System.Threading.Mutex(true,"Local\\CatWatchDisplayWatcher",out created)) {
            if (!created) return;
            Application.Run(new CatWatchDisplay(path));
        }
    }
}
'@
Add-Type -TypeDefinition $source -ReferencedAssemblies System.Windows.Forms
if ($CompileOnly) { Write-Output 'Display watcher compiled'; exit 0 }
[CatWatchDisplay]::Run($StateDirectory)
