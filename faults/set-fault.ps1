param(
    [Parameter(Mandatory=$true)][ValidateSet("force_500","slow_requests","redis_failure")][string]$Fault,
    [Parameter(Mandatory=$true)][ValidateSet("on","off")][string]$State
)

$enabled = if ($State -eq "on") { "True" } else { "False" }
$code = "import urllib.request, json; r=urllib.request.Request('http://localhost:8000/admin/faults/$Fault', data=json.dumps({'enabled': $enabled}).encode(), method='PUT', headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(r).read().decode())"
docker compose exec api python -c $code
