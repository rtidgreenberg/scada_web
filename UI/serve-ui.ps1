<#
.SYNOPSIS
    Serves the SCADA Tag Monitor UI on a local static HTTP server and opens it.

.DESCRIPTION
    Iteration 1 talks to RTI Web Integration Service over its WebSocket API.
    The page is a static file, so all this script does is host UI/ on a local
    port and open a browser. It does NOT start WIS or any DDS app — run WIS
    (with -enableWebSockets) separately.

    Server is chosen automatically: python -m http.server if Python is on PATH,
    otherwise a tiny built-in Node static server. No packages are installed.

.PARAMETER Port
    Port to serve on. Default 8000 (kept off WIS's usual 8080).

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
Write-Host "  (make sure WIS is running with -enableWebSockets)" -ForegroundColor DarkGray
Write-Host "  Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

function Open-Browser($u) {
    if (-not $NoBrowser) { Start-Process $u | Out-Null }
}

# --- Prefer Python's built-in server ---------------------------------------
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if ($python) {
    Write-Host "  using: $($python.Source) -m http.server" -ForegroundColor DarkGray
    Open-Browser $Url
    & $python.Source -m http.server $Port --directory $UiDir
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
    res.writeHead(200, { "Content-Type": types[path.extname(fp).toLowerCase()] || "application/octet-stream" });
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
