# Private Pokémon DS trading

Run one private Nintendo DS network with friend codes for live Wi-Fi Club sessions and a GTS for offers that can be completed later. Keep the services on a private LAN. The GTS framework's license allows private LAN use among people you know. Both players need a compatible DS client already configured for the private WFC service.

| Service | Backend | Saves |
|---|---|---|
| Friend codes and Wi-Fi Club | The pinned [AltWFC fork](https://github.com/ubergeek77/dwc_network_server_emulator/tree/68fcdb2989e57a10ec8cf8398ff7506c4c73d390) | Docker volume for profiles and friend lists |
| GTS offers and trade history | Your private [Poké Classic Framework](https://github.com/mm201/pkmn-classic-framework) web application | The framework's MySQL database |

## Run it

For a Windows home PC and a later move to a dedicated machine, follow the [Windows hosting and migration guide](WINDOWS-HOST.md).

Use Docker Compose with Linux containers. The AltWFC image runs as Linux x86-64 because its pinned legacy dependencies use x86-64 wheels.

1. Set up the private GTS web application and initialize its database using the [upstream deployment instructions](https://github.com/mm201/pkmn-classic-framework/wiki/Creating-a-development-server). The framework is deployed separately under [its own license](https://github.com/mm201/pkmn-classic-framework/blob/master/LICENSE.md). Publish the GTS web application at the root of its private HTTP origin so the `/pokemondpds/` and `/syachi2ds/` endpoints are available.
2. In this directory, copy `.env.example` to `.env`. On PowerShell use `Copy-Item .env.example .env`. Set `GTS_UPSTREAM` to the actual GTS origin reachable from Docker. For a GTS app listening on the Docker host, use `http://host.docker.internal:PORT` with its real port.
3. Run `docker compose up -d --build`. The gateway uses port 80 by default. To test on a machine with port 80 already in use, set `WFC_HTTP_PORT=8080` before starting. The games themselves use port 80 for GTS.
4. For two clients on the private LAN, bind the services to the host's private IPv4 address by setting `WFC_BIND_IP`. Configure the clients' private WFC access and DNS according to [AltWFC's client documentation](https://github.com/polaris-/dwc_network_server_emulator/wiki). On that private network, the clients must reach the gateway for Nintendo WFC authentication, the connection check, and the GTS, and reach the same host for the GameSpy services. Use a spare test save for each player before moving existing profiles to another network.

For clients already configured to use a private HTTP-compatible WFC service, the private resolver should direct `nas.nintendowifi.net`, `conntest.nintendowifi.net`, `gamestats2.gs.nintendowifi.net`, and the client’s GameSpy service names to this host. The gateway handles HTTP. Clients need a compatible WFC authentication setup before the games can sign in.

The gateway forwards Gen IV `/pokemondpds/` and Gen V `/syachi2ds/` requests to the private GTS origin. It routes NAS HTTP requests to AltWFC. The profiles volume and GTS database are private to their services. The deployment publishes only the HTTP gateway and GameSpy ports. Preserve both the profiles volume and the GTS database when moving the server. Restarting the stack with `docker compose down` and `docker compose up -d` preserves the profiles volume.

## Verify with two players

Use test saves with separate console profiles. Test the two generations independently.
Start Gen IV with Diamond, Pearl, Platinum, HeartGold, or SoulSilver. Start Gen V with Black or White.

1. Connect both players to the same private WFC network. Obtain their friend codes in game and register them in both Pal Pads. Verify they see each other in the Wi-Fi Club and can finish a trade.
2. In the GTS, have one player deposit an offer, the other player find and fulfill it, and the original player reconnect and collect the result.
3. Restart both servers and confirm the profiles and trade history survived. Repeat with a Gen V pair after the Gen IV check.

AltWFC's [title compatibility notes](https://github.com/ubergeek77/dwc_network_server_emulator/wiki/Compatibility) report Wi-Fi Club and GTS support for the target generations with limitations. The exact transaction and client compatibility checks above are still required for this deployment.

Run `python check.py` from the host to check the connection-test endpoint and friend-code listener. Add `--port 8080` if using the alternate HTTP test port, and `--pid TEST_PROFILE_ID` to check both GTS handshakes with your test profile. These checks leave offers and saves intact.
