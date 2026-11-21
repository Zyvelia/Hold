# Host Pokémon DS trading on your home PC

Start on a Windows PC with Docker Desktop in Linux-container mode. Keep both players on your private LAN for the first test. Later, move the server data to the always-on PC. Use the [server overview](README.md) for compatible games and trade tests.

## Set up the Windows PC

1. Reserve a private IPv4 address for the host in your router's DHCP settings. In PowerShell, use `ipconfig` to find the address for its active Ethernet or Wi-Fi adapter.
2. Install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/), start it, then run `docker compose version` in PowerShell. Install Python 3 for the included checks.
3. Set up the separate GTS backend using the [Poké Classic Framework deployment guide](https://github.com/mm201/pkmn-classic-framework/wiki/Creating-a-development-server). Retrieve the framework with its Git submodules. Enable ASP.NET in IIS, publish the `gts` project at the root of an IIS site, and use HTTP port `8081` with the host name left blank in the IIS binding. Leave port `80` available for Docker. Configure the database connection strings, load `library/database.sql`, and run the Veekun import for the initial database. Keep the database on localhost. The battle video service is optional for these two trading features.
4. Open PowerShell in this repository's `server/ds-wfc` folder. Copy `.env.example` to `.env`. Set `WFC_BIND_IP` to the reserved private IPv4 address, keep `WFC_HTTP_PORT=80`, and set `GTS_UPSTREAM` to the IIS origin reachable by the Docker containers. The example below uses the host's private address to reach IIS from Docker. Add that address to `WFC_NO_PROXY` if the host uses an HTTP proxy.

```dotenv
WFC_BIND_IP=192.168.1.50
WFC_HTTP_PORT=80
GTS_UPSTREAM=http://192.168.1.50:8081
WFC_NO_PROXY=192.168.1.50
```

```powershell
docker compose up -d --build
docker compose ps
py -3 check.py --host 192.168.1.50
```

Use your reserved address in both places. Check the same address from a second LAN device. If Windows Firewall blocks the game traffic, allow the published ports on the Private profile, scoped to the local subnet. Allow the Docker gateway to reach IIS on `8081`. The game ports are TCP `80`, `28910`, `29900`, `29901`, `29920` and UDP `27900`, `27901`. Keep the services private with no router port forwarding.

Configure both compatible clients to use your private WFC network as described in the [server overview](README.md#run-it). Start with test saves. Finish one Wi-Fi Club trade and one GTS deposit, fulfillment, and pickup before switching to your regular saves. Add `--pid` and a test GameSpy profile ID to `check.py` to test both GTS handshakes. If those checks return HTTP 502, check Docker's access to IIS and the IIS site binding.

## Move to the always-on PC

Set up IIS or another compatible ASP.NET host, the same GTS backend, and Docker Compose with Linux containers on the destination. Reserve its private address. Keep the destination services stopped until the data is restored. Preserve the players' DS saves and WFC profiles as well as the server data.

On the old host, stop the Compose stack with `docker compose stop` and stop the GTS web site so trades cannot change during the backup. Keep MySQL running for the dump. In PowerShell, from `server/ds-wfc`:

```powershell
$backup = Join-Path $env:USERPROFILE ("pokemon-wfc-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $backup -ErrorAction Stop | Out-Null

docker compose run --rm --no-deps -T --volume "§{backup}:/backup" --entrypoint sh friend-codes -ec 'test -s /app/state/gpcm.db; tar -czf /backup/wfc-profiles.tar.gz -C /app/state .; tar -tzf /backup/wfc-profiles.tar.gz'
if ($LASTEXITCODE -ne 0) { throw "Profile backup failed" }

mysqldump -u root -p --single-transaction --databases gts "--result-file=$backup\gts.sql"
if ($LASTEXITCODE -ne 0) { throw "GTS database backup failed" }
```

Use the actual GTS database name if it differs from `gts`. With MariaDB, use the corresponding `mariadb-dump` and `mariadb` commands. Store the archive and SQL dump privately. Transfer the local deployment settings securely, including the GTS database connection settings. For a cutover, leave the old services stopped.

On a Windows destination, load the same server files, configure `.env` with the new IP, and build the image with `docker compose build friend-codes`. Point `$backup` to the transferred folder. Restore into a fresh Compose volume and an empty MySQL instance or one where the GTS database name is unused:

```powershell
$backup = (Resolve-Path 'C:\path\to\pokemon-wfc-backup').Path

docker compose run --rm --no-deps -T --volume "§{backup}:/backup:ro" --entrypoint sh friend-codes -ec 'test $(ls -A /app/state | wc -l) -eq 0; tar -xzf /backup/wfc-profiles.tar.gz -C /app/state; test -s /app/state/gpcm.db'
if ($LASTEXITCODE -ne 0) { throw "Profile restore failed or the destination volume is already in use" }

Push-Location $backup
try {
    mysql -u root -p --execute='source gts.sql'
    if ($LASTEXITCODE -ne 0) { throw "GTS database restore failed" }
} finally {
    Pop-Location
}
```

The profile restore requires an empty volume. Create the GTS application database user and grant it access separately. On a Linux destination, use the same Docker commands with an absolute `backup` path and import the dump using `mysql -u root -p < gts.sql` from the backup directory.

Start the destination GTS site and Docker stack, update the private DNS records to the new host address, then run the connection checks and verify existing friend codes and GTS offers with your test saves. The same Compose services restart with Docker. On Docker Desktop, enable **Start Docker Desktop when you sign in** and verify the stack after a reboot and sign-in. For unattended startup on Linux, enable Docker at boot. Keep the source backups until the destination passes the in-game checks.
