<#
.SYNOPSIS
    Serves the SCADA Tag Monitor UI on a local static HTTP server and opens it.

.DESCRIPTION
    The UI talks to scada_web's native REST/WebSocket API (GET /api/v1/...,
    WS /ws). The page is a static file, so all this script does is host UI/ on
    a local port and open a browser. It does NOT start scada_web itself — run
    `python -m scada_web` separately (it also serves this UI directly on its
    own port via document_root, so this script is only needed for a standalone
    preview on a different port).

    Server is chosen automatically: python -m http.server if Python is on PATH,
    otherwise a tiny built-in Node static server. No packages are installed.

.PARAMETER Port
    Port to serve on. Default 8000 (kept off scada_web's usual 8080).

.PARAMETER NoBrowser
    Don't auto-open the browser.

.EXAMPLE
    .\serve-ui.ps1
.EXAMPLE
    .\serve-ui.ps1 -Port 9000 -NoBrowser
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$UiDir = $PSScriptRoot
$Url   = "http://localhost:$Port/"

Write-Host ""
Write-Host "  SCADA Tag Monitor UI" -ForegroundColor Cyan
Write-Host "  serving : $UiDir"
Write-Host "  url     : $Url"
Write-Host "  (make sure scada_web is running: python -m scada_web)" -ForegroundColor DarkGray
Write-Host "  Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

function Open-Browser($u) {
    if (-not $NoBrowser) { Start-Process $u | Out-Null }
}

# --- Prefer Python's built-in server ---------------------------------------
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if ($python) {
    $pyServer = @'
import http.server
import mimetypes
import os
import sys
from urllib.parse import unquote

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        self.path = unquote(self.path)
        return super().do_GET()

    def do_HEAD(self):
        self.path = unquote(self.path)
        return super().do_HEAD()

if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    os.chdir(root)
    mimetypes.init()
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), NoCacheHandler) as httpd:
        print(f"serving {root} on http://127.0.0.1:{port}/")
        httpd.serve_forever()
'@
    $tmp = Join-Path $env:TEMP "scada_ui_server.py"
    [System.IO.File]::WriteAllText($tmp, $pyServer, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  using: $($python.Source) (custom no-cache server)" -ForegroundColor DarkGray
    Open-Browser $Url
    & $python.Source $tmp $UiDir $Port
    return
}

# --- Fallback: minimal Node static server (no npm install) ------------------
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $js = @'
const http = require("http"), fs = require("fs"), path = require("path");
const dir = path.resolve(process.argv[2]), port = Number(process.argv[3]);
const types = { ".html":"text/html", ".js":"text/javascript", ".css":"text/css",
                ".json":"application/json", ".svg":"image/svg+xml", ".ico":"image/x-icon" };
http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split("?")[0]);
  if (p === "/" || p === "") p = "/index.html";
  const fp = path.join(dir, p);
  if (!fp.startsWith(dir)) { res.writeHead(403); res.end("forbidden"); return; }
  fs.readFile(fp, (e, d) => {
    if (e) { res.writeHead(404); res.end("not found"); return; }
    const headers = { "Content-Type": types[path.extname(fp).toLowerCase()] || "application/octet-stream" };
    if (path.extname(fp).toLowerCase() === ".html") {
      headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0";
      headers["Pragma"] = "no-cache";
      headers["Expires"] = "0";
    }
    res.writeHead(200, headers);
    res.end(d);
  });
}).listen(port, () => console.log("  node static server listening on " + port));
'@
    $tmp = Join-Path $env:TEMP "scada_ui_server.js"
    [System.IO.File]::WriteAllText($tmp, $js, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  using: $($node.Source) (built-in fallback server)" -ForegroundColor DarkGray
    Open-Browser $Url
    & $node.Source $tmp $UiDir $Port
    return
}

Write-Error "Neither 'python' nor 'node' found on PATH. Install one, or just open UI\index.html directly in a browser."
