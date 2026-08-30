<#
.SYNOPSIS
  Live, human-readable view of the SENTINEL agent's activity.

.DESCRIPTION
  Tails logs/sentinel.jsonl and pretty-prints each structured event with colour,
  so you can watch an incident go alert -> investigate -> RCA -> approve -> fix
  without a TrueForge UI. Run in its own terminal alongside `python -m agent.main`.
#>
[CmdletBinding()]
param([string]$LogFile = "logs/sentinel.jsonl")

$skip = @('timestamp', 'event', 'level', 'correlation_id', 'logger')

function Colour($level) {
  switch ($level) {
    'error'   { 'Red' }
    'warning' { 'Yellow' }
    default   { 'Gray' }
  }
}

Write-Host "watching $LogFile  (Ctrl+C to stop)" -ForegroundColor Cyan
Get-Content $LogFile -Wait -Tail 5 | ForEach-Object {
  try { $e = $_ | ConvertFrom-Json } catch { return }
  $ts = try { ([datetime]$e.timestamp).ToLocalTime().ToString('HH:mm:ss') } catch { '--:--:--' }
  $rest = $e.PSObject.Properties |
    Where-Object { $_.Name -notin $skip } |
    ForEach-Object { "$($_.Name)=$($_.Value)" }
  $line = "{0}  {1,-28}  {2}" -f $ts, $e.event, ($rest -join '  ')
  Write-Host $line -ForegroundColor (Colour $e.level)
}
